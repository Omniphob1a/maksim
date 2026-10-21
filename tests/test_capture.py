import numpy as np
import pytest
from scapy.layers.inet import ICMP, IP, TCP
from scapy.layers.inet6 import IPv6
from scapy.layers.l2 import ARP, Ether
from scapy.utils import PcapNgWriter, PcapWriter

from netgaf.capture import CancelledError, read_capture
from netgaf.config import AnalysisConfig
from netgaf.windows import make_windows, training_split


@pytest.mark.parametrize("writer_type,suffix", [(PcapWriter, ".pcap"), (PcapNgWriter, ".pcapng")])
def test_real_packet_formats_and_missing_ports(tmp_path, writer_type, suffix):
    path = tmp_path / ("capture" + suffix)
    packets = [
        Ether(src="02:00:00:00:00:01", dst="02:00:00:00:00:02")
        / IP(src="192.0.2.1", dst="198.51.100.2")
        / TCP(dport=443),
        Ether(src="02:00:00:00:00:01", dst="02:00:00:00:00:02")
        / IP(src="192.0.2.1", dst="198.51.100.2")
        / ICMP(),
        Ether(src="02:00:00:00:00:01", dst="02:00:00:00:00:02")
        / IPv6(src="2001:db8::1", dst="2001:db8::2")
        / TCP(dport=80),
        Ether(src="02:00:00:00:00:01", dst="02:00:00:00:00:02") / ARP(),
    ]
    with writer_type(str(path)) as writer:
        for index, packet in enumerate(packets):
            packet.time = 1_700_000_000 + index / 10
            writer.write(packet)
        for second in range(1, 33):
            packet = packets[0].copy()
            packet.time = 1_700_000_000 + second
            writer.write(packet)
    capture = read_capture(path, AnalysisConfig(window_size=16))
    assert capture.stats.skipped_non_ip == 1
    assert capture.stats.ip_packets == 35
    host = next(s for s in capture.series if s.node == "192.0.2.1")
    assert host.values[0, 0] == 2
    assert host.values[0, 1] == len(bytes(packets[0])) + len(bytes(packets[1]))
    assert host.values[0, 2] == 1
    assert any(s.node == "2001:db8::1" for s in capture.series)
    assert len(host.values) == 32


def test_no_windows_across_capture_gaps(tmp_path):
    path = tmp_path / "gaps.pcap"
    with PcapWriter(str(path), sync=True) as writer:
        for base in (0, 1000):
            for second in range(33):
                packet = (
                    Ether(src="02:00:00:00:00:01", dst="02:00:00:00:00:02")
                    / IP(src="192.0.2.1", dst="198.51.100.2")
                    / TCP(dport=80)
                )
                packet.time = 1_700_000_000 + base + second
                writer.write(packet)
    config = AnalysisConfig(window_size=16)
    capture = read_capture(path, config)
    assert capture.stats.segments == 2
    windows = make_windows(capture.series, config)
    assert len(windows) == 4
    assert all((w.end_ns - w.start_ns) == 16_000_000_000 for w in windows)
    assert {w.segment for w in windows} == {0, 1}


def test_split_prevents_overlapping_training_and_calibration_events(normal_path):
    config = AnalysisConfig(stride=1)
    capture = read_capture(normal_path, config)
    training, validation = training_split(capture.series, config)
    assert max(w.end_ns for w in training) <= min(w.start_ns for w in validation)


def test_packet_order_error_is_explicit(tmp_path):
    path = tmp_path / "unordered.pcap"
    with PcapWriter(str(path), sync=True) as writer:
        for stamp in (1000, 999):
            packet = Ether(src="02:00:00:00:00:01", dst="02:00:00:00:00:02") / IP() / TCP()
            packet.time = stamp
            writer.write(packet)
    with pytest.raises(ValueError, match="порядок"):
        read_capture(path, AnalysisConfig())


def test_cancel_and_memory_limit(normal_path):
    with pytest.raises(CancelledError):
        read_capture(normal_path, AnalysisConfig(), cancel=lambda: True)
    with pytest.raises(ValueError, match="лимит|Превышен"):
        read_capture(normal_path, AnalysisConfig(max_cells=10))


def test_incoming_groups_by_receiver(normal_path):
    capture = read_capture(normal_path, AnalysisConfig(direction="incoming"))
    assert {s.node for s in capture.series} == {"198.51.100.2"}
    assert np.sum(capture.series[0].values[:, 0]) > 100


def test_outer_node_does_not_use_encapsulated_ports(tmp_path):
    path = tmp_path / "tunnel.pcap"
    with PcapWriter(str(path), sync=True) as writer:
        for second in range(33):
            packet = (
                Ether(src="02:00:00:00:00:01", dst="02:00:00:00:00:02")
                / IP(src="192.0.2.1", dst="198.51.100.2")
                / IP(src="10.0.0.1", dst="10.0.0.2")
                / TCP(dport=443)
            )
            packet.time = 1_700_000_000 + second
            writer.write(packet)
    capture = read_capture(path, AnalysisConfig())
    assert capture.series[0].node == "192.0.2.1"
    np.testing.assert_array_equal(capture.series[0].values[:, 2], 0)
