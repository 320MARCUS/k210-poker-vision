from __future__ import annotations

import argparse
import json
from pathlib import Path

from .classes import load_catalog
from .data import audit_and_prepare_dataset
from .evaluate import evaluate_command
from .export import export_command
from .predict import predict_command
from .train import train_command
from .utils import sha256_file, write_json


def _catalog_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--classes",
        default="configs/classes.json",
        help="reviewed class catalog",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poker-vision")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit = subparsers.add_parser(
        "audit-data", help="validate and remap the published source dataset"
    )
    audit.add_argument("--source", required=True)
    audit.add_argument("--output", required=True)
    _catalog_arg(audit)

    train = subparsers.add_parser("train", help="train YOLOv2-tiny")
    train.add_argument("--data-dir", required=True)
    train.add_argument("--cfg", required=True)
    train.add_argument("--weights")
    train.add_argument(
        "--initialize-from",
        help="copy matching tensors from a checkpoint into a narrower model",
    )
    train.add_argument("--anchors")
    train.add_argument("--estimate-anchors", action="store_true")
    train.add_argument("--resume")
    train.add_argument("--reset-scheduler", action="store_true")
    train.add_argument("--output-dir", required=True)
    train.add_argument("--epochs", type=int, default=100)
    train.add_argument("--batch-size", type=int, default=32)
    train.add_argument("--lr", type=float, default=1e-3)
    train.add_argument("--weight-decay", type=float, default=5e-4)
    train.add_argument("--num-workers", type=int, default=0)
    train.add_argument("--early-stopping", type=int, default=15)
    train.add_argument("--seed", type=int, default=42)
    train.add_argument("--device", default="auto")

    evaluate = subparsers.add_parser("evaluate", help="evaluate mAP and identity")
    evaluate.add_argument("--checkpoint", required=True)
    evaluate.add_argument("--cfg")
    evaluate.add_argument("--data-dir", required=True)
    evaluate.add_argument("--output-dir", required=True)
    evaluate.add_argument("--split", choices=["valid", "test"], default="test")
    evaluate.add_argument("--threshold", type=float, default=0.25)
    evaluate.add_argument("--identity-threshold", type=float)
    evaluate.add_argument("--min-confidence", type=float, default=0.001)
    evaluate.add_argument("--calibrate-threshold", action="store_true")
    evaluate.add_argument("--batch-size", type=int, default=32)
    evaluate.add_argument("--num-workers", type=int, default=0)
    evaluate.add_argument("--device", default="auto")
    _catalog_arg(evaluate)

    predict = subparsers.add_parser("predict", help="run PC inference")
    predict.add_argument("--checkpoint", required=True)
    predict.add_argument("--cfg")
    predict.add_argument("--source", required=True)
    predict.add_argument("--output-dir", required=True)
    predict.add_argument("--threshold", type=float)
    predict.add_argument("--identity-threshold", type=float)
    predict.add_argument("--device", default="auto")
    _catalog_arg(predict)

    export = subparsers.add_parser("export", help="export a deployment ONNX file")
    export.add_argument("--checkpoint", required=True)
    export.add_argument("--cfg")
    export.add_argument("--output", required=True)
    export.add_argument("--threshold", type=float, default=0.25)
    export.add_argument("--identity-threshold", type=float)
    export.add_argument("--opset", type=int, default=12)
    _catalog_arg(export)

    checksum = subparsers.add_parser("checksums", help="write SHA-256 metadata for release assets")
    checksum.add_argument("--output", required=True)
    checksum.add_argument("files", nargs="+")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    catalog = None
    if getattr(args, "classes", None):
        catalog = load_catalog(args.classes)

    if args.command == "audit-data":
        report = audit_and_prepare_dataset(args.source, args.output, catalog)
        summary = {key: report[key] for key in ("status", "total_images", "total_boxes")}
        print(json.dumps(summary, indent=2))
        return 0 if report["status"] == "ok" else 1
    if args.command == "train":
        train_command(args)
        return 0
    if args.command == "evaluate":
        evaluate_command(args, catalog)
        return 0
    if args.command == "predict":
        predict_command(args, catalog)
        return 0
    if args.command == "export":
        export_command(args, catalog)
        return 0
    if args.command == "checksums":
        payload = {}
        for name in args.files:
            path = Path(name)
            payload[path.name] = {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        write_json(args.output, payload)
        return 0
    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
