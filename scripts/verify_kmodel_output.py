from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from ai_edge_litert.interpreter import Interpreter
from PIL import Image


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tflite", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument(
        "--kmodel-output",
        required=True,
        help="float32 output emitted by ncc -i k210model -o inference",
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    image = Image.open(args.image).convert("RGB").resize((320, 320))
    sample_nchw = np.asarray(image, dtype=np.float32).transpose(2, 0, 1)[None] / 255.0

    interpreter = Interpreter(model_path=args.tflite)
    interpreter.allocate_tensors()
    input_detail = interpreter.get_input_details()[0]
    output_detail = interpreter.get_output_details()[0]
    interpreter.set_tensor(input_detail["index"], sample_nchw.transpose(0, 2, 3, 1))
    interpreter.invoke()
    reference = interpreter.get_tensor(output_detail["index"])[0].transpose(2, 0, 1)

    emulated = np.fromfile(args.kmodel_output, dtype=np.float32).reshape(reference.shape)
    difference = np.abs(reference - emulated)
    correlation = float(np.corrcoef(reference.ravel(), emulated.ravel())[0, 1])
    payload = {
        "shape": list(reference.shape),
        "max_abs_difference": float(difference.max()),
        "mean_abs_difference": float(difference.mean()),
        "correlation": correlation,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
