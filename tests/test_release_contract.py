import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_default_k210_model_contract_is_fixed_in_build_script() -> None:
    script = (ROOT / "scripts" / "build_k210_sd.ps1").read_text(encoding="utf-8")
    assert "ExpectedModelBytes = 2089896" in script
    assert (
        "060163f63db6b4bb818a3c8483ca2f686f3e7e1331bef09b7567b79422fc3b6a"
        in script
    )
    assert "physically-demonstrated" in script


def test_media_manifest_outputs_exist_and_match_hashes() -> None:
    manifest = json.loads((ROOT / "results" / "media_manifest.json").read_text(encoding="utf-8"))
    assert manifest["privacy_review"]["audio"] == "removed from public video"
    assert len(manifest["items"]) == 4
    for item in manifest["items"]:
        path = ROOT / item["output"]
        payload = path.read_bytes()
        assert len(payload) == item["output_file"]["bytes"]
        assert hashlib.sha256(payload).hexdigest() == item["output_file"]["sha256"]


def test_e20_candidate_remains_marked_pending() -> None:
    status = json.loads(
        (ROOT / "results" / "e20_candidate_metrics.json").read_text(encoding="utf-8")
    )
    assert status["status"] == "candidate_physical_verification_pending"
    assert status["metrics"]["nine_of_clubs_ap50"] > 0.5


def test_public_readme_does_not_make_unverified_hardware_claims() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "未完成正式三轮 FPS、300 秒稳定性和 104 实例 holdout" in readme
    assert "不是完成全部硬件 KPI 的生产版本" in (
        ROOT / "docs" / "release-notes-v1.0.md"
    ).read_text(encoding="utf-8")
    assert "e20" in readme.lower()
