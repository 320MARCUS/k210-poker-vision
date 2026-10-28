from __future__ import annotations

from pathlib import Path

import torch

from .classes import ClassCatalog
from .evaluate import load_checkpoint
from .utils import runtime_metadata, sha256_file, write_json


def export_command(args, catalog: ClassCatalog) -> dict:
    model, checkpoint = load_checkpoint(args.checkpoint, args.cfg)
    model.eval()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dummy = torch.zeros(1, 3, model.input_height, model.input_width)
    with torch.no_grad():
        reference_output = model(dummy)
    torch.onnx.export(
        model,
        dummy,
        output_path,
        export_params=True,
        opset_version=args.opset,
        do_constant_folding=True,
        input_names=["input"],
        output_names=["raw_output"],
        dynamo=False,
    )
    card = {
        "format": "onnx",
        "input_shape": [1, 3, model.input_height, model.input_width],
        "output_shape": list(reference_output.shape),
        "num_classes": model.num_classes,
        "num_anchors": model.num_anchors,
        "anchors": model.anchors.cpu().tolist(),
        "class_codes": catalog.names,
        "box_threshold": float(args.threshold),
        "identity_threshold": float(
            args.identity_threshold if args.identity_threshold is not None else args.threshold
        ),
        "nms_iou": 0.45,
        "checkpoint_epoch": checkpoint.get("epoch"),
        "onnx_sha256": sha256_file(output_path),
        "runtime": runtime_metadata(),
    }
    write_json(output_path.with_suffix(".model_card.json"), card)
    return card
