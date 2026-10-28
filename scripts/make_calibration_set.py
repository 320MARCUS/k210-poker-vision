from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from poker_vision.data import read_yolo_label
from poker_vision.utils import ensure_dir, write_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--per-class", type=int, default=2)
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    output = ensure_dir(args.output)
    selected: dict[str, set[int]] = {}
    chosen: list[Path] = []
    image_dir = data_dir / "train" / "images"
    label_dir = data_dir / "train" / "labels"
    for label_path in sorted(label_dir.glob("*.txt")):
        image_path = image_dir / f"{label_path.stem}.jpg"
        if not image_path.exists():
            continue
        class_ids = {box.class_id for box in read_yolo_label(label_path)}
        needed = {
            class_id
            for class_id in class_ids
            if len(selected.get(class_id, set())) < args.per_class
        }
        if not needed:
            continue
        chosen.append(image_path)
        for class_id in needed:
            selected.setdefault(class_id, set()).add(len(chosen))

    for image_path in chosen:
        shutil.copy2(image_path, output / image_path.name)
    write_json(
        output / "calibration_manifest.json",
        {
            "images": len(chosen),
            "per_class": args.per_class,
            "class_samples": {
                str(class_id): len(indices) for class_id, indices in sorted(selected.items())
            },
        },
    )
    print(json.dumps({"images": len(chosen)}, indent=2))


if __name__ == "__main__":
    main()
