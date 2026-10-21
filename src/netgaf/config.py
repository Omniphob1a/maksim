import math
from dataclasses import asdict, dataclass

FEATURES = ("Пакеты", "Захваченные байты", "Уникальные порты назначения")


@dataclass(frozen=True)
class AnalysisConfig:
    interval: float = 1.0
    window_size: int = 32
    stride: int = 16
    direction: str = "outgoing"
    representation: str = "gasf"
    gap_seconds: float = 120.0
    max_bins: int = 200_000
    max_windows: int = 30_000
    max_cells: int = 6_000_000

    def __post_init__(self):
        if not math.isfinite(self.interval) or not 0.001 <= self.interval <= 3600:
            raise ValueError("Шаг времени должен быть от 0.001 до 3600 секунд.")
        if self.window_size not in (16, 32, 64):
            raise ValueError("Размер окна должен быть 16, 32 или 64.")
        if not 1 <= self.stride <= self.window_size:
            raise ValueError("Шаг окна должен быть от 1 до размера окна.")
        if self.direction not in ("incoming", "outgoing"):
            raise ValueError("Неизвестное направление трафика.")
        if self.representation not in ("gasf", "gadf"):
            raise ValueError("Поддерживаются GASF и GADF.")
        if not math.isfinite(self.gap_seconds) or self.gap_seconds <= self.interval:
            raise ValueError("Граница разрыва должна превышать шаг времени.")
        if min(self.max_bins, self.max_windows, self.max_cells) < 1:
            raise ValueError("Ограничения ресурсов должны быть положительными.")

    def to_dict(self):
        return asdict(self)
