from __future__ import annotations

import csv
import json
import math
import random
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import torch
from PIL import Image, ImageEnhance
from torch.utils.data import DataLoader, Dataset

from .classes import ClassCatalog
from .utils import ensure_dir, sha256_file, write_json

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
SPLITS = ("train", "valid", "test")


@dataclass(frozen=True)
class Box:
    class_id: int
    cx: float
    cy: float
    width: float
    height: float


def read_yolo_label(path: Path) -> list[Box]:
    boxes: list[Box] = []
    text = path.read_text(encoding="utf-8-sig")
    for line_number, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        fields = line.split()
        if len(fields) != 5:
            raise ValueError(f"{path}:{line_number}: expected 5 fields, got {len(fields)}")
        try:
            class_id = int(fields[0])
            cx, cy, width, height = (float(value) for value in fields[1:])
        except ValueError as exc:
            raise ValueError(f"{path}:{line_number}: non-numeric field") from exc
        if not all(0.0 <= value <= 1.0 for value in (cx, cy, width, height)):
            raise ValueError(f"{path}:{line_number}: label outside [0, 1]")
        if width <= 0.0 or height <= 0.0:
            raise ValueError(f"{path}:{line_number}: zero-area box")
        boxes.append(Box(class_id, cx, cy, width, height))
    return boxes


