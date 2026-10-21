"""Small CPU convolutional autoencoder; model files never contain Python pickles."""

import io
import json
import os
import platform
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from zipfile import ZipFile

import numpy as np
import torch
from torch import nn

from .capture import CaptureData, check_cancelled
from .config import FEATURES, AnalysisConfig
from .transforms import FixedScaler, gaf
from .windows import Window, make_windows, training_split


class Autoencoder(nn.Module):
    def __init__(self):
        super().__init__()
        self.layers = nn.Sequential(
            nn.Conv2d(3, 8, 4, 2, 1),
            nn.ReLU(),
            nn.Conv2d(8, 16, 4, 2, 1),
            nn.ReLU(),
            nn.Conv2d(16, 8, 4, 2, 1),
            nn.ReLU(),
            nn.ConvTranspose2d(8, 16, 4, 2, 1),
            nn.ReLU(),
            nn.ConvTranspose2d(16, 8, 4, 2, 1),
            nn.ReLU(),
            nn.ConvTranspose2d(8, 3, 4, 2, 1),
            nn.Tanh(),
        )

    def forward(self, images):
        return self.layers(images)


@dataclass
class Detector:
    network: Autoencoder
    config: AnalysisConfig
    scaler: FixedScaler
    threshold: float
    metadata: dict


def _errors(network, raw, scaler, config, cancel=None):
    network.eval()
    errors = []
    with torch.inference_mode():
        for start in range(0, len(raw), 32):
            check_cancelled(cancel)
            normalized, *_ = scaler.transform(raw[start : start + 32])
            images = torch.from_numpy(gaf(normalized, config.representation))
            reconstructed = network(images)
            errors.extend((images - reconstructed).square().mean((1, 2, 3)).numpy().tolist())
    return np.array(errors)


def train_detector(
    captures: list[CaptureData],
    config: AnalysisConfig,
    epochs: int = 20,
    quantile: float = 0.99,
    seed: int = 42,
    progress: Callable[[str], None] = lambda _: None,
    cancel: Callable[[], bool] | None = None,
) -> Detector:
    if not 1 <= epochs <= 1000 or not 0.9 <= quantile <= 1:
        raise ValueError("Неверное число эпох или квантиль порога.")
    if not captures:
        raise ValueError("Выберите нормальные захваты для обучения.")
    all_series = [series for capture in captures for series in capture.series]
    train, validation = training_split(all_series, config)
    if len(train) + len(validation) > config.max_windows:
        raise ValueError("Слишком много обучающих окон. Разделите данные.")
    raw_train = np.stack([w.values for w in train])
    raw_validation = np.stack([w.values for w in validation])
    scaler = FixedScaler.fit(raw_train)
    torch.set_num_threads(min(2, os.cpu_count() or 1))
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    generator = np.random.default_rng(seed)
    network = Autoencoder()
    optimizer = torch.optim.Adam(network.parameters(), lr=0.001)
    history = []
    started = time.perf_counter()
    for epoch in range(epochs):
        network.train()
        indices = generator.permutation(len(raw_train))
        losses = []
        for start in range(0, len(indices), 16):
            check_cancelled(cancel)
            normalized, *_ = scaler.transform(raw_train[indices[start : start + 16]])
            images = torch.from_numpy(gaf(normalized, config.representation))
            optimizer.zero_grad(set_to_none=True)
            reconstructed = network(images)
            loss = (reconstructed - images).square().mean()
            if not torch.isfinite(loss):
                raise ValueError("Обучение остановлено: неконечное значение ошибки.")
            loss.backward()
            optimizer.step()
            losses.append((float(loss.detach()), len(images)))
        train_loss = sum(value * size for value, size in losses) / len(raw_train)
        val_loss = float(_errors(network, raw_validation, scaler, config, cancel).mean())
        history.append({"epoch": epoch + 1, "train_mse": train_loss, "validation_mse": val_loss})
        progress(
            f"Эпоха {epoch + 1}/{epochs}: MSE обучения {train_loss:.5f}, валидации {val_loss:.5f}"
        )
    errors = _errors(network, raw_validation, scaler, config, cancel)
    threshold = max(float(np.quantile(errors, quantile, method="higher")), 1e-12)
    metadata = {
        "format_version": 1,
        "architecture": "conv-autoencoder-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "features": list(FEATURES),
        "training_sources": [Path(c.source).name for c in captures],
        "train_windows": len(train),
        "validation_windows": len(validation),
        "split": "70/30 chronological per capture segment, before windowing",
        "threshold_quantile": quantile,
        "seed": seed,
        "epochs": epochs,
        "learning_rate": 0.001,
        "history": history,
        "duration_seconds": time.perf_counter() - started,
        "python_version": platform.python_version(),
        "torch_version": torch.__version__,
        "numpy_version": np.__version__,
    }
    return Detector(network.eval(), config, scaler, threshold, metadata)


