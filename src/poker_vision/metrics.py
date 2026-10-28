from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch


@dataclass(frozen=True)
class Detection:
    image_index: int
    class_id: int
    score: float
    box: tuple[float, float, float, float]


@dataclass(frozen=True)
class GroundTruth:
    image_index: int
    class_id: int
    box: tuple[float, float, float, float]


def xywh_to_xyxy(boxes: torch.Tensor) -> torch.Tensor:
    cx, cy, width, height = boxes.unbind(dim=-1)
    return torch.stack(
        [
            cx - width / 2.0,
            cy - height / 2.0,
            cx + width / 2.0,
            cy + height / 2.0,
        ],
        dim=-1,
    )


def box_iou(boxes_a: torch.Tensor, boxes_b: torch.Tensor) -> torch.Tensor:
    if boxes_a.numel() == 0 or boxes_b.numel() == 0:
        return torch.zeros(
            (len(boxes_a), len(boxes_b)),
            dtype=boxes_a.dtype,
            device=boxes_a.device,
        )
    top_left = torch.maximum(boxes_a[:, None, :2], boxes_b[None, :, :2])
    bottom_right = torch.minimum(boxes_a[:, None, 2:], boxes_b[None, :, 2:])
    dimensions = (bottom_right - top_left).clamp_min(0.0)
    intersection = dimensions[..., 0] * dimensions[..., 1]
    area_a = (boxes_a[:, 2] - boxes_a[:, 0]).clamp_min(0.0) * (
        boxes_a[:, 3] - boxes_a[:, 1]
    ).clamp_min(0.0)
    area_b = (boxes_b[:, 2] - boxes_b[:, 0]).clamp_min(0.0) * (
        boxes_b[:, 3] - boxes_b[:, 1]
    ).clamp_min(0.0)
    union = area_a[:, None] + area_b[None, :] - intersection
    return intersection / union.clamp_min(1e-9)


def _nms(boxes: torch.Tensor, scores: torch.Tensor, iou_threshold: float) -> torch.Tensor:
    if boxes.numel() == 0:
        return torch.empty((0,), dtype=torch.long, device=boxes.device)
    order = scores.argsort(descending=True)
    keep: list[torch.Tensor] = []
    while order.numel():
        index = order[0]
        keep.append(index)
        if order.numel() == 1:
            break
        ious = box_iou(boxes[index].unsqueeze(0), boxes[order[1:]])[0]
        order = order[1:][ious <= iou_threshold]
    return torch.stack(keep)


def decode_predictions(
    decoded: torch.Tensor,
    confidence_threshold: float,
    iou_threshold: float = 0.45,
) -> list[tuple[torch.Tensor, torch.Tensor, torch.Tensor]]:
    """Convert [A,H,W,5+C] tensors to per-image boxes, scores and class ids."""
    results: list[tuple[torch.Tensor, torch.Tensor, torch.Tensor]] = []
    for image in decoded:
        objectness = image[..., 4]
        class_probs, class_ids = image[..., 5:].max(dim=-1)
        scores = objectness * class_probs
        selected = scores > confidence_threshold
        boxes = xywh_to_xyxy(image[..., :4][selected]).clamp(0.0, 1.0)
        selected_scores = scores[selected]
        selected_classes = class_ids[selected]

        keep_parts: list[torch.Tensor] = []
        for class_id in selected_classes.unique():
            class_mask = selected_classes == class_id
            local_keep = _nms(
                boxes[class_mask],
                selected_scores[class_mask],
                iou_threshold,
            )
            source_indices = class_mask.nonzero(as_tuple=False).flatten()
            keep_parts.append(source_indices[local_keep])
        if keep_parts:
            keep = torch.cat(keep_parts)
            if keep.numel() > 1:
                keep = keep[selected_scores[keep].argsort(descending=True)]
            results.append((boxes[keep], selected_scores[keep], selected_classes[keep]))
        else:
            results.append(
                (
                    torch.empty((0, 4), device=image.device),
                    torch.empty((0,), device=image.device),
                    torch.empty((0,), dtype=torch.long, device=image.device),
                )
            )
    return results


