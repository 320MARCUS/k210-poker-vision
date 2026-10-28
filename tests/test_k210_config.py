import json
import runpy
from pathlib import Path

from poker_vision.classes import load_catalog

ROOT = Path(__file__).resolve().parents[1]


def test_k210_config_matches_catalog() -> None:
    catalog = load_catalog(ROOT / "configs" / "classes.json")
    config = runpy.run_path(str(ROOT / "k210" / "config.py"))
    assert config["NUM_CLASSES"] == 52
    assert config["NUM_ANCHORS"] == 5
    assert config["INPUT_WIDTH"] == 160
    assert config["INPUT_HEIGHT"] == 120
    assert len(config["ANCHORS"]) == 10
    assert list(config["CLASS_CODES"]) == catalog.names
    assert config["MODEL_PATH"] == "/sd/models/yolov2_k210.kmodel"
    assert config["BOX_THRESHOLD"] == 0.25
    assert config["IDENTITY_THRESHOLD"] == 0.20
    assert config["NMS_THRESHOLD"] == 0.45
    assert config["RUN_MODE"] in {"SMOKE", "BENCHMARK", "STABILITY", "HOLDOUT", "DEMO"}
    assert config["START_DELAY_MS"] == 10_000
    assert config["BENCHMARK_RUNS"] == 3
    assert config["BENCHMARK_FRAMES"] == 100
    assert config["STABILITY_SECONDS"] == 300
    assert config["HOLDOUT_SCENES"] == 26
    assert config["HOLDOUT_CAPTURE_FRAMES"] == 5


def test_k210_holdout_layout_matches_schema() -> None:
    payload = json.loads(
        (ROOT / "configs" / "k210_holdout_scenes.json").read_text(encoding="utf-8")
    )
    config = runpy.run_path(str(ROOT / "k210" / "config.py"))
    slot_ids = [slot["id"] for slot in payload["slots"]]
    expected = [
        tuple(scene["cards"][slot_id] for slot_id in slot_ids) for scene in payload["scenes"]
    ]
    assert len(config["HOLDOUT_LAYOUT"]) == 26
    assert config["HOLDOUT_LAYOUT"] == tuple(expected)
    assert config["HOLDOUT_SLOT_LABELS"] == tuple(slot["label"] for slot in payload["slots"])


def test_k210_launcher_and_protocol_contract() -> None:
    launcher = (ROOT / "k210" / "main.py").read_text(encoding="utf-8")
    application = (ROOT / "k210" / "poker_app.py").read_text(encoding="utf-8")
    assert 'sys.path.insert(0, "/sd/k210")' in launcher
    assert "poker_app.main()" in launcher
    assert len(launcher.splitlines()) <= 15
    assert 'print("PVJSON " + payload)' in application
    for mode in ("SMOKE", "BENCHMARK", "STABILITY", "HOLDOUT", "DEMO"):
        assert f'"{mode}"' in application or f'("{mode}")' in application
