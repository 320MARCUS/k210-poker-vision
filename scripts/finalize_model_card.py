from __future__ import annotations

import argparse
import json
from pathlib import Path

from poker_vision.utils import sha256_file


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--card", required=True)
    parser.add_argument("--onnx", required=True)
    parser.add_argument("--tflite", required=True)
    parser.add_argument("--kmodel", required=True)
    parser.add_argument("--metrics", required=True)
    parser.add_argument("--emulator-parity", required=True)
    parser.add_argument("--kmodel-evaluation")
    parser.add_argument("--kpu-memory", type=int, required=True)
    parser.add_argument("--main-memory", type=int, required=True)
    parser.add_argument("--weights-bits", type=int, choices=(8, 16), default=8)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    card = json.loads(Path(args.card).read_text(encoding="utf-8"))
    metrics = json.loads(Path(args.metrics).read_text(encoding="utf-8"))
    parity = json.loads(Path(args.emulator_parity).read_text(encoding="utf-8"))
    onnx = Path(args.onnx)
    tflite = Path(args.tflite)
    kmodel = Path(args.kmodel)
    card.update(
        {
            "onnx_bytes": onnx.stat().st_size,
            "onnx_sha256": sha256_file(onnx),
            "tflite_bytes": tflite.stat().st_size,
            "tflite_sha256": sha256_file(tflite),
            "kmodel_bytes": kmodel.stat().st_size,
            "kmodel_sha256": sha256_file(kmodel),
            "kmodel_weights_bits": args.weights_bits,
            "kmodel_kpu_memory_bytes": args.kpu_memory,
            "kmodel_main_memory_bytes": args.main_memory,
            "kmodel_emulator_correlation": parity["correlation"],
            "test_metrics": metrics["metrics"],
            "identity_operating_point": metrics["identity_operating_point"],
        }
    )
    if args.kmodel_evaluation:
        evaluation = json.loads(
            Path(args.kmodel_evaluation).read_text(encoding="utf-8")
        )
        card["kmodel_emulator_evaluation"] = {
            "samples": evaluation["samples"],
            "thresholds": evaluation["thresholds"],
            "float": evaluation["float"],
            "kmodel": evaluation["kmodel_emulator"],
            "delta": evaluation["delta"],
        }
    output = Path(args.output)
    output.write_text(
        json.dumps(card, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(output)


if __name__ == "__main__":
    main()
