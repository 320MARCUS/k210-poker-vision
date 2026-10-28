from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
from ai_edge_litert.interpreter import Interpreter


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--onnx", required=True)
    parser.add_argument("--tflite", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    sample_nchw = np.load(args.input, allow_pickle=False).astype(np.float32)
    onnx_output = ort.InferenceSession(
        args.onnx,
        providers=["CPUExecutionProvider"],
    ).run(None, {"input": sample_nchw})[0]

    interpreter = Interpreter(model_path=args.tflite)
    interpreter.allocate_tensors()
    input_detail = interpreter.get_input_details()[0]
    output_detail = interpreter.get_output_details()[0]
    interpreter.set_tensor(input_detail["index"], sample_nchw.transpose(0, 2, 3, 1))
    interpreter.invoke()
    tflite_output = interpreter.get_tensor(output_detail["index"]).transpose(0, 3, 1, 2)

    difference = np.abs(onnx_output - tflite_output)
    payload = {
        "onnx_shape": list(onnx_output.shape),
        "tflite_shape": list(tflite_output.shape),
        "tflite_input_shape_nhwc": input_detail["shape"].tolist(),
        "tflite_output_shape_nhwc": output_detail["shape"].tolist(),
        "max_abs_difference": float(difference.max()),
        "mean_abs_difference": float(difference.mean()),
        "allclose_atol_1e-4": bool(np.allclose(onnx_output, tflite_output, atol=1e-4, rtol=1e-4)),
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
