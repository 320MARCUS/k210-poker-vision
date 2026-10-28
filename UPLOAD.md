# GitHub 上传清单

这个目录是公开候选。GitHub 建仓、可见性选择、push、tag 和 Release 均由本人操作。

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

## 上传顺序

```powershell
git init -b main
git add .
git commit -m "release: finalize K210 poker vision project"
git remote add origin <your-repository-url>
git push -u origin main
git tag -a v1.0.0 -m "K210 Poker Vision v1.0.0 closing release"
git push origin v1.0.0
```

在 GitHub Release `v1.0.0` 中上传 `dist/release` 下除 `release_manifest.json` 外的
全部资产，连同 `release_manifest.json` 一起保留也可。Release 标题建议：

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
