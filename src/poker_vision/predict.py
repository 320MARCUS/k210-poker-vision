from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw

from .classes import ClassCatalog
from .evaluate import load_checkpoint
from .metrics import decode_predictions
from .utils import ensure_dir, select_device, write_json

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def predict_command(args, catalog: ClassCatalog) -> list[dict]:
    device = select_device(args.device)
    model, checkpoint = load_checkpoint(args.checkpoint, args.cfg)
    model.to(device).eval()
    threshold = float(args.threshold or checkpoint.get("confidence_threshold", 0.25))
    identity_threshold = float(
        args.identity_threshold if args.identity_threshold is not None else threshold
    )
    output_dir = ensure_dir(args.output_dir)
    sources = (
        sorted(
            path
            for path in Path(args.source).iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        )
        if Path(args.source).is_dir()
        else [Path(args.source)]
    )

    all_payloads: list[dict] = []
    for source in sources:
        image = Image.open(source).convert("RGB")
        resized = image.resize(model.input_shape, Image.Resampling.BILINEAR)
        tensor = (
            torch.from_numpy(np.asarray(resized, dtype="float32").transpose(2, 0, 1) / 255.0)
            .unsqueeze(0)
            .to(device)
        )
        with torch.no_grad():
            decoded = model.decode(model(tensor))
            prediction = decode_predictions(decoded, threshold, iou_threshold=0.45)[0]
        boxes, scores, class_ids = prediction
        draw = ImageDraw.Draw(image)
        detections = []
        width, height = image.size
        for box, score, class_id in zip(
            boxes.cpu().tolist(),
            scores.cpu().tolist(),
            class_ids.cpu().tolist(),
            strict=True,
        ):
            card = catalog.by_id(int(class_id))
            xyxy = [
                int(box[0] * width),
                int(box[1] * height),
                int(box[2] * width),
                int(box[3] * height),
            ]
            confident = score >= identity_threshold
            display_label = card.code if confident else "unknown"
            color = (0, 220, 80) if confident else (255, 190, 0)
            draw.rectangle(xyxy, outline=color, width=3)
            draw.text(
                (xyxy[0] + 2, max(0, xyxy[1] - 14)),
                f"{display_label} {score:.2f}",
                fill=color,
            )
            detections.append(
                {
                    "label": display_label,
                    "predicted_label": card.code,
                    "score": float(score),
                    "bbox": [float(value) for value in box],
                    "bbox_pixels": xyxy,
                }
            )
        output_image = output_dir / f"{source.stem}_prediction.jpg"
        image.save(output_image, quality=92)
        payload = {
            "source": str(source.resolve()),
            "image": str(output_image.resolve()),
            "threshold": threshold,
            "identity_threshold": identity_threshold,
            "detections": detections,
        }
        all_payloads.append(payload)
    write_json(output_dir / "predictions.json", all_payloads)
    return all_payloads
