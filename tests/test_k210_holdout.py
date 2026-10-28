import copy
import json
from pathlib import Path

import pytest

from scripts.evaluate_k210_holdout import (
    evaluate_events,
    load_events,
    validate_holdout_schema,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "configs" / "k210_holdout_scenes.json"
CLASS_PATH = ROOT / "configs" / "classes.json"
SLOT_BOXES = {
    "top_left": [10, 30, 150, 130],
    "top_right": [170, 30, 310, 130],
    "bottom_left": [10, 136, 150, 236],
    "bottom_right": [170, 136, 310, 236],
}


def _fixtures():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    classes = json.loads(CLASS_PATH.read_text(encoding="utf-8"))
    class_codes = [item["code"] for item in classes["classes"]]
    return schema, class_codes


def _perfect_events(schema: dict) -> list[dict]:
    events = []
    for scene in schema["scenes"]:
        detections = [
            {
                "label": scene["cards"][slot["id"]],
                "score": 0.9,
                "bbox": SLOT_BOXES[slot["id"]],
            }
            for slot in schema["slots"]
        ]
        events.append(
            {
                "event": "holdout_scene",
                "phase": "holdout",
                "scene": scene["id"],
                "detections": detections,
            }
        )
    events.append({"event": "summary", "phase": "holdout", "status": "complete"})
    return events


def _write_images(image_dir: Path) -> None:
    image_dir.mkdir()
    for scene_id in range(1, 27):
        (image_dir / f"scene_{scene_id:02d}.jpg").write_bytes(f"scene-{scene_id}".encode())


def test_holdout_schema_has_each_card_twice() -> None:
    schema, class_codes = _fixtures()
    slots, scene_map = validate_holdout_schema(schema, class_codes)
    assert len(slots) == 4
    assert len(scene_map) == 26
    counts = {}
    for cards in scene_map.values():
        for code in cards.values():
            counts[code] = counts.get(code, 0) + 1
    assert set(counts.values()) == {2}
    assert len(counts) == 52


def test_holdout_rejects_duplicate_card_in_scene() -> None:
    schema, class_codes = _fixtures()
    broken = copy.deepcopy(schema)
    broken["scenes"][0]["cards"]["top_right"] = broken["scenes"][0]["cards"]["top_left"]
    with pytest.raises(ValueError, match="repeats a card"):
        validate_holdout_schema(broken, class_codes)


def test_perfect_complete_holdout_passes(tmp_path: Path) -> None:
    schema, class_codes = _fixtures()
    image_dir = tmp_path / "images"
    _write_images(image_dir)
    result = evaluate_events(_perfect_events(schema), schema, class_codes, image_dir)
    assert result["status"] == "passed"
    assert result["metrics"]["identity_accuracy"] == 1.0
    assert result["metrics"]["identity_coverage"] == 1.0
    assert result["metrics"]["box_coverage"] == 1.0
    assert result["evidence"]["high_accuracy_claim_allowed"] is True


def test_unknown_reduces_coverage_but_not_conditional_accuracy(tmp_path: Path) -> None:
    schema, class_codes = _fixtures()
    image_dir = tmp_path / "images"
    _write_images(image_dir)
    events = _perfect_events(schema)
    events[0]["detections"][0]["label"] = "unknown"
    result = evaluate_events(events, schema, class_codes, image_dir)
    assert result["totals"]["unknown_instances"] == 1
    assert result["metrics"]["identity_accuracy"] == 1.0
    assert result["metrics"]["identity_coverage"] == pytest.approx(103 / 104)
    assert result["metrics"]["box_coverage"] == 1.0


def test_missing_images_make_evidence_incomplete(tmp_path: Path) -> None:
    schema, class_codes = _fixtures()
    image_dir = tmp_path / "images"
    _write_images(image_dir)
    (image_dir / "scene_12.jpg").unlink()
    result = evaluate_events(_perfect_events(schema), schema, class_codes, image_dir)
    assert result["status"] == "incomplete"
    assert result["evidence"]["images_complete"] is False
    assert result["evidence"]["high_accuracy_claim_allowed"] is False


def test_load_events_accepts_raw_and_capture_jsonl(tmp_path: Path) -> None:
    log = tmp_path / "capture.jsonl"
    log.write_text(
        "\n".join(
            [
                '{"event":"phase","phase":"ready","captured_at_utc":"now"}',
                'noise before PVJSON {"event":"summary","phase":"holdout"}',
            ]
        ),
        encoding="utf-8",
    )
    events = load_events(log)
    assert [event["event"] for event in events] == ["phase", "summary"]
