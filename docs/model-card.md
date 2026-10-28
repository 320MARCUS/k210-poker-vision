# 模型卡

## 用途

- 教育、作品展示和 K210 边缘推理复盘；
- 清晰、基本无遮挡的标准扑克牌桌面场景；
- 低置信度显示 `unknown`，允许系统不报牌面。

## 不适用范围

- 赌博执法、自动计分或其他身份错误会产生现实损失的场景；
- 严重遮挡、运动模糊、非标准牌面；
- 用训练集、少量现场演示或模拟指标宣称生产准确率。

## 数据

- 公开 Roboflow `poker cards`，CC BY 4.0；
- 1,285 张图，5,573 个可用框，52 类；
- 固定 964/193/128 划分；
- 1 个无法确认的源标注被隔离；
- 数据集不随仓库或 Release 分发。

## 320×320 桌面模型

- YOLOv2-tiny，RGB 320×320，10×10 网格，5 anchors，52 类；
- test mAP@0.5 `0.875`；
- test mAP@0.5:0.95 `0.541`；
- precision / recall `0.804 / 0.843`；
- identity accuracy `0.857`，coverage `0.933`；
- 对应 checkpoint SHA-256
  `d2fe485940c66928874e2d937a863814b4d12314531f6df32a378d7fd72e2ec1`。

该模型证明桌面训练和评估链有效。对应 5.20 MB KModel 在 K210 上出现
`ERR_NO_MEM`，不能作为可部署模型。

## 160×120 实机模型

- 输入 `1×3×120×160`；
- 输出 `1×285×7×10`；
- 大小 `2,089,896` 字节；
- SHA-256
  `060163f63db6b4bb818a3c8483ca2f686f3e7e1331bef09b7567b79422fc3b6a`；
- 已在 Maix-Bit V2.0 上跑通摄像头、KPU、YOLO2 后处理和 LCD；
- 未完成三轮完整管线 FPS、300 秒稳定性和 104 实例 holdout；
- 现场观察到梅花 9 持续识别失败。

该模型是默认 SD 包模型。IDE 观察约 `10.4–10.8 FPS`，不得写成正式 benchmark。

## e20 参考候选

- 输入和输出契约与实机模型相同；
- SHA-256
  `5ac40f3fe35cff586e10ffaac09d6ed462abeda580c1323dde8ee50842094a10`；
- valid mAP@0.5 `0.481`；
- identity accuracy `0.588`；
- identity coverage `0.747`；
- 梅花 9 AP@0.5 `0.505`。

e20 增加了 160×120 微调轮次，但未完成物理上传和复验，只作为
`candidate` / `physical-verification-pending` 发布。

## 阈值

- box：`0.25`
- identity：`0.20`
- NMS IoU：`0.45`

阈值在 holdout 前冻结。降低 identity 阈值到 `0.10` 的对照显示 coverage
升至 `0.885`，但 identity accuracy 降至 `0.442`，因此否决。

## 禁止表述

- “生产级高准确率 52 类识别”；
- “K210 稳定 10 FPS”；
- “320 KModel 已实机部署”；
- “e20 已完成实机验证”；
- 把 KModel 模拟结果当成物理实测结果。
