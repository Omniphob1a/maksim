import argparse
import json
import sys
from pathlib import Path

from .capture import read_capture
from .config import AnalysisConfig
from .demo import generate_demo
from .evaluation import evaluate_demo
from .model import analyze, load_detector, save_detector, train_detector
from .reports import export_csv, export_json


def main(argv=None):
    parser = argparse.ArgumentParser(description="NetGAF — анализ сетевых аномалий")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("gui", help="Открыть Desktop-приложение")
    demo = sub.add_parser("demo", help="Создать синтетические PCAP без отправки пакетов")
    demo.add_argument("directory", type=Path)
    train = sub.add_parser("train", help="Обучить модель на нормальных PCAP")
    train.add_argument("captures", nargs="+", type=Path)
    train.add_argument("--model", required=True, type=Path)
    train.add_argument("--epochs", type=int, default=20)
    train.add_argument("--interval", type=float, default=1)
    train.add_argument("--window", type=int, default=32)
    train.add_argument("--stride", type=int, default=16)
    train.add_argument("--direction", choices=["incoming", "outgoing"], default="outgoing")
    train.add_argument("--representation", choices=["gasf", "gadf"], default="gasf")
    train.add_argument("--quantile", type=float, default=0.99)
    detect = sub.add_parser("analyze", help="Проанализировать PCAP сохранённой моделью")
    detect.add_argument("capture", type=Path)
    detect.add_argument("--model", required=True, type=Path)
    detect.add_argument("--output", required=True, type=Path)
    evaluate = sub.add_parser("evaluate-demo", help="Проверить разные синтетические сценарии")
    evaluate.add_argument("directory", type=Path)
    evaluate.add_argument("--model", required=True, type=Path)
    evaluate.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "gui":
            from .gui import main as desktop

            return desktop()
        if args.command == "demo":
            print(
                json.dumps({k: str(v) for k, v in generate_demo(args.directory).items()}, indent=2)
            )
        elif args.command == "train":
            config = AnalysisConfig(
                interval=args.interval,
                window_size=args.window,
                stride=args.stride,
                direction=args.direction,
                representation=args.representation,
            )
            captures = [read_capture(path, config, print) for path in args.captures]
            detector = train_detector(captures, config, args.epochs, args.quantile, progress=print)
            save_detector(detector, args.model)
            print(f"Модель сохранена: {args.model}. Порог MSE: {detector.threshold:.6f}")
        elif args.command == "evaluate-demo":
            report = evaluate_demo(args.directory, load_detector(args.model), print)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
            )
            print(f"Демонстрационные результаты: {args.output}")
        else:
            detector = load_detector(args.model)
            capture = read_capture(args.capture, detector.config, print)
            results = analyze(capture, detector, print)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            if args.output.suffix.lower() == ".csv":
                export_csv(args.output, results)
            else:
                export_json(args.output, results, detector, capture.stats)
            print(f"Окон: {len(results)}, подозрительных: {sum(r.anomalous for r in results)}")
        return 0
    except (ValueError, OSError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