def collect_detections(
    predictions: list[tuple[torch.Tensor, torch.Tensor, torch.Tensor]],
) -> list[Detection]:
    output: list[Detection] = []
    for image_index, (boxes, scores, class_ids) in enumerate(predictions):
        for box, score, class_id in zip(
            boxes.cpu().tolist(),
            scores.cpu().tolist(),
            class_ids.cpu().tolist(),
            strict=True,
        ):
            output.append(
                Detection(
                    image_index=image_index,
                    class_id=int(class_id),
                    score=float(score),
                    box=tuple(float(value) for value in box),
                )
            )
    return output


def calculate_ap(
    detections: list[Detection],
    ground_truth: list[GroundTruth],
    num_classes: int,
    iou_threshold: float,
) -> tuple[float, dict[int, float]]:
    per_class: dict[int, float] = {}
    gt_by_image_class: dict[tuple[int, int], list[GroundTruth]] = {}
    for item in ground_truth:
        gt_by_image_class.setdefault((item.image_index, item.class_id), []).append(item)
    for class_id in range(num_classes):
        class_gt_count = sum(1 for item in ground_truth if item.class_id == class_id)
        if class_gt_count == 0:
            continue
        class_detections = sorted(
            (item for item in detections if item.class_id == class_id),
            key=lambda item: item.score,
            reverse=True,
        )
        used: set[int] = set()
        true_positive: list[int] = []
        false_positive: list[int] = []
        for detection in class_detections:
            candidates = gt_by_image_class.get((detection.image_index, detection.class_id), [])
            best_index = -1
            best_iou = 0.0
            for index, target in enumerate(candidates):
                key = id(target)
                if key in used:
                    continue
                iou = _manual_iou(detection.box, target.box)
                if iou > best_iou:
                    best_iou = iou
                    best_index = index
            if best_iou >= iou_threshold and best_index >= 0:
                used.add(id(candidates[best_index]))
                true_positive.append(1)
                false_positive.append(0)
            else:
                true_positive.append(0)
                false_positive.append(1)
        if not true_positive:
            per_class[class_id] = 0.0
            continue
        tp = np.cumsum(true_positive)
        fp = np.cumsum(false_positive)
        recall = tp / max(class_gt_count, 1)
        precision = tp / np.maximum(tp + fp, 1)
        ap = 0.0
        for threshold in np.linspace(0.0, 1.0, 101):
            candidates = precision[recall >= threshold]
            ap += float(candidates.max()) if candidates.size else 0.0
        per_class[class_id] = ap / 101.0
    mean_ap = float(np.mean(list(per_class.values()))) if per_class else 0.0
    return mean_ap, per_class


