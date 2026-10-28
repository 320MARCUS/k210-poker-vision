# v1.0.0 收尾版

## 定位

本版本是“边缘部署与量化实验”公开候选，不是完成全部硬件 KPI 的生产版本。

## 包含

- 52 类数据审计、类别映射和异常框隔离记录；
- YOLOv2-tiny 训练、评估、预测和导出代码；
- 320×320 桌面模型指标；
- 160×120 K210 实机应用、配置和默认 KModel；
- e20 未复验候选的 ONNX、KModel、指标和状态；
- PC 开发终端包与 FAT32 SD 一键安装包；
- 硬件图、LCD 检测图和去除音频的 55 秒演示视频；
- SHA-256 清单、模型卡、工程复盘和面试材料。

## 已验证

- 320 桌面模型 test mAP@0.5 `0.875`；
- 20 图 KModel 模拟 mAP@0.5 `0.849`；
- 160×120 KModel 在 Maix-Bit 上成功加载并显示检测结果；
- MaixPy IDE 可观察完整画面；
- 阈值 `0.20→0.10` 对照证明“强行报牌”会降低身份准确率。

## 未完成

- 三轮 100 帧完整管线 benchmark；
- 300 秒稳定性；
- 104 个真实牌面 holdout；
- e20 物理复验。

## 发布资产

- `k210-poker-vision-pc-v1.0.0.zip`
- `k210-poker-vision-sd-v1.0.0.zip`
- `k210-poker-vision-default.kmodel`
- `candidate-e20-physical-verification-pending.kmodel`
- `candidate-e20-physical-verification-pending.onnx`
- `candidate-e20-physical-verification-pending.json`
- `MODEL_CARD.md`
- `k210-demo.mp4`
- `k210-demo-poster.jpg`
- `SHA256SUMS.txt`
- `release_manifest.json`

失败 probe、旧 memoryfit 包和不可部署的 320 KModel 不作为 Release 资产。
