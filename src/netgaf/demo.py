"""Offline synthetic packets only. Does not transmit anything onto the network."""

import json
from pathlib import Path

import numpy as np
from scapy.layers.inet import IP, TCP
from scapy.layers.l2 import Ether
from scapy.packet import Raw
from scapy.utils import PcapWriter

from .capture import check_cancelled


def generate_demo(directory: str | Path, seed: int = 42, cancel=None) -> dict[str, Path]:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    names = (
        "normal.pcap",
        "mixed.pcap",
        "packet_burst.pcap",
        "byte_surge.pcap",
        "port_diversity.pcap",
        "labels.json",
    )
    outputs = {name: directory / name for name in names}
    if any(path.exists() for path in outputs.values()):
        raise ValueError("В выбранной папке уже есть демонстрационные файлы. Выберите новую папку.")
    base = 1_767_225_600  # 2026-01-01 00:00:00 UTC
    length = 640
    scenarios = {
        "normal.pcap": [],
        "packet_burst.pcap": [(256, 384, "packet_burst")],
        "byte_surge.pcap": [(256, 384, "byte_surge")],
        "port_diversity.pcap": [(256, 384, "port_diversity")],
        "mixed.pcap": [
            (128, 224, "packet_burst"),
            (288, 384, "byte_surge"),
            (448, 544, "port_diversity"),
        ],
    }
    for file_index, (filename, intervals) in enumerate(scenarios.items()):
        rng = np.random.default_rng(seed + file_index)
        with PcapWriter(str(outputs[filename]), sync=True) as writer:
            for second in range(length + 1):
                check_cancelled(cancel)
                kind = next((kind for start, end, kind in intervals if start <= second < end), None)
                count = int(rng.integers(4, 9)) + int(2 * np.sin(second / 8))
                if kind == "packet_burst":
                    count = 55
                for index in range(count):
                    port = 1000 + index if kind == "port_diversity" else (443 if index % 2 else 80)
                    size = 1200 if kind == "byte_surge" else int(rng.integers(30, 130))
                    packet = (
                        Ether(src="02:00:00:00:00:01", dst="02:00:00:00:00:02")
                        / IP(src="192.0.2.10", dst="198.51.100.20")
                        / TCP(
                            sport=50000, dport=port, flags="S" if kind == "port_diversity" else "PA"
                        )
                        / Raw(b"x" * size)
                    )
                    packet.time = base + second + index / (count + 1)
                    writer.write(packet)
    outputs["labels.json"].write_text(
        json.dumps(
            {
                "synthetic": True,
                "note": "Only a functional demonstration. Not evidence of real-world detection quality.",
                "node": "192.0.2.10",
                "window_label_rule": "any positive-duration overlap with a labelled interval",
                "scenarios": {
                    filename: [
                        {
                            "start_ns": (base + start) * 10**9,
                            "end_ns": (base + end) * 10**9,
                            "label": kind,
                        }
                        for start, end, kind in intervals
                    ]
                    for filename, intervals in scenarios.items()
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return outputs
