# 技术说明

项目解决的是把公开扑克牌数据训练成可审计、可转换、可在 K210 上真实运行的
检测原型。

## 数据

源数据 1,285 图和 5,574 框，但类别名称存在错位并包含异常 `59`。人工审计后
形成 52 类映射，隔离 1 个无法确认框，保留 5,573 个有效框和原始
964/193/128 划分。

## 模型

当前 320×320 桌面 YOLOv2-tiny 使用 10×10 网格、5 anchors、52 类和 285 通道
检测头。test mAP@0.5 为 `0.875`，identity accuracy 为 `0.857`。对应转换链
为 PyTorch → ONNX → TensorFlow/TFLite → nncase KModel。

320 KModel 的桌面模拟可运行，但实机因 KPU/摄像头内存条件失败。因此部署路线
改为 160×120 矩形输入，输出 7×10 网格，默认实机模型为 2,089,896 字节。

## 证据

- 桌面指标：`results/metrics.json`
- ONNX 与 TFLite parity：`results/onnx_parity.json`、`results/tflite_parity.json`
- KModel 模拟：`results/kmodel_20image_evaluation.json`
- 实机状态：`results/k210_benchmark.json`
- 媒体派生与隐私：`results/media_manifest.json`
- 模型卡：`docs/model-card.md`

## 边界

KModel 模拟、IDE 观察 FPS 和完整物理 benchmark 是不同证据。正式三轮 FPS、
300 秒稳定性和真实 holdout 未完成，不能互相替代。
