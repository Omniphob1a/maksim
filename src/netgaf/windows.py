from dataclasses import dataclass

import numpy as np

from .capture import Series
from .config import AnalysisConfig


@dataclass
class Window:
    source: str
    node: str
    segment: int
    start_ns: int
    end_ns: int
    values: np.ndarray


def make_windows(series: list[Series], config: AnalysisConfig) -> list[Window]:
    windows = []
    interval_ns = round(config.interval * 1e9)
    for item in series:
        for offset in range(0, len(item.values) - config.window_size + 1, config.stride):
            if len(windows) >= config.max_windows:
                raise ValueError("Слишком много окон: увеличьте шаг окна или разделите захват.")
            start = item.start_ns + offset * interval_ns
            windows.append(
                Window(
                    item.source,
                    item.node,
                    item.segment,
                    start,
                    start + config.window_size * interval_ns,
                    item.values[offset : offset + config.window_size],
                )
            )
    return sorted(windows, key=lambda w: (w.start_ns, w.node, w.source))


def training_split(series: list[Series], config: AnalysisConfig, fraction=0.7):
    """Cut each capture segment in time BEFORE creating overlapping windows."""
    train_series, validation_series = [], []
    interval_ns = round(config.interval * 1e9)
    for item in series:
        cut = int(len(item.values) * fraction)
        train_series.append(
            Series(item.source, item.node, item.segment, item.start_ns, item.values[:cut])
        )
        validation_series.append(
            Series(
                item.source,
                item.node,
                item.segment,
                item.start_ns + cut * interval_ns,
                item.values[cut:],
            )
        )
    train = make_windows(train_series, config)
    validation = make_windows(validation_series, config)
    if len(train) < 2 or len(validation) < 2:
        raise ValueError(
            "Для обучения нужны минимум два обучающих и два валидационных окна. "
            "Добавьте более длинный нормальный захват или уменьшите окно/шаг времени."
        )
    return train, validation
