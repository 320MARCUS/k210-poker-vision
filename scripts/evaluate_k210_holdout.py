from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PVJSON_PREFIX = "PVJSON "


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            if stripped.startswith("{"):
                record = json.loads(stripped)
                if isinstance(record.get("pvjson"), dict):
                    record = record["pvjson"]
            elif PVJSON_PREFIX in stripped:
                record = json.loads(stripped.split(PVJSON_PREFIX, 1)[1])
            else:
                continue
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid PVJSON at line {line_number}: {exc}") from exc
        if not isinstance(record, dict) or "event" not in record:
            continue
        events.append(record)
    return events


def validate_holdout_schema(
    payload: dict[str, Any], class_codes: list[str]
) -> tuple[list[dict[str, Any]], dict[int, dict[str, str]]]:
    camera_size = payload.get("camera_size")
    if (
        not isinstance(camera_size, list)
        or len(camera_size) != 2
        or not all(isinstance(value, int) and value > 0 for value in camera_size)
    ):
        raise ValueError("holdout schema must define a positive camera_size")
    slots = payload.get("slots")
    scenes = payload.get("scenes")
    if not isinstance(slots, list) or len(slots) != 4:
        raise ValueError("holdout schema must contain four spatial slots")
    slot_ids = [str(slot.get("id")) for slot in slots]
    if len(set(slot_ids)) != 4:
        raise ValueError("holdout slot ids must be unique")
    for slot in slots:
        center = slot.get("center")
        if (
            not isinstance(center, list)
            or len(center) != 2
            or not all(isinstance(value, (int, float)) and 0 <= value <= 1 for value in center)
        ):
            raise ValueError(f"invalid center for slot {slot.get('id')}")

    if not isinstance(scenes, list) or len(scenes) != 26:
        raise ValueError("holdout schema must contain exactly 26 scenes")
    expected_codes = set(class_codes)
    occurrences: Counter[str] = Counter()
    scene_map: dict[int, dict[str, str]] = {}
    for expected_id, scene in enumerate(scenes, start=1):
        if int(scene.get("id", -1)) != expected_id:
            raise ValueError("holdout scene ids must be contiguous from 1")
        cards = scene.get("cards")
        if not isinstance(cards, dict) or set(cards) != set(slot_ids):
            raise ValueError(f"scene {expected_id} does not match the slot schema")
        normalized = {slot_id: str(cards[slot_id]) for slot_id in slot_ids}
        if len(set(normalized.values())) != 4:
            raise ValueError(f"scene {expected_id} repeats a card")
        unknown = set(normalized.values()) - expected_codes
        if unknown:
            raise ValueError(f"scene {expected_id} contains unknown classes: {sorted(unknown)}")
        occurrences.update(normalized.values())
        scene_map[expected_id] = normalized

    wrong_counts = {code: count for code, count in occurrences.items() if count != 2}
    if set(occurrences) != expected_codes or wrong_counts:
        raise ValueError(
            "holdout must contain every class exactly twice; "
            f"invalid counts: {dict(sorted(wrong_counts.items()))}"
        )
    return slots, scene_map