def write_yolo_label(path: Path, boxes: Iterable[Box]) -> None:
    lines = [
        f"{box.class_id} {box.cx:.8f} {box.cy:.8f} {box.width:.8f} {box.height:.8f}"
        for box in boxes
    ]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _image_files(directory: Path) -> list[Path]:
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def audit_and_prepare_dataset(
    source: str | Path,
    output: str | Path,
    catalog: ClassCatalog,
) -> dict:
    """Validate source data, apply the reviewed class map, and write a clean copy."""
    source = Path(source)
    output = Path(output)
    report: dict = {
        "source": str(source.resolve()),
        "output": str(output.resolve()),
        "catalog_classes": catalog.num_classes,
        "dataset": {
            "url": catalog.dataset_url,
            "license": catalog.dataset_license,
        },
        "splits": {},
        "quarantined": [],
        "errors": [],
    }
    all_image_hashes: dict[str, list[str]] = {}

    for split in SPLITS:
        image_dir = source / split / "images"
        label_dir = source / split / "labels"
        if not image_dir.is_dir() or not label_dir.is_dir():
            report["errors"].append(f"missing split directories: {split}")
            continue

        images = _image_files(image_dir)
        image_stems = {path.stem for path in images}
        labels = sorted(label_dir.glob("*.txt"))
        label_stems = {path.stem for path in labels}
        missing_labels = sorted(image_stems - label_stems)
        orphan_labels = sorted(label_stems - image_stems)
        if missing_labels:
            report["errors"].append(f"{split}: {len(missing_labels)} images without labels")
        if orphan_labels:
            report["errors"].append(f"{split}: {len(orphan_labels)} labels without images")

        out_images = ensure_dir(output / split / "images")
        out_labels = ensure_dir(output / split / "labels")
        class_counts = [0] * catalog.num_classes
        box_count = 0
        quarantined_split = 0

        for image_path in images:
            label_path = label_dir / f"{image_path.stem}.txt"
            if not label_path.exists():
                continue
            source_boxes = read_yolo_label(label_path)
            mapped: list[Box] = []
            for box in source_boxes:
                try:
                    canonical_id = catalog.source_to_canonical(box.class_id)
                except ValueError as exc:
                    report["errors"].append(f"{label_path}: {exc}")
                    continue
                if canonical_id is None:
                    quarantined_split += 1
                    report["quarantined"].append(
                        {
                            "split": split,
                            "image": str(image_path.relative_to(source)),
                            "source_class_id": box.class_id,
                            "reason": "unresolved one-off source annotation",
                            "box": [box.cx, box.cy, box.width, box.height],
                        }
                    )
                    continue
                mapped.append(Box(canonical_id, box.cx, box.cy, box.width, box.height))
                class_counts[canonical_id] += 1
                box_count += 1

            shutil.copy2(image_path, out_images / image_path.name)
            write_yolo_label(out_labels / label_path.name, mapped)
            digest = sha256_file(image_path)
            relative = str(image_path.relative_to(source))
            all_image_hashes.setdefault(digest, []).append(relative)

        report["splits"][split] = {
            "images": len(images),
            "labels": len(labels),
            "boxes": box_count,
            "quarantined_boxes": quarantined_split,
            "missing_labels": missing_labels,
            "orphan_labels": orphan_labels,
            "class_counts": class_counts,
        }

    duplicates = {digest: paths for digest, paths in all_image_hashes.items() if len(paths) > 1}
    report["duplicate_image_groups"] = duplicates
    if duplicates:
        report["errors"].append(f"{len(duplicates)} duplicate image groups")

    with (output / "class_distribution.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["class_id", "code", *SPLITS, "total"])
        for item in catalog.classes:
            values = [
                report["splits"]
                .get(split, {})
                .get("class_counts", [0] * catalog.num_classes)[item.id]
                for split in SPLITS
            ]
            writer.writerow([item.id, item.code, *values, sum(values)])

    with (output / "manifest.jsonl").open("w", encoding="utf-8") as handle:
        for digest, paths in sorted(all_image_hashes.items()):
            for relative in paths:
                handle.write(
                    json.dumps(
                        {"sha256": digest, "path": relative},
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    report["total_boxes"] = sum(item.get("boxes", 0) for item in report["splits"].values())
    report["total_images"] = sum(item.get("images", 0) for item in report["splits"].values())
    report["status"] = "ok" if not report["errors"] else "error"
    write_json(output / "audit.json", report)
    return report


class PokerDataset(Dataset):
    def __init__(
        self,
        root: str | Path,
        split: str,
        input_size: int | tuple[int, int] = 215,
        augment: bool = False,
    ) -> None:
        self.root = Path(root)
        self.split = split
        self.input_size = (
            (int(input_size), int(input_size))
            if isinstance(input_size, int)
            else (int(input_size[0]), int(input_size[1]))
        )
        self.augment = augment
        self.image_dir = self.root / split / "images"
        self.label_dir = self.root / split / "labels"
        self.images = _image_files(self.image_dir)
        if not self.images:
            raise RuntimeError(f"no images found in {self.image_dir}")

    def __len__(self) -> int:
        return len(self.images)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor, str]:
        image_path = self.images[index]
        label_path = self.label_dir / f"{image_path.stem}.txt"
        image = Image.open(image_path).convert("RGB")
        boxes = read_yolo_label(label_path)

        if self.augment:
            image, boxes = self._augment(image, boxes)

        image = image.resize(self.input_size, Image.Resampling.BILINEAR)
        image_array = np.asarray(image, dtype=np.float32).transpose(2, 0, 1) / 255.0
        target_array = (
            np.asarray(
                [[box.cx, box.cy, box.width, box.height, box.class_id] for box in boxes],
                dtype=np.float32,
            )
            if boxes
            else np.zeros((0, 5), dtype=np.float32)
        )
        return (
            torch.from_numpy(image_array),
            torch.from_numpy(target_array),
            image_path.name,
        )

    def _augment(self, image: Image.Image, boxes: Sequence[Box]) -> tuple[Image.Image, list[Box]]:
        augmented = list(boxes)
        if random.random() < 0.5:
            image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            augmented = [
                Box(box.class_id, 1.0 - box.cx, box.cy, box.width, box.height) for box in augmented
            ]
        if random.random() < 0.5:
            image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            augmented = [
                Box(box.class_id, box.cx, 1.0 - box.cy, box.width, box.height) for box in augmented
            ]
        if random.random() < 0.8:
            angle = random.uniform(-12.0, 12.0)
            scale = random.uniform(0.92, 1.08)
            translate_x = random.uniform(-0.04, 0.04)
            translate_y = random.uniform(-0.04, 0.04)
            image = _affine_image(image, angle, scale, translate_x, translate_y)
            augmented = [
                _transform_box(box, angle, scale, translate_x, translate_y) for box in augmented
            ]
            augmented = [
                box
                for box in augmented
                if 0.0 <= box.cx <= 1.0
                and 0.0 <= box.cy <= 1.0
                and box.width >= 0.03
                and box.height >= 0.03
            ]
        if random.random() < 0.8:
            image = ImageEnhance.Brightness(image).enhance(random.uniform(0.7, 1.3))
        if random.random() < 0.5:
            image = ImageEnhance.Contrast(image).enhance(random.uniform(0.8, 1.2))
        if random.random() < 0.4:
            image = ImageEnhance.Color(image).enhance(random.uniform(0.7, 1.3))
        return image, augmented


def _affine_image(
    image: Image.Image,
    angle_degrees: float,
    scale: float,
    translate_x: float,
    translate_y: float,
) -> Image.Image:
    radians = math.radians(angle_degrees)
    cosine = math.cos(radians) / scale
    sine = math.sin(radians) / scale
    center_x = (image.width - 1) / 2.0
    center_y = (image.height - 1) / 2.0
    shift_x = translate_x * image.width
    shift_y = translate_y * image.height
    matrix = (
        cosine,
        sine,
        center_x - cosine * center_x - sine * center_y - shift_x,
        -sine,
        cosine,
        center_y + sine * center_x - cosine * center_y - shift_y,
    )
    return image.transform(
        image.size,
        Image.Transform.AFFINE,
        matrix,
        resample=Image.Resampling.BILINEAR,
    )


def _transform_box(
    box: Box,
    angle_degrees: float,
    scale: float,
    translate_x: float,
    translate_y: float,
) -> Box:
    radians = math.radians(angle_degrees)
    cosine = math.cos(radians) * scale
    sine = math.sin(radians) * scale
    half_width = box.width / 2.0
    half_height = box.height / 2.0
    corners = [
        (-half_width, -half_height),
        (half_width, -half_height),
        (half_width, half_height),
        (-half_width, half_height),
    ]
    transformed = [
        (
            box.cx + translate_x + cosine * x - sine * y,
            box.cy + translate_y + sine * x + cosine * y,
        )
        for x, y in corners
    ]
    xs = [point[0] for point in transformed]
    ys = [point[1] for point in transformed]
    return Box(
        class_id=box.class_id,
        cx=(min(xs) + max(xs)) / 2.0,
        cy=(min(ys) + max(ys)) / 2.0,
        width=max(xs) - min(xs),
        height=max(ys) - min(ys),
    )


def collate_batch(
    batch: Sequence[tuple[torch.Tensor, torch.Tensor, str]],
) -> tuple[torch.Tensor, list[torch.Tensor], list[str]]:
    images = torch.stack([sample[0] for sample in batch])
    targets = [sample[1] for sample in batch]
    names = [sample[2] for sample in batch]
    return images, targets, names


def make_loader(
    dataset: PokerDataset,
    batch_size: int,
    shuffle: bool,
    num_workers: int,
) -> DataLoader:
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=num_workers,
        collate_fn=collate_batch,
        pin_memory=torch.cuda.is_available(),
        persistent_workers=num_workers > 0,
    )
