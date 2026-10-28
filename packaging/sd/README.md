# K210 Poker Vision SD 包

该目录可安装到 FAT32 SD 卡，默认模型是已在 Maix-Bit 上跑通摄像头、KPU、后处理和 LCD 显示的 160×120 KModel。

## 安装

1. 备份 SD 卡中的现有内容。
2. 将本目录放在可读写的 Windows 电脑上。
3. 双击 `install-sd.bat`，输入 SD 卡盘符，例如 `F:`。
4. 安装器会检查 FAT32、备份已有的 `k210` 和 `models` 目录、复制文件并核对 SHA-256。
5. 安装器不会格式化 SD 卡，也不会刷写固件。

## 启动

把 SD 卡插入 Maix-Bit 后，可以先用 MaixPy IDE 手动执行：

```python
import sys

sys.path.insert(0, "/sd/k210")
import poker_app

poker_app.main("SMOKE")
```

只有冒烟测试通过后，才建议把安装包里的 `flash/main.py` 写入板载 `/flash/main.py`。安装器在连接板卡时可选择通过 REPL 上传该启动器。

## 约束

- 目标固件：MaixPy 0.6.x；实测为 MaixPy 0.6.2。
- 输入：`160×120`，QQVGA 摄像头。
- 类别：52。
- 阈值：box `0.25`、identity `0.20`、NMS `0.45`。
- 低于 identity 阈值的框显示黄色 `unknown`，不强行报牌面。
- 本包没有宣称完整三轮 FPS、300 秒稳定性或 104 实例 holdout 已通过。

详细问题见仓库中的 `docs/environment-and-deployment.md`。
