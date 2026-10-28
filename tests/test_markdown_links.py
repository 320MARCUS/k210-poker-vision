import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".tools",
    ".tmp",
    ".venv",
    "artifacts",
    "data",
    "dist",
    "vendor",
}
LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def test_local_markdown_links_exist() -> None:
    missing: list[str] = []
    for path in ROOT.rglob("*.md"):
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        text = path.read_text(encoding="utf-8")
        for raw_target in LINK.findall(text):
            target = raw_target.strip().strip("<>")
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            target = unquote(target.split("#", 1)[0])
            if not (path.parent / target).resolve().exists():
                missing.append(f"{path.relative_to(ROOT)} -> {target}")
    assert not missing, "\n".join(missing)
