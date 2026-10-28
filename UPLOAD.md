# GitHub 上传清单

项目已发布：

- 仓库：<https://github.com/320MARCUS/k210-poker-vision>
- Release：<https://github.com/320MARCUS/k210-poker-vision/releases/tag/v1.0.0>

本文件保留发布检查口径和后续版本更新流程。

## 仓库信息

- 建议仓库名：`k210-poker-vision`
- 简介：`52-class poker-card detection on K210 with audited data, YOLOv2 training, quantization and honest hardware evidence`
- 建议 topics：`k210`, `maixpy`, `yolov2`, `edge-ai`, `object-detection`, `model-quantization`

## 本地检查

```bat
start-dev.bat test
start-dev.bat leak
```

确认以下内容不存在：

- `artifacts/`
- `data/`
- `vendor/`
- 完整 checkpoint、数据集和大下载包；
- 一次性失败 probe、旧内存适配包和 SD 布局修复脚本；
- 原始未脱敏照片、视频或音频；
- token、账号、个人路径和聊天信息。

## 后续版本流程

```powershell
git add .
git commit -m "<change summary>"
git push origin main
```

需要发布新版本时，重新构建 `dist/release`，核对 `SHA256SUMS.txt` 与
`release_manifest.json`，再创建新 tag 和 Release。已发布的 `v1.0.0`
继续保留原始模型、PC/SD 包和演示媒体。

```text
K210 Poker Vision v1.0.0 - edge deployment and quantization review
```

Release 正文使用 `docs/release-notes-v1.0.md`。

## 必须保留的口径

- 默认模型是已跑通摄像头的 160×120 KModel；
- IDE 约 10 FPS 是观察值，不是正式 benchmark；
- 三轮 FPS、300 秒稳定性和 104 实例 holdout 未完成；
- e20 是未物理复验候选；
- 320 桌面 mAP 不能代表 K210 实机性能。
