import torch

from poker_vision.metrics import (
    Detection,
    GroundTruth,
    box_iou,
    calculate_ap,
    decode_predictions,
)


def test_box_iou_and_perfect_ap() -> None:
    boxes = torch.tensor([[0.1, 0.1, 0.3, 0.3]])
    iou = box_iou(boxes, boxes)
    assert torch.allclose(iou, torch.ones((1, 1)))
    detections = [Detection(0, 2, 0.9, (0.1, 0.1, 0.3, 0.3))]
    truth = [GroundTruth(0, 2, (0.1, 0.1, 0.3, 0.3))]
    mean_ap, per_class = calculate_ap(detections, truth, 3, 0.5)
    assert mean_ap == 1.0
    assert per_class[2] == 1.0


def test_decode_filters_empty_output() -> None:
    decoded = torch.zeros(1, 5, 7, 7, 57)
    decoded[..., 4] = 0.0
    boxes, scores, classes = decode_predictions(decoded, 0.5)[0]
    assert boxes.shape == (0, 4)
    assert scores.numel() == 0
    assert classes.numel() == 0
