from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from .data import PokerDataset


def _wh_iou(box: np.ndarray, clusters: np.ndarray) -> np.ndarray:
    intersection = np.minimum(box[0], clusters[:, 0]) * np.minimum(box[1], clusters[:, 1])
    union = box[0] * box[1] + clusters[:, 0] * clusters[:, 1] - intersection
    return intersection / np.clip(union, 1e-9, None)


def kmeans_anchors(
    boxes_wh: np.ndarray,
    num_anchors: int = 5,
    iterations: int = 30,
    seed: int = 42,
) -> np.ndarray:
    if boxes_wh.ndim != 2 or boxes_wh.shape[1] != 2:
        raise ValueError("boxes_wh must have shape [N, 2]")
    if len(boxes_wh) < num_anchors:
        raise ValueError("not enough boxes to estimate anchors")
    rng = np.random.default_rng(seed)
    clusters = boxes_wh[rng.choice(len(boxes_wh), num_anchors, replace=False)].copy()
    for _ in range(iterations):
        distances = 1.0 - _pairwise_iou(boxes_wh, clusters)
        assignments = distances.argmin(axis=1)
        updated = clusters.copy()
        for index in range(num_anchors):
            selected = boxes_wh[assignments == index]
            if len(selected):
                updated[index] = selected.mean(axis=0)
        if np.allclose(updated, clusters, atol=1e-6):
            break
        clusters = updated
    order = np.argsort(clusters[:, 0] * clusters[:, 1])
    return clusters[order]


def _pairwise_iou(boxes: np.ndarray, clusters: np.ndarray) -> np.ndarray:
    intersection = np.minimum(boxes[:, None, 0], clusters[None, :, 0]) * np.minimum(
        boxes[:, None, 1], clusters[None, :, 1]
    )
    box_area = boxes[:, 0] * boxes[:, 1]
    cluster_area = clusters[:, 0] * clusters[:, 1]
    union = box_area[:, None] + cluster_area[None, :] - intersection
    return intersection / np.clip(union, 1e-9, None)


def estimate_dataset_anchors(
    dataset_dir: str | Path,
    grid_width: int = 7,
    grid_height: int = 7,
    num_anchors: int = 5,
) -> list[tuple[float, float]]:
    dataset = PokerDataset(dataset_dir, "train", augment=False)
    widths_heights: list[tuple[float, float]] = []
    for index in range(len(dataset)):
        _, targets, _ = dataset[index]
        if len(targets):
            widths_heights.extend(
                (
                    float(row[2]) * grid_width,
                    float(row[3]) * grid_height,
                )
                for row in targets
            )
    anchors = kmeans_anchors(
        np.asarray(widths_heights, dtype=np.float32),
        num_anchors=num_anchors,
    )
    return [(float(width), float(height)) for width, height in anchors]


def set_model_anchors(model: torch.nn.Module, anchors: list[tuple[float, float]]) -> None:
    tensor = torch.tensor(anchors, dtype=torch.float32)
    model.anchors.copy_(tensor)
