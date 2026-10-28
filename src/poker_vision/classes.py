from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class CardClass:
    id: int
    code: str
    display: str
    rank: str
    suit: str


@dataclass(frozen=True)
class ClassCatalog:
    classes: tuple[CardClass, ...]
    source_id_to_code: dict[int, str | None]
    quarantined_source_ids: tuple[int, ...]
    dataset_url: str
    dataset_license: str

    @property
    def num_classes(self) -> int:
        return len(self.classes)

    @property
    def code_to_id(self) -> dict[str, int]:
        return {item.code: item.id for item in self.classes}

    @property
    def names(self) -> list[str]:
        return [item.code for item in self.classes]

    def by_id(self, class_id: int) -> CardClass:
        if class_id < 0 or class_id >= len(self.classes):
            raise IndexError(f"class_id outside catalog: {class_id}")
        return self.classes[class_id]

    def source_to_canonical(self, source_id: int) -> int | None:
        if source_id not in self.source_id_to_code:
            raise ValueError(f"unknown source class id: {source_id}")
        code = self.source_id_to_code[source_id]
        if code is None:
            return None
        return self.code_to_id[code]


def load_catalog(path: str | Path) -> ClassCatalog:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    classes = tuple(
        CardClass(
            id=int(item["id"]),
            code=str(item["code"]),
            display=str(item["display"]),
            rank=str(item["rank"]),
            suit=str(item["suit"]),
        )
        for item in payload["classes"]
    )
    ids = [item.id for item in classes]
    if ids != list(range(len(classes))):
        raise ValueError("class ids must be contiguous and zero-based")
    codes = [item.code for item in classes]
    if len(codes) != len(set(codes)):
        raise ValueError("class codes must be unique")
    source_map = {
        int(key): (None if value is None else str(value))
        for key, value in payload["source_id_to_code"].items()
    }
    return ClassCatalog(
        classes=classes,
        source_id_to_code=source_map,
        quarantined_source_ids=tuple(int(x) for x in payload["quarantined_source_ids"]),
        dataset_url=str(payload["dataset"]["url"]),
        dataset_license=str(payload["dataset"]["license"]),
    )


def make_catalog_payload(
    classes: Iterable[CardClass],
    source_id_to_code: dict[int, str | None],
) -> dict:
    return {
        "version": 1,
        "classes": [
            {
                "id": item.id,
                "code": item.code,
                "display": item.display,
                "rank": item.rank,
                "suit": item.suit,
            }
            for item in classes
        ],
        "source_id_to_code": {str(key): value for key, value in sorted(source_id_to_code.items())},
        "quarantined_source_ids": [
            key for key, value in sorted(source_id_to_code.items()) if value is None
        ],
        "dataset": {
            "name": "poker cards",
            "project": "poker-cards-cxcvz",
            "url": "https://universe.roboflow.com/object-detection/poker-cards-cxcvz",
            "license": "CC BY 4.0",
        },
    }
