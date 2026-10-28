from __future__ import annotations

import csv
import time
from pathlib import Path

import torch

from .classes import ClassCatalog
from .data import PokerDataset, make_loader
from .metrics import calibration_sweep, decode_predictions, evaluate_metrics
from .model import YOLOv2Tiny
from .utils import ensure_dir, runtime_metadata, select_device, sha256_file, write_json


def load_checkpoint(
    checkpoint_path: str | Path,
    cfg_path: str | Path | None = None,
) -> tuple[YOLOv2Tiny, dict]:
    checkpoint = torch.load(
        checkpoint_path,
        map_location="cpu",
        weights_only=False,
    )
    effective_cfg = cfg_path or checkpoint.get("cfg")
    if not effective_cfg:
        raise ValueError("cfg path missing from checkpoint and command line")
    model = YOLOv2Tiny(effective_cfg)
    model.load_state_dict(checkpoint["model_state_dict"])
    if checkpoint.get("anchors"):
        model.anchors.copy_(torch.tensor(checkpoint["anchors"], dtype=torch.float32))
    model.eval()
    return model, checkpoint


def run_inference(
    model: YOLOv2Tiny,
    data_dir: str | Path,
    split: str,
    batch_size: int,
    num_workers: int,
    device: torch.device,
    confidence_threshold: float,
) -> tuple[
    list[tuple[torch.Tensor, torch.Tensor, torch.Tensor]],
    list[torch.Tensor],
]:
    dataset = PokerDataset(data_dir, split, input_size=model.input_shape)
    loader = make_loader(dataset, batch_size, False, num_workers)
    predictions: list[tuple[torch.Tensor, torch.Tensor, torch.Tensor]] = []
    targets: list[torch.Tensor] = []
    model.to(device).eval()
    with torch.no_grad():
        for images, batch_targets, _ in loader:
            images = images.to(device, non_blocking=True)
            raw = model(images)
            decoded = model.decode(raw)
            predictions.extend(
                decode_predictions(
                    decoded,
                    confidence_threshold=confidence_threshold,
                )
            )
            targets.extend(target.cpu() for target in batch_targets)
    return predictions, targets


def evaluate_command(args, catalog: ClassCatalog) -> dict:
    device = select_device(args.device)
    model, checkpoint = load_checkpoint(args.checkpoint, args.cfg)
    predictions, targets = run_inference(
        model=model,
        data_dir=args.data_dir,
        split=args.split,
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        device=device,
        confidence_threshold=args.min_confidence,
    )
    if args.calibrate_threshold:
        if args.split != "valid":
            raise ValueError("threshold calibration must run on the validation split")
        sweep = calibration_sweep(predictions, targets, catalog.num_classes)
        selected_threshold = float(sweep["selected_box"]["threshold"])
        identity_threshold = float(sweep["selected_identity"]["threshold"])
    else:
        sweep = None
        selected_threshold = args.threshold
        identity_threshold = args.identity_threshold or selected_threshold

    metrics = evaluate_metrics(
        predictions,
        targets,
        catalog.num_classes,
        report_threshold=selected_threshold,
    )
    identity_metrics = evaluate_metrics(
        predictions,
        targets,
        catalog.num_classes,
        report_threshold=identity_threshold,
    )
    for item in metrics["per_class"]:
        item["code"] = catalog.by_id(item["class_id"]).code
    payload = {
        "dataset": {
            "name": "poker cards",
            "url": catalog.dataset_url,
            "license": catalog.dataset_license,
            "split": args.split,
        },
        "checkpoint": Path(args.checkpoint).name,
        "checkpoint_sha256": sha256_file(args.checkpoint),
        "checkpoint_epoch": checkpoint.get("epoch"),
        "model_input_size": model.input_size,
        "model_input_shape": list(model.input_shape),
        "num_classes": catalog.num_classes,
        "threshold": selected_threshold,
        "identity_threshold": identity_threshold,
        "nms_iou": 0.45,
        "runtime": runtime_metadata(),
        "desktop_benchmark": benchmark_model(
            model,
            args.data_dir,
            device,
            warmup=10,
            iterations=50,
        ),
        "metrics": metrics,
        "identity_operating_point": identity_metrics,
    }
    if sweep:
        payload["calibration"] = sweep

    output_dir = ensure_dir(args.output_dir)
    write_json(output_dir / "metrics.json", payload)
    with (output_dir / "per_class_metrics.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["class_id", "code", "ground_truth", "ap50"])
        for item in metrics["per_class"]:
            writer.writerow(
                [
                    item["class_id"],
                    item["code"],
                    item["ground_truth"],
                    "" if item["ap50"] is None else f"{item['ap50']:.6f}",
                ]
            )
    return payload


def benchmark_model(
    model: YOLOv2Tiny,
    data_dir: str | Path,
    device: torch.device,
    warmup: int,
    iterations: int,
) -> dict:
    dataset = PokerDataset(data_dir, "test", input_size=model.input_shape)
    image, _, _ = dataset[0]
    tensor = image.unsqueeze(0).to(device)
    model.to(device).eval()
    with torch.no_grad():
        for _ in range(warmup):
            model(tensor)
        if device.type == "cuda":
            torch.cuda.synchronize()
        started = time.perf_counter()
        for _ in range(iterations):
            model(tensor)
        if device.type == "cuda":
            torch.cuda.synchronize()
        elapsed = time.perf_counter() - started
    latency_ms = elapsed * 1000.0 / max(iterations, 1)
    return {
        "device": str(device),
        "warmup": warmup,
        "iterations": iterations,
        "latency_ms": latency_ms,
        "fps": 1000.0 / max(latency_ms, 1e-9),
    }
