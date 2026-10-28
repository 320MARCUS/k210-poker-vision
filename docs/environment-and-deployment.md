# 环境与部署说明

## 1. 已验证环境

| 组件 | 已验证值 |
|---|---|
| 板卡 | Sipeed Maix-Bit V2.0，Kendryte K210 |
| 固件 | MaixPy 0.6.2，`v0.6.2-85-g23d09fbcc`，2023-06-05 |
| 串口 | `COM3` 为 REPL，`COM4` 同时出现；设备为 FTDI `VID_0403/PID_6010` |
| 摄像头 | OV 系列，QQVGA `160×120` |
| nncase | 1.0.0 |
| 训练环境 | Python 3.12、PyTorch 2.14、CUDA 12.6；环境路径由本机变量指定 |
| GPU | NVIDIA RTX 4060 Laptop |

训练、转换和硬件验证另需支持 K210 的 Python 环境、nncase `ncc`、MaixPy IDE
和 kflash_gui。公开包不重新分发这些第三方工具，也不记录本机安装路径。

## 2. PC 开发环境

推荐从公开包根目录运行：

```bat
start-dev.bat
```

终端菜单提供：

1. 环境状态；
2. 环境修复；
3. pytest 与 Ruff；
4. 串口枚举；
5. `PVJSON` 日志采集；
6. `SMOKE/BENCHMARK/STABILITY/HOLDOUT/DEMO`；
7. MaixPy IDE；
8. SD 包构建；
9. Release 构建；
10. 泄漏扫描。

环境解析顺序：

1. 环境变量 `POKER_VISION_CENTRAL_PYTHON`；
2. 根据 `UV_PYTHON_INSTALL_DIR`、`PNPM_HOME` 等本机工具链变量自动发现的
   `envs/yolo`；
3. 项目 `.venv`；
4. `uv sync --frozen --extra dev`。

如果本机已有集中管理环境，可只在当前终端设置其 Python 路径：

```powershell
$env:POKER_VISION_CENTRAL_PYTHON = "<path-to-python.exe>"
$env:POKER_VISION_TOOLS_ROOT = "<path-to-tool-root>"
$env:MAIXPY_IDE = "<path-to-maixpyide.exe>"
$env:FFMPEG_EXE = "<path-to-ffmpeg.exe>"
```

这些变量不会被写回仓库或 Release 包。

如果 `uv` 不存在，启动器只下载固定的 `uv 0.12.24` 到 `.tools`，校验
`uv.exe` 的 SHA-256 后使用。不会安装全局程序，也不会修改 PATH。

## 3. SD 目录

```text
SD 根目录/
  k210/poker_app.py
  k210/config.py
  models/yolov2_k210.kmodel

板载 Flash:
  /flash/main.py
```

`/flash/main.py` 只有几行，作用是把 `/sd/k210` 加入 `sys.path` 并启动应用。
完整程序和模型都放在 SD，减少板载文件系统写入。

默认 KModel：

- 输入：`1×3×120×160`
- 输出：`1×285×7×10`
- 大小：`2,089,896` 字节
- SHA-256：`060163f63db6b4bb818a3c8483ca2f686f3e7e1331bef09b7567b79422fc3b6a`
- 权重：8-bit

## 4. 一键安装 SD

解压 `k210-poker-vision-sd-v1.0.0.zip`，双击：

```text
install-sd.bat
```

输入盘符，例如 `F:`。安装器会：

1. 校验包内文件；
2. 拒绝系统盘、非可移动盘和非 FAT32；
3. 把已有 `k210`、`models` 和根目录 `main.py` 复制到
   `.poker-vision-backup-时间戳`；
4. 复制应用和默认模型；
5. 重新计算目标文件 SHA-256；
6. 可选通过 REPL 把 `flash/main.py` 上传到 `/flash/main.py`。

安装器不会格式化卡、不会刷固件，也不会自动重启板卡。

## 5. 首次冒烟

连接 MaixPy IDE 到 REPL UART，波特率 `115200 8N1`：

```python
import sys

sys.path.insert(0, "/sd/k210")
import poker_app

poker_app.main("SMOKE")
```

通过条件：

- 日志出现 `model_file` 和 `model_ready`；
- 摄像头初始化；
- LCD 有画面；
- 能看到至少一个检测框；
- 结束后正常 `kpu.deinit`。

冒烟通过后再安装自动启动器。当前默认 `RUN_MODE = "SMOKE"`，如果发布演示版，
需要有意识地改为 `DEMO`，不要误把测试模式当成自动演示。

## 6. 常见故障

### 双 COM 口

FTDI 会同时暴露两个端口。一次只连接一个，用返回 MaixPy `>>>` 提示符的端口
作为 REPL。不要因为另一个端口无响应就反复刷固件。

### 串口消失

先检查 USB 数据线、接口和 USB Hub。串口反复消失是连接问题，不是
“模型坏掉”或“必须换固件”的证据。

### `ERR_KMODEL_FORMAT`

表示文件不符合当前 KPU 对 KModel 的解析契约。11.18 MB 历史模型已出现此错误。
不要把 `.onnx` 或 `.tflite` 直接改后缀为 `.kmodel`。

### `ERR_NO_MEM`

模型加载成功不等于摄像头、推理和显示能同时运行。320 输入模型与 QVGA 摄像头
在当前固件下无法共存；当前解决路线是 160×120 模型，而不是关闭安全机制或盲刷
非目标固件。

### 能显示画面但没有检测框

确认模型 SHA-256、配置中的 anchor、输入尺寸、52 类和 285 通道输出匹配。
旧模型和当前脚本不能混搭。

## 7. 测量口径

- IDE 观察 FPS 只作现场说明；
- 正式 FPS 必须包含拍照、KPU、后处理、绘制和 LCD；
- 阈值固定为 box `0.25`、identity `0.20`、NMS `0.45`；
- 低于 identity 阈值的框保留并显示 `unknown`；
- 三轮 100 帧 benchmark、300 秒稳定性和 104 实例 holdout 尚未完成，不得写成已通过。

## 8. 禁止操作

- 不为通过测试而关闭 UAC、Defender、防火墙或安全启动；
- 不格式化含其他数据的 SD 卡；
- 不在未备份时覆盖 `/flash/main.py`；
- 不为兼容问题无限刷固件；
- 不上传原始数据集、checkpoint、第三方全量源码或未脱敏音视频。
