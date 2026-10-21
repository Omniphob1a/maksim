import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLCONFIGDIR", tempfile.mkdtemp(prefix="netgaf-mpl-"))
os.environ.setdefault("XDG_CACHE_HOME", tempfile.mkdtemp(prefix="netgaf-cache-"))

import pytest
from scapy.layers.inet import IP, TCP
from scapy.layers.l2 import Ether
from scapy.packet import Raw
from scapy.utils import PcapWriter

from netgaf.capture import read_capture
from netgaf.config import AnalysisConfig
from netgaf.model import train_detector


@pytest.fixture(scope="session")
def normal_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("captures") / "normal.pcap"
    with PcapWriter(str(path), sync=True) as writer:
        for second in range(225):
            for index in range(3 + second % 5):
                packet = (
                    Ether(src="02:00:00:00:00:01", dst="02:00:00:00:00:02")
                    / IP(src="192.0.2.1", dst="198.51.100.2")
                    / TCP(sport=40000, dport=80 + index % 2)
                    / Raw(b"x" * (40 + second % 100))
                )
                packet.time = 1_700_000_000 + second + index / 10
                writer.write(packet)
    return path


@pytest.fixture(scope="session")
def trained(normal_path):
    config = AnalysisConfig()
    capture = read_capture(normal_path, config)
    return train_detector([capture], config, epochs=3), capture
