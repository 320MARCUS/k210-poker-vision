from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from poker_vision.data import read_yolo_label
from poker_vision.evaluate import load_checkpoint
from poker_vision.metrics import decode_predictions, evaluate_metrics
from poker_vision.utils import select_device


def _target_tensor(data_dir: Path, stem: str) -> torch.Tensor:
    label_path = data_dir / "test" / "labels" / f"{stem}.txt"
    boxes = read_yolo_label(label_path)
    return torch.tensor(
        [[box.cx, box.cy, box.width, box.height, box.class_id] for box in boxes],
        dtype=torch.float32,
    )


def _metrics(predictions, targets, num_classes: int, thresholds: dict) -> dict:
    return evaluate_metrics(
        predictions,
        targets,
        num_classes,
        report_threshold=thresholds["box"],
    ) | {
        "identity_operating_point": evaluate_metrics(
            predictions,
            targets,
            num_classes,
            report_threshold=thresholds["identity"],
        )
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--cfg", required=True)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--emulator-outputs", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--box-threshold", type=float, default=0.25)
    parser.add_argument("--identity-threshold", type=float, default=0.2)
    args = parser.parse_args()

    model, _ = load_checkpoint(args.checkpoint, args.cfg)
    device = select_device("auto")
    model.to(device).eval()
    data_dir = Path(args.data_dir)
    emulator_dir = Path(args.emulator_outputs)
    bins = sorted(emulator_dir.glob("*.bin"))
    thresholds = {"box": args.box_threshold, "identity": args.identity_threshold}

    float_predictions = []
    emulated_predictions = []
    targets = []
    with torch.no_grad():
        for binary in bins:
            stem = binary.stem
            image_path = data_dir / "test" / "images" / f"{stem}.jpg"
            image = (
                Image.open(image_path).convert("RGB").resize((model.input_size, model.input_size))
            )
            sample = (
                torch.from_numpy(np.asarray(image, dtype=np.float32).transpose(2, 0, 1))
                .unsqueeze(0)
                .to(device)
                / 255.0
            )
            float_raw = model(sample)
            float_predictions.extend(decode_predictions(model.decode(float_raw), 0.001, 0.45))
            emulated_raw = torch.from_numpy(
                np.fromfile(binary, dtype=np.float32).reshape(
                    1, 285, model.input_size // 32, model.input_size // 32
                )
            ).to(device)
            emulated_predictions.extend(decode_predictions(model.decode(emulated_raw), 0.001, 0.45))
            targets.append(_target_tensor(data_dir, stem))

    float_metrics = _metrics(float_predictions, targets, model.num_classes, thresholds)
    emulated_metrics = _metrics(emulated_predictions, targets, model.num_classes, thresholds)
    payload = {
        "samples": len(bins),
        "thresholds": thresholds,
        "float": float_metrics,
        "kmodel_emulator": emulated_metrics,
        "delta": {
            "mAP50": emulated_metrics["mAP50"] - float_metrics["mAP50"],
            "mAP50_95": emulated_metrics["mAP50_95"] - float_metrics["mAP50_95"],
            "identity_accuracy": (
                emulated_metrics["identity_operating_point"]["identity_accuracy"]
                - float_metrics["identity_operating_point"]["identity_accuracy"]
            ),
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["delta"], indent=2))


if __name__ == "__main__":
    main()
