from __future__ import annotations

import argparse
import json

import numpy as np
import onnxruntime as ort
import torch

from poker_vision.data import PokerDataset
from poker_vision.evaluate import load_checkpoint
from poker_vision.metrics import decode_predictions
from poker_vision.utils import write_json


def _match_predictions(
    reference: tuple[torch.Tensor, torch.Tensor, torch.Tensor],
    candidate: tuple[torch.Tensor, torch.Tensor, torch.Tensor],
) -> tuple[int, int, float]:
    ref_boxes, _, ref_classes = reference
    cand_boxes, _, cand_classes = candidate
    used: set[int] = set()
    matched = class_correct = 0
    iou_sum = 0.0
    for ref_box, ref_class in zip(ref_boxes.tolist(), ref_classes.tolist(), strict=True):
        best_index = -1
        best_iou = 0.0
        for index, cand_box in enumerate(cand_boxes.tolist()):
            if index in used:
                continue
            iou = _iou(ref_box, cand_box)
            if iou > best_iou:
                best_iou = iou
                best_index = index
        if best_iou >= 0.5 and best_index >= 0:
            used.add(best_index)
            matched += 1
            class_correct += int(cand_classes[best_index].item() == ref_class)
            iou_sum += best_iou
    return matched, class_correct, iou_sum / max(matched, 1)


def _iou(
    first: list[float],
    second: list[float],
) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    area_first = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    area_second = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    return intersection / max(area_first + area_second - intersection, 1e-9)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--onnx", required=True)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--cfg")
    parser.add_argument("--output", required=True)
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--threshold", type=float, default=0.1)
    args = parser.parse_args()

    model, _ = load_checkpoint(args.checkpoint, args.cfg)
    model.eval()
    session = ort.InferenceSession(
        args.onnx,
        providers=["CPUExecutionProvider"],
    )
    dataset = PokerDataset(args.data_dir, "test", input_size=model.input_size)
    sample_count = min(args.samples, len(dataset))
    matched_total = class_correct_total = reference_total = candidate_total = 0
    iou_values = []
    max_abs = 0.0
    mean_abs = 0.0

    for index in range(sample_count):
        image, _, _ = dataset[index]
        tensor = image.unsqueeze(0)
        with torch.no_grad():
            torch_raw = model(tensor)
        onnx_raw = session.run(None, {"input": tensor.numpy()})[0]
        difference = np.abs(torch_raw.numpy() - onnx_raw)
        max_abs = max(max_abs, float(difference.max()))
        mean_abs += float(difference.mean())

        torch_decoded = decode_predictions(
            model.decode(torch_raw), args.threshold, iou_threshold=0.45
        )[0]
        onnx_decoded = decode_predictions(
            torch.from_numpy(model.decode(torch.from_numpy(onnx_raw)).numpy()),
            args.threshold,
            iou_threshold=0.45,
        )[0]
        matched, correct, mean_iou = _match_predictions(torch_decoded, onnx_decoded)
        matched_total += matched
        class_correct_total += correct
        reference_total += len(torch_decoded[0])
        candidate_total += len(onnx_decoded[0])
        if matched:
            iou_values.append(mean_iou)

    matched_class_agreement = class_correct_total / max(matched_total, 1)
    mean_matched_iou = float(np.mean(iou_values)) if iou_values else 0.0
    box_iou_deviation = 1.0 - mean_matched_iou
    payload = {
        "samples": sample_count,
        "raw_max_abs_difference": max_abs,
        "raw_mean_abs_difference": mean_abs / max(sample_count, 1),
        "reference_detections": reference_total,
        "candidate_detections": candidate_total,
        "matched_detections": matched_total,
        "matched_fraction": matched_total / max(reference_total, candidate_total, 1),
        "matched_class_agreement": matched_class_agreement,
        "mean_matched_iou": mean_matched_iou,
        "box_iou_deviation": box_iou_deviation,
        "class_agreement_at_least_0_99": matched_class_agreement >= 0.99,
        "box_iou_deviation_at_most_0_01": box_iou_deviation <= 0.01,
        "threshold": args.threshold,
    }
    write_json(args.output, payload)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
