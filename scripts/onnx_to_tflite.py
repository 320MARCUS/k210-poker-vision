from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--onnx", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument(
        "--test-input",
        required=True,
        help="normalized [1,3,H,W] NumPy sample for onnx2tf validation",
    )
    args = parser.parse_args()

    onnx_path = Path(args.onnx).resolve()
    output_path = Path(args.output).resolve()
    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

    try:
        import onnx2tf.onnx2tf as onnx2tf_module
        import tensorflow as tf
    except ImportError as exc:
        raise SystemExit(
            "TensorFlow is missing. Install the centrally managed K210 "
            "conversion environment before running this script."
        ) from exc

    test_data_nchw = np.load(Path(args.test_input), allow_pickle=False)
    if test_data_nchw.ndim != 4 or test_data_nchw.shape[1] != 3:
        raise SystemExit("test input must have shape [N, 3, H, W]")
    test_data_nhwc = test_data_nchw.transpose(0, 2, 3, 1)

    # onnx2tf 1.28 downloads an object-pickled sample tensor for every 4D NCHW
    # input. Supply the reviewed project sample instead of that remote fallback.
    onnx2tf_module.download_test_image_data = lambda: test_data_nhwc
    onnx2tf_module.convert(
        input_onnx_file_path=str(onnx_path),
        output_folder_path=str(work_dir),
        output_signaturedefs=True,
        not_use_onnxsim=False,
        non_verbose=True,
    )

    candidates = sorted(work_dir.rglob("*float32.tflite"))
    if not candidates:
        candidates = sorted(work_dir.rglob("*.tflite"))
    if candidates:
        source = candidates[0]
        output_path.write_bytes(source.read_bytes())
    else:
        saved_models = sorted(work_dir.rglob("saved_model.pb"))
        if not saved_models:
            raise SystemExit("onnx2tf produced neither TFLite nor SavedModel")
        converter = tf.lite.TFLiteConverter.from_saved_model(str(saved_models[0].parent))
        output_path.write_bytes(converter.convert())

    print(output_path)
    print(output_path.stat().st_size)


if __name__ == "__main__":
    main()
