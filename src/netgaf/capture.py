"""Streaming extraction. No payload inspection and no network capture privileges required."""

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Callable

import numpy as np
from scapy.layers.inet import IP, TCP, UDP
from scapy.layers.inet6 import (
    IPv6,
    IPv6ExtHdrDestOpt,
    IPv6ExtHdrFragment,
    IPv6ExtHdrHopByHop,
    IPv6ExtHdrRouting,
)
from scapy.utils import PcapReader

from .config import AnalysisConfig


class CancelledError(Exception):
    pass


def check_cancelled(cancel: Callable[[], bool] | None):
    if cancel and cancel():
        raise CancelledError("Операция отменена.")


@dataclass
class CaptureStats:
    total: int = 0
    ip_packets: int = 0
    skipped_non_ip: int = 0
    truncated: int = 0
    segments: int = 0
    excluded_partial_bins: int = 0


@dataclass
class Series:
    source: str
    node: str
    segment: int
    start_ns: int
    values: np.ndarray


@dataclass
class CaptureData:
    series: list[Series]
    stats: CaptureStats
    source: str


@dataclass
class _Segment:
    start: int
    end: int
    buckets: dict = field(default_factory=dict)


def read_capture(
    path: str | Path,
    config: AnalysisConfig,
    progress: Callable[[str], None] = lambda _: None,
    cancel: Callable[[], bool] | None = None,
) -> CaptureData:
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError(f"Файл не найден: {path}")
    interval_ns = round(config.interval * 1_000_000_000)
    gap_ns = round(config.gap_seconds * 1_000_000_000)
    stats = CaptureStats()
    segments: list[_Segment] = []
    previous = None
    bucket_count = 0
    progress(f"Чтение {path.name}…")
    try:
        with PcapReader(str(path)) as reader:
            for packet in reader:
                check_cancelled(cancel)
                stats.total += 1
                stamp = int(Decimal(str(packet.time)) * 1_000_000_000)
                if previous is not None and stamp < previous:
                    raise ValueError(
                        f"Пакет {stats.total}: нарушен порядок временных меток. "
                        "Подготовьте хронологический захват (например, reordercap)."
                    )
                if previous is None or stamp - previous > gap_ns:
                    segments.append(_Segment(stamp, stamp))
                previous = stamp
                segment = segments[-1]
                segment.end = stamp
                bin_index = (stamp - segment.start) // interval_ns
                if bin_index > config.max_bins:
                    raise ValueError(
                        "Слишком длинный захват: увеличьте шаг времени или разделите файл."
                    )
                ip = packet.getlayer(IP) or packet.getlayer(IPv6)
                if ip is None:
                    stats.skipped_non_ip += 1
                    continue
                stats.ip_packets += 1
                node = str(ip.src if config.direction == "outgoing" else ip.dst)
                # Do not attach an encapsulated TCP/UDP port to an outer IP node.
                transport = ip.payload
                while isinstance(
                    transport,
                    (IPv6ExtHdrDestOpt, IPv6ExtHdrFragment, IPv6ExtHdrHopByHop, IPv6ExtHdrRouting),
                ):
                    transport = transport.payload
                port = int(transport.dport) if isinstance(transport, (TCP, UDP)) else None
                captured_size = len(packet.original)
                if getattr(packet, "wirelen", captured_size) > captured_size:
                    stats.truncated += 1
                key = (node, bin_index)
                if key not in segment.buckets:
                    bucket_count += 1
                    if bucket_count > config.max_cells // 3:
                        raise ValueError("Превышен лимит агрегатов. Разделите захват на части.")
                    segment.buckets[key] = [0, 0, set()]
                bucket = segment.buckets[key]
                bucket[0] += 1
                bucket[1] += captured_size
                if port is not None:
                    bucket[2].add(port)
                if stats.total % 25_000 == 0:
                    progress(f"Прочитано пакетов: {stats.total:,}")
    except (ValueError, CancelledError):
        raise
    except Exception as exc:
        raise ValueError(f"Не удалось прочитать PCAP/PCAPNG: {exc}") from exc
    stats.segments = len(segments)
    result = []
    cells = 0
    for segment_id, segment in enumerate(segments):
        check_cancelled(cancel)
        # Capture ends inside its final interval: do not invent a complete interval.
        bins = (segment.end - segment.start) // interval_ns
        stats.excluded_partial_bins += 1
        if bins < config.window_size:
            continue
        arrays = {}
        for (node, index), (packets, size, ports) in segment.buckets.items():
            if index >= bins:
                continue
            if node not in arrays:
                cells += bins * 3
                if cells > config.max_cells:
                    raise ValueError(
                        "Превышен лимит временных рядов. Увеличьте шаг времени или разделите файл."
                    )
                arrays[node] = np.zeros((bins, 3), dtype=np.float64)
            arrays[node][index] = (packets, size, len(ports))
        for node, values in sorted(arrays.items()):
            result.append(Series(str(path), node, segment_id, segment.start, values))
    if not result:
        raise ValueError(
            f"Нет полного окна из {config.window_size} интервалов по {config.interval:g} с. "
            "Нужен более длинный IP-захват или меньший шаг времени."
        )
    progress(f"Обработано {stats.ip_packets:,} IP-пакетов; рядов узлов: {len(result)}.")
    return CaptureData(result, stats, str(path))
