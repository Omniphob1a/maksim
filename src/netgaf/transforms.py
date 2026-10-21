from dataclasses import dataclass

import numpy as np


@dataclass
class FixedScaler:
    lower: np.ndarray
    upper: np.ndarray

    @classmethod
    def fit(cls, values: np.ndarray):
        values = np.asarray(values, dtype=np.float64).reshape(-1, 3)
        if len(values) == 0 or not np.isfinite(values).all() or (values < 0).any():
            raise ValueError("Обучающие признаки должны быть конечными и неотрицательными.")
        return cls(values.min(axis=0), values.max(axis=0))

    def transform(self, values):
        values = np.asarray(values, dtype=np.float64)
        span = self.upper - self.lower
        # A constant training feature still has to reveal changes at inference.
        span = np.where(span > 0, span, np.maximum(np.abs(self.upper), 1.0))
        scaled = (values - self.lower) / span
        low = (values < self.lower).sum(axis=-2)
        high = (values > self.upper).sum(axis=-2)
        excess = np.maximum(np.maximum(-scaled, scaled - 1), 0).max(axis=-2)
        return np.clip(scaled, 0, 1).astype(np.float32), low, high, excess

    def to_dict(self):
        return {"lower": self.lower.tolist(), "upper": self.upper.tolist()}


def gaf(values: np.ndarray, method: str = "gasf") -> np.ndarray:
    """(..., time, channels) in [0,1] → (..., channels, time, time)."""
    values = np.asarray(values)
    values = values.astype(np.float64 if values.dtype == np.float64 else np.float32, copy=False)
    if values.ndim < 2 or not np.isfinite(values).all():
        raise ValueError("Ожидается конечный массив временных рядов.")
    if (values < 0).any() or (values > 1).any():
        raise ValueError("Перед GAF нужна фиксированная нормализация в [0, 1].")
    x = np.swapaxes(values, -1, -2)
    sine = np.sqrt(np.maximum(0, 1 - x * x))
    if method == "gasf":
        return x[..., :, None] * x[..., None, :] - sine[..., :, None] * sine[..., None, :]
    if method == "gadf":
        return sine[..., :, None] * x[..., None, :] - x[..., :, None] * sine[..., None, :]
    raise ValueError("Неизвестное преобразование GAF.")
