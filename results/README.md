# 结果文件

- `metrics.json`：当前 320×320 桌面模型测试指标；
- `per_class_metrics.csv`：当前桌面模型逐类 AP；
- `dataset_audit.json`：1,285 图、5,573 有效框、异常框隔离和划分；
- `onnx_parity.json`：PyTorch/ONNX 类别与框一致性；
- `tflite_parity.json`：ONNX/TFLite 输出一致性；
- `kmodel_20image_evaluation.json`：320 KModel 模拟与浮点子集比较；
- `kmodel_simulation_parity.json`：KModel 模拟输出相关性；
- `e20_candidate_metrics.json`：160×120 e20 未物理复验候选；
- `k210_benchmark.json`：实机证据层级与未完成协议；
- `k210_holdout.json`：未完成 holdout 的明确状态；
- `k210-smoke-evidence.log`：去除本机路径的串口启动证据；
- `media_manifest.json`：原媒体、公开派生媒体、隐私检查和哈希。

`artifacts/` 中的 checkpoint、原始串口日志和批量推理仍保留在私有工作目录，
不进入公开仓库。

Release 资产清单只在构建目录 `dist/release/release_manifest.json` 中生成。
