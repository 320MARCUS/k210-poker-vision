from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    rows: dict[int, dict] = {}
    for raw_path in args.history:
        for line in Path(raw_path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            rows[int(row["epoch"])] = row
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for epoch in sorted(rows):
            handle.write(json.dumps(rows[epoch], ensure_ascii=False) + "\n")
    print(output)


if __name__ == "__main__":
    main()
