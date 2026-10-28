from __future__ import annotations

import argparse
import json
from pathlib import Path

from poker_vision.utils import sha256_file, write_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--source", nargs="*", default=[])
    args = parser.parse_args()

    audit = json.loads(Path(args.audit).read_text(encoding="utf-8"))
    public = {
        "dataset": audit["dataset"],
        "catalog_classes": audit["catalog_classes"],
        "total_images": audit["total_images"],
        "total_boxes": audit["total_boxes"],
        "quarantined": audit["quarantined"],
        "duplicate_image_groups": len(audit["duplicate_image_groups"]),
        "splits": {
            split: {key: value for key, value in payload.items() if key != "class_counts"}
            for split, payload in audit["splits"].items()
        },
    }
    output_dir = Path(args.output_dir)
    write_json(output_dir / "dataset_audit.json", public)

    sources = {}
    for raw_path in args.source:
        path = Path(raw_path)
        if path.is_file():
            sources[path.name] = {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
    if sources:
        write_json(output_dir / "source_manifest.json", sources)
    print(output_dir)


if __name__ == "__main__":
    main()
