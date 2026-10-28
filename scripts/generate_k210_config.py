from __future__ import annotations

import argparse
import json
from pathlib import Path

from poker_vision.classes import load_catalog


def tuple_lines(values: list[str], indent: str = "    ") -> str:
    return "\n".join(f"{indent}{value}," for value in values)


def render_holdout_layout(path: str | None) -> tuple[str, str]:
    if path is None:
        return "()", "()"
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    slot_ids = [str(slot["id"]) for slot in payload["slots"]]
    slot_labels = [str(slot["label"]) for slot in payload["slots"]]
    scenes = payload["scenes"]
    if len(slot_ids) != 4 or len(set(slot_ids)) != 4:
        raise ValueError("holdout layout must define four unique slots")
    if len(scenes) != 26:
        raise ValueError("holdout layout must define exactly 26 scenes")

    rendered_scenes = []
    for expected_id, scene in enumerate(scenes, start=1):
        if int(scene["id"]) != expected_id:
            raise ValueError("holdout scene ids must be contiguous from 1")
        cards = scene["cards"]
        if set(cards) != set(slot_ids):
            raise ValueError(f"scene {expected_id} does not match the slot schema")
        codes = [str(cards[slot_id]) for slot_id in slot_ids]
        if len(codes) != len(set(codes)):
            raise ValueError(f"scene {expected_id} repeats a card")
        rendered_scenes.append("    (" + ", ".join(f'"{code}"' for code in codes) + "),")

    labels = "(\n" + "\n".join(f'    "{label}",' for label in slot_labels) + "\n)"
    layout = "(\n" + "\n".join(rendered_scenes) + "\n)"
    return labels, layout


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--classes", required=True)
    parser.add_argument("--anchors", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--input-width", type=int, default=160)
    parser.add_argument("--input-height", type=int, default=120)
    parser.add_argument("--box-threshold", type=float, default=0.25)
    parser.add_argument("--identity-threshold", type=float, default=0.20)
    parser.add_argument(
        "--run-mode",
        choices=["SMOKE", "BENCHMARK", "STABILITY", "HOLDOUT", "DEMO"],
        default="DEMO",
    )
    parser.add_argument("--holdout-scenes")
    args = parser.parse_args()

    catalog = load_catalog(args.classes)
    anchors_payload = json.loads(Path(args.anchors).read_text(encoding="utf-8"))
    anchors = [f"{float(value):.8f}" for pair in anchors_payload for value in pair]
    codes = [f'"{code}"' for code in catalog.names]
    holdout_labels, holdout_layout = render_holdout_layout(args.holdout_scenes)
    payload = f"""# Generated deployment configuration.
# Rebuild with scripts/generate_k210_config.py.
MODEL_PATH = "/sd/models/yolov2_k210.kmodel"
INPUT_WIDTH = {args.input_width}
INPUT_HEIGHT = {args.input_height}
NUM_CLASSES = {catalog.num_classes}
NUM_ANCHORS = 5
ANCHORS = (
{tuple_lines(anchors)}
)
BOX_THRESHOLD = {args.box_threshold:.4f}
IDENTITY_THRESHOLD = {args.identity_threshold:.4f}
NMS_THRESHOLD = 0.45
RUN_MODE = "{args.run_mode}"
START_DELAY_MS = 10000
SMOKE_FRAMES = 30
BENCHMARK_WARMUP_FRAMES = 30
BENCHMARK_RUNS = 3
BENCHMARK_FRAMES = 100
STABILITY_SECONDS = 300
HOLDOUT_SCENES = 26
HOLDOUT_WAIT_MS = 10000
HOLDOUT_CAPTURE_FRAMES = 5
HOLDOUT_OUTPUT_DIR = "/sd/holdout"
TARGET_FPS = 5.0
HOLDOUT_TARGET_ACCURACY = 0.70
HOLDOUT_TARGET_COVERAGE = 0.70
HOLDOUT_SLOT_LABELS = {holdout_labels}
HOLDOUT_LAYOUT = {holdout_layout}
CLASS_CODES = (
{tuple_lines(codes)}
)
"""
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload, encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