def _bbox_center(bbox: Any, camera_size: list[int]) -> tuple[float, float] | None:
    if not isinstance(bbox, list) or len(bbox) != 4:
        return None
    if not all(isinstance(value, (int, float)) for value in bbox):
        return None
    x1, y1, x2, y2 = (float(value) for value in bbox)
    if x2 <= x1 or y2 <= y1:
        return None
    width, height = camera_size
    return ((x1 + x2) / (2.0 * width), (y1 + y2) / (2.0 * height))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evaluate_events(
    events: list[dict[str, Any]],
    schema: dict[str, Any],
    class_codes: list[str],
    image_dir: Path | None,
    accuracy_target: float = 0.70,
    coverage_target: float = 0.70,
) -> dict[str, Any]:
    slots, scene_map = validate_holdout_schema(schema, class_codes)
    camera_size = [int(value) for value in schema["camera_size"]]
    scene_events: dict[int, dict[str, Any]] = {}
    duplicate_scenes: list[int] = []
    for event in events:
        if event.get("event") != "holdout_scene":
            continue
        scene_id = int(event.get("scene", 0))
        if scene_id in scene_events:
            duplicate_scenes.append(scene_id)
        else:
            scene_events[scene_id] = event

    summaries = [
        event
        for event in events
        if event.get("event") == "summary" and event.get("phase") == "holdout"
    ]
    known_codes = set(class_codes)
    per_class = {
        code: {"instances": 0, "covered": 0, "correct": 0, "wrong": 0, "missed": 0}
        for code in class_codes
    }
    failures: list[dict[str, Any]] = []
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    total_instances = 0
    detected_instances = 0
    covered_instances = 0
    correct_instances = 0
    unknown_instances = 0
    missing_instances = 0
    image_records: list[dict[str, Any]] = []

    for scene_id in sorted(scene_map):
        event = scene_events.get(scene_id)
        detections = event.get("detections", []) if event else []
        if not isinstance(detections, list):
            detections = []
        assigned: dict[str, list[dict[str, Any]]] = {str(slot["id"]): [] for slot in slots}
        for detection in detections:
            center = _bbox_center(detection.get("bbox"), camera_size)
            if center is None:
                continue
            nearest = min(
                slots,
                key=lambda slot: math.dist(center, tuple(slot["center"])),
            )
            assigned[str(nearest["id"])].append(detection)

        image_path = image_dir / f"scene_{scene_id:02d}.jpg" if image_dir else None
        image_records.append(
            {
                "scene": scene_id,
                "path": str(image_path) if image_path else None,
                "sha256": _sha256(image_path) if image_path and image_path.is_file() else None,
                "present": bool(image_path and image_path.is_file()),
            }
        )

        for slot in slots:
            slot_id = str(slot["id"])
            expected = scene_map[scene_id][slot_id]
            total_instances += 1
            per_class[expected]["instances"] += 1
            candidates = assigned[slot_id]
            if not candidates:
                missing_instances += 1
                per_class[expected]["missed"] += 1
                failures.append(
                    {
                        "scene": scene_id,
                        "slot": slot_id,
                        "expected": expected,
                        "predicted": None,
                        "score": None,
                        "reason": "missing_detection",
                    }
                )
                continue

            prediction = max(candidates, key=lambda item: float(item.get("score", 0.0)))
            predicted = str(prediction.get("label", "unknown"))
            detected_instances += 1
            if predicted not in known_codes:
                unknown_instances += 1
                failures.append(
                    {
                        "scene": scene_id,
                        "slot": slot_id,
                        "expected": expected,
                        "predicted": predicted,
                        "score": prediction.get("score"),
                        "bbox": prediction.get("bbox"),
                        "reason": "unknown_identity",
                    }
                )
                continue

            covered_instances += 1
            per_class[expected]["covered"] += 1
            confusion[expected][predicted] += 1
            if predicted == expected:
                correct_instances += 1
                per_class[expected]["correct"] += 1
            else:
                per_class[expected]["wrong"] += 1
                failures.append(
                    {
                        "scene": scene_id,
                        "slot": slot_id,
                        "expected": expected,
                        "predicted": predicted,
                        "score": prediction.get("score"),
                        "bbox": prediction.get("bbox"),
                        "reason": "wrong_identity",
                    }
                )

    for metrics in per_class.values():
        metrics["coverage"] = round(metrics["covered"] / max(metrics["instances"], 1), 6)
        metrics["accuracy"] = round(metrics["correct"] / max(metrics["covered"], 1), 6)

    accuracy = correct_instances / max(covered_instances, 1)
    coverage = covered_instances / total_instances
    box_coverage = detected_instances / total_instances
    complete_scenes = len(scene_events)
    summary_complete = bool(summaries and summaries[-1].get("status") == "complete")
    images_complete = all(item["present"] for item in image_records)
    evidence_complete = (
        complete_scenes == 26 and summary_complete and images_complete and not duplicate_scenes
    )
    metrics_pass = accuracy >= accuracy_target and coverage >= coverage_target
    if not evidence_complete:
        evidence_status = "incomplete"
    elif metrics_pass:
        evidence_status = "passed"
    else:
        evidence_status = "degraded"

    return {
        "status": evidence_status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": {
            "alignment": "Each bbox center is assigned to the nearest fixed quadrant center.",
            "identity_accuracy": "Correct known identities / covered known identities.",
            "coverage": "Correct-slot known identities / 104 ground-truth instances.",
            "box_coverage": "Correct-slot detections of any confidence / 104 instances.",
            "unknown_policy": "unknown lowers coverage and is never counted as a correct identity.",
        },
        "thresholds": {
            "box": 0.25,
            "identity": 0.20,
            "nms": 0.45,
            "accuracy_target": accuracy_target,
            "coverage_target": coverage_target,
        },
        "totals": {
            "instances": total_instances,
            "detected_instances": detected_instances,
            "covered_instances": covered_instances,
            "correct_instances": correct_instances,
            "unknown_instances": unknown_instances,
            "missing_instances": missing_instances,
        },
        "metrics": {
            "identity_accuracy": round(accuracy, 6),
            "identity_coverage": round(coverage, 6),
            "box_coverage": round(box_coverage, 6),
        },
        "evidence": {
            "complete": evidence_complete,
            "scene_events": complete_scenes,
            "summary_complete": summary_complete,
            "images_complete": images_complete,
            "duplicate_scenes": duplicate_scenes,
            "high_accuracy_claim_allowed": evidence_complete and metrics_pass,
        },
        "per_class": per_class,
        "confusion_matrix": {
            actual: dict(sorted(predictions.items())) for actual, predictions in confusion.items()
        },
        "failures": failures,
        "images": image_records,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--scenes", default=ROOT / "configs" / "k210_holdout_scenes.json")
    parser.add_argument("--classes", default=ROOT / "configs" / "classes.json")
    parser.add_argument("--images", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--accuracy-target", type=float, default=0.70)
    parser.add_argument("--coverage-target", type=float, default=0.70)
    args = parser.parse_args()

    class_payload = load_json(args.classes)
    class_codes = [str(item["code"]) for item in class_payload["classes"]]
    result = evaluate_events(
        events=load_events(args.events),
        schema=load_json(args.scenes),
        class_codes=class_codes,
        image_dir=args.images,
        accuracy_target=args.accuracy_target,
        coverage_target=args.coverage_target,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["metrics"], ensure_ascii=False))


if __name__ == "__main__":
    main()
