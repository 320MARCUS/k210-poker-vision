from pathlib import Path

import torch

from poker_vision.model import YOLOv2Tiny

ROOT = Path(__file__).resolve().parents[1]


def test_model_contract() -> None:
    model = YOLOv2Tiny(ROOT / "configs" / "yolov2-tiny-52-215.cfg")
    raw = model(torch.zeros(1, 3, 215, 215))
    assert tuple(raw.shape) == (1, 285, 7, 7)
    decoded = model.decode(raw)
    assert tuple(decoded.shape) == (1, 5, 7, 7, 57)


def test_320_model_contract() -> None:
    model = YOLOv2Tiny(ROOT / "configs" / "yolov2-tiny-52-320.cfg")
    raw = model(torch.zeros(1, 3, 320, 320))
    assert tuple(raw.shape) == (1, 285, 10, 10)
    assert tuple(model.decode(raw).shape) == (1, 5, 10, 10, 57)


def test_narrow_k210_model_contract() -> None:
    model = YOLOv2Tiny(ROOT / "configs" / "yolov2-tiny-52-320-c512-256.cfg")
    raw = model(torch.zeros(1, 3, 320, 320))
    assert tuple(raw.shape) == (1, 285, 10, 10)
    assert tuple(model.decode(raw).shape) == (1, 5, 10, 10, 57)
