# 实验记录

所有数据划分保持 964/193/128，测试集不参与 checkpoint 或阈值选择。

## E1：215×215

- test mAP@0.5：`0.503`
- test mAP@0.5:0.95：`0.256`
- precision / recall：`0.466 / 0.537`

结论：分辨率不足以稳定区分点数和花色，不满足作品目标。

## E2：320×320 初版

- test mAP@0.5：`0.689`
- mAP@0.5:0.95：`0.374`
- high-confidence identity accuracy：`0.762`
- identity coverage：`0.636`

结论：提高分辨率有效，但算子兼容仍限制 KModel 转换。

## E3：320×320 当前桌面模型

- checkpoint SHA-256：
  `d2fe485940c66928874e2d937a863814b4d12314531f6df32a378d7fd72e2ec1`
- test mAP@0.5：`0.875`
- test mAP@0.5:0.95：`0.541`
- precision / recall：`0.804 / 0.843`
- identity accuracy：`0.857`
- identity coverage：`0.933`
- RTX 4060 推理：约 `0.80 ms/图`
- KModel 模拟 20 图 mAP@0.5：`0.849`
- 同子集浮点 mAP@0.5：`0.870`
- KModel 模拟与浮点差值：`-0.021`

结论：桌面精度和量化后输出均可用；5.20 MB KModel 在实机出现
`ERR_NO_MEM`，不能当作部署成功。

## E4：160×120 实机迁移

- 输入：`120×160`
- 输出：`1×285×7×10`
- KModel：`2,089,896` 字节
- SHA-256：`060163f63db6b4bb818a3c8483ca2f686f3e7e1331bef09b7567b79422fc3b6a`

结论：摄像头、KPU、后处理和 LCD 跑通，但现场梅花 9 持续识别失败。未完成
完整 FPS、稳定性和 holdout。

## E5：e20 微调参考

- checkpoint SHA-256：
  `20d2cfd031e3a7fb397fd8d767d071c30243873905455027ca05f92a5abaf23c`
- KModel SHA-256：
  `5ac40f3fe35cff586e10ffaac09d6ed462abeda580c1323dde8ee50842094a10`
- valid mAP@0.5：`0.481`
- identity accuracy：`0.588`
- identity coverage：`0.747`
- 梅花 9 AP@0.5：`0.505`

结论：说明矩形输入微调有优化空间，但未完成物理复验，不进入默认包。