def save_detector(detector: Detector, path: str | Path):
    path = Path(path)
    metadata = dict(detector.metadata)
    metadata.update(
        config=detector.config.to_dict(),
        scaler=detector.scaler.to_dict(),
        threshold=detector.threshold,
    )
    weights = io.BytesIO()
    np.savez_compressed(
        weights,
        **{
            key: value.detach().cpu().numpy()
            for key, value in detector.network.state_dict().items()
        },
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as output, ZipFile(output, "w") as archive:
            archive.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
            archive.writestr("weights.npz", weights.getvalue())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_detector(path: str | Path) -> Detector:
    try:
        with ZipFile(path) as archive:
            if set(archive.namelist()) != {"metadata.json", "weights.npz"}:
                raise ValueError("Неизвестная структура файла модели.")
            if any(i.file_size > 8_000_000 for i in archive.infolist()):
                raise ValueError("Превышен допустимый размер файла модели.")
            metadata = json.loads(archive.read("metadata.json"))
            if metadata["format_version"] != 1 or metadata["architecture"] != "conv-autoencoder-v1":
                raise ValueError("Несовместимая версия модели.")
            config = AnalysisConfig(**metadata["config"])
            scaler = FixedScaler(
                np.array(metadata["scaler"]["lower"], dtype=np.float64),
                np.array(metadata["scaler"]["upper"], dtype=np.float64),
            )
            if (
                scaler.lower.shape != (3,)
                or scaler.upper.shape != (3,)
                or not np.isfinite([scaler.lower, scaler.upper]).all()
                or (scaler.lower < 0).any()
                or (scaler.upper < scaler.lower).any()
            ):
                raise ValueError("Повреждены параметры нормализации.")
            threshold = float(metadata["threshold"])
            if not np.isfinite(threshold) or threshold <= 0:
                raise ValueError("Неверный порог модели.")
            network = Autoencoder()
            with np.load(io.BytesIO(archive.read("weights.npz")), allow_pickle=False) as weights:
                if any(i.file_size > 2_000_000 for i in weights.zip.infolist()):
                    raise ValueError("Превышен размер массива весов.")
                reference = network.state_dict()
                if set(weights.files) != set(reference):
                    raise ValueError("Неверный набор весов модели.")
                state = {}
                for key, target in reference.items():
                    value = weights[key]
                    if value.shape != tuple(target.shape) or value.dtype != np.float32:
                        raise ValueError("Неверная размерность или тип весов.")
                    if not np.isfinite(value).all():
                        raise ValueError("Неконечные веса модели.")
                    state[key] = torch.from_numpy(value.copy())
                network.load_state_dict(state, strict=True)
            return Detector(network.eval(), config, scaler, threshold, metadata)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Не удалось открыть модель: {exc}") from exc


@dataclass
class Result:
    window: Window
    score: float
    threshold: float
    below: list[int]
    above: list[int]
    excess: list[float]

    @property
    def anomalous(self):
        return self.score > self.threshold

    def to_dict(self):
        return {
            "source": Path(self.window.source).name,
            "node": self.window.node,
            "segment": self.window.segment,
            "start_ns": self.window.start_ns,
            "end_ns": self.window.end_ns,
            "score": self.score,
            "threshold": self.threshold,
            "anomalous": self.anomalous,
            "below_training_range": self.below,
            "above_training_range": self.above,
            "max_normalized_excess": self.excess,
        }


def analyze(
    capture: CaptureData,
    detector: Detector,
    progress: Callable[[str], None] = lambda _: None,
    cancel: Callable[[], bool] | None = None,
) -> list[Result]:
    windows = make_windows(capture.series, detector.config)
    if not windows:
        raise ValueError("В файле нет полных окон.")
    results = []
    torch.set_num_threads(min(2, os.cpu_count() or 1))
    for start in range(0, len(windows), 32):
        check_cancelled(cancel)
        batch = windows[start : start + 32]
        raw = np.stack([w.values for w in batch])
        scores = _errors(detector.network, raw, detector.scaler, detector.config, cancel)
        _, low, high, excess = detector.scaler.transform(raw)
        results.extend(
            Result(w, float(score), detector.threshold, lo.tolist(), hi.tolist(), ex.tolist())
            for w, score, lo, hi, ex in zip(batch, scores, low, high, excess)
        )
        progress(f"Проанализировано окон: {len(results)}/{len(windows)}")
    return results


def reconstruct(detector: Detector, window: Window):
    normalized, *_ = detector.scaler.transform(window.values)
    image = gaf(normalized, detector.config.representation)
    with torch.inference_mode():
        restored = detector.network(torch.from_numpy(image[None]))[0].numpy()
    return image, restored