def evaluate_metrics(
    predictions: list[tuple[torch.Tensor, torch.Tensor, torch.Tensor]],
    targets: list[torch.Tensor],
    num_classes: int,
    report_threshold: float,
) -> dict:
    detections_all = collect_detections(predictions)
    ground_truth = _ground_truth(targets)
    ap50, ap50_per_class = calculate_ap(detections_all, ground_truth, num_classes, 0.5)
    ap_values = [
        calculate_ap(detections_all, ground_truth, num_classes, threshold)[0]
        for threshold in np.arange(0.5, 1.0, 0.05)
    ]
    selected = [item for item in detections_all if item.score >= report_threshold]
    true_positive = false_positive = 0
    matched_ground_truth: set[int] = set()
    for detection in selected:
        candidates = [
            (index, item)
            for index, item in enumerate(ground_truth)
            if item.image_index == detection.image_index and item.class_id == detection.class_id
        ]
        best_index = -1
        best_iou = 0.0
        for index, item in candidates:
            if index in matched_ground_truth:
                continue
            iou = _manual_iou(detection.box, item.box)
            if iou > best_iou:
                best_iou = iou
                best_index = index
        if best_iou >= 0.5 and best_index >= 0:
            matched_ground_truth.add(best_index)
            true_positive += 1
        else:
            false_positive += 1

    correct_identity = 0
    matched_identity = 0
    for ground_truth_index, target in enumerate(ground_truth):
        same_image = [item for item in selected if item.image_index == target.image_index]
        if not same_image:
            continue
        best = max(same_image, key=lambda item: _manual_iou(item.box, target.box))
        if _manual_iou(best.box, target.box) >= 0.5:
            matched_identity += 1
            correct_identity += int(best.class_id == target.class_id)

    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(len(ground_truth), 1)
    identity_accuracy = correct_identity / max(matched_identity, 1)
    classes = []
    for class_id in range(num_classes):
        classes.append(
            {
                "class_id": class_id,
                "ap50": ap50_per_class.get(class_id),
                "ground_truth": sum(1 for item in ground_truth if item.class_id == class_id),
            }
        )
    return {
        "mAP50": ap50,
        "mAP50_95": float(np.mean(ap_values)),
        "precision": precision,
        "recall": recall,
        "identity_accuracy": identity_accuracy,
        "matched_identity_boxes": matched_identity,
        "identity_coverage": matched_identity / max(len(ground_truth), 1),
        "ground_truth_boxes": len(ground_truth),
        "report_threshold": report_threshold,
        "per_class": classes,
    }


def calibration_sweep(
    predictions: list[tuple[torch.Tensor, torch.Tensor, torch.Tensor]],
    targets: list[torch.Tensor],
    num_classes: int,
) -> dict:
    rows = []
    for threshold in np.arange(0.05, 0.96, 0.05):
        metrics = evaluate_metrics(
            predictions, targets, num_classes, report_threshold=float(threshold)
        )
        f1 = (
            2
            * metrics["precision"]
            * metrics["recall"]
            / max(metrics["precision"] + metrics["recall"], 1e-9)
        )
        rows.append(
            {
                "threshold": float(threshold),
                "precision": metrics["precision"],
                "recall": metrics["recall"],
                "f1": f1,
                "identity_accuracy": metrics["identity_accuracy"],
                "identity_coverage": metrics["identity_coverage"],
            }
        )
    selected_box = max(
        rows,
        key=lambda row: (row["f1"], row["identity_accuracy"], -row["threshold"]),
    )
    eligible_identity = [
        row for row in rows if row["identity_accuracy"] >= 0.70 and row["identity_coverage"] >= 0.05
    ]
    if eligible_identity:
        selected_identity = min(eligible_identity, key=lambda row: row["threshold"])
    else:
        selected_identity = max(
            rows,
            key=lambda row: (
                row["identity_accuracy"],
                row["identity_coverage"],
                -row["threshold"],
            ),
        )
    return {
        "selected_box": selected_box,
        "selected_identity": selected_identity,
        "rows": rows,
    }


def _ground_truth(targets: list[torch.Tensor]) -> list[GroundTruth]:
    output: list[GroundTruth] = []
    for image_index, target in enumerate(targets):
        for row in target.cpu().tolist():
            cx, cy, width, height, class_id = row
            output.append(
                GroundTruth(
                    image_index=image_index,
                    class_id=int(class_id),
                    box=(
                        cx - width / 2,
                        cy - height / 2,
                        cx + width / 2,
                        cy + height / 2,
                    ),
                )
            )
    return output


def _manual_iou(
    box_a: tuple[float, float, float, float],
    box_b: tuple[float, float, float, float],
) -> float:
    left = max(box_a[0], box_b[0])
    top = max(box_a[1], box_b[1])
    right = min(box_a[2], box_b[2])
    bottom = min(box_a[3], box_b[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    area_a = max(0.0, box_a[2] - box_a[0]) * max(0.0, box_a[3] - box_a[1])
    area_b = max(0.0, box_b[2] - box_b[0]) * max(0.0, box_b[3] - box_b[1])
    return intersection / max(area_a + area_b - intersection, 1e-9)
