from pathlib import Path

from PIL import Image

from poker_vision.classes import load_catalog
from poker_vision.data import Box, _transform_box, audit_and_prepare_dataset

ROOT = Path(__file__).resolve().parents[1]


def test_audit_remaps_and_quarantines(tmp_path: Path) -> None:
    source = tmp_path / "source"
    colors = {"train": (10, 20, 30), "valid": (40, 50, 60), "test": (70, 80, 90)}
    for split, count in (("train", 1), ("valid", 1), ("test", 1)):
        image_dir = source / split / "images"
        label_dir = source / split / "labels"
        image_dir.mkdir(parents=True)
        label_dir.mkdir(parents=True)
        for index in range(count):
            Image.new("RGB", (32, 32), colors[split]).save(image_dir / f"{split}_{index}.jpg")
            labels = "0 0.5 0.5 0.2 0.2\n"
            if split == "train":
                labels += "19 0.7 0.7 0.1 0.1\n20 0.3 0.3 0.1 0.1\n"
            (label_dir / f"{split}_{index}.txt").write_text(labels, encoding="utf-8")

    catalog = load_catalog(ROOT / "configs" / "classes.json")
    report = audit_and_prepare_dataset(source, tmp_path / "prepared", catalog)
    assert report["status"] == "ok"
    assert report["total_images"] == 3
    assert report["splits"]["train"]["boxes"] == 2
    assert report["splits"]["train"]["quarantined_boxes"] == 1
    prepared = tmp_path / "prepared" / "train" / "labels" / "train_0.txt"
    ids = [int(line.split()[0]) for line in prepared.read_text().splitlines()]
    assert ids == [catalog.code_to_id["10H"], catalog.code_to_id["10D"]]


def test_affine_box_transform_keeps_positive_dimensions() -> None:
    transformed = _transform_box(
        Box(3, 0.5, 0.5, 0.2, 0.3),
        angle_degrees=11.0,
        scale=1.05,
        translate_x=0.02,
        translate_y=-0.01,
    )
    assert transformed.class_id == 3
    assert transformed.width > 0.0
    assert transformed.height > 0.0
    assert 0.0 < transformed.cx < 1.0
    assert 0.0 < transformed.cy < 1.0
