# Maix-Bit / K210 deployment package

This package targets a Sipeed Maix-Bit V2.0 running MaixPy 0.6.x. The on-board
boot file is deliberately small; the application, configuration and KModel live
on a FAT32 SD card.

## SD layout

```text
/flash/main.py                       boot launcher
/sd/k210/poker_app.py                detector and experiment runner
/sd/k210/config.py                   generated 52-class configuration
/sd/models/yolov2_k210.kmodel        2,089,896-byte KModel
```

Do not format a card that contains other data. Use a blank or already backed-up
card. Copy `main.py` to `/flash/main.py` only after the manual smoke test passes.

## Manual run before installing the launcher

Start MaixPy IDE at `115200 8N1`, connect to the REPL port, and run:

```python
import sys

sys.path.insert(0, "/sd/k210")
import poker_app

poker_app.main("SMOKE")
```

Mode overrides are `SMOKE`, `BENCHMARK`, `STABILITY`, `HOLDOUT` and `DEMO`.
The checked-in configuration defaults to `SMOKE`; the flash launcher will keep
using that mode until `config.py` is regenerated with another `--run-mode`.

## Measurement contract

All modes use the same full pipeline: camera capture, KPU YOLO2 inference,
decode/NMS, drawing and LCD display. The application emits one-line records:

```text
PVJSON {"event":"summary","phase":"benchmark","median_fps":...}
```

Frozen detection settings:

- box threshold: `0.25`
- identity threshold: `0.20`
- YOLO2 NMS threshold: `0.45`

Below the identity threshold, the box remains visible as `unknown`. The
holdout evaluation must not retune these values.

`BENCHMARK` discards 30 warm-up frames and measures three runs of 100 frames.
`STABILITY` runs for at least 300 seconds and emits a heartbeat every 100
frames. `HOLDOUT` displays four fixed card codes for each of 26 scenes, waits
10 seconds, captures five frames, saves the final annotated frame to
`/sd/holdout/scene_XX.jpg`, and emits the detections as `PVJSON`.

The fixed slots are `TL`, `TR`, `BL` and `BR`; all are kept inside the
QQVGA `160 x 120` camera frame.

## PC capture

The PowerShell collector opens a port read-only, leaves DTR/RTS disabled, and
never sends data to the board:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts/k210_serial_capture.ps1 `
  -ComPort COM3 -OutputPath artifacts/k210-serial/benchmark.log `
  -TimeoutSeconds 180 -StopAfterSummary
```

The same directory receives a `.jsonl` file containing parsed `PVJSON` events.
Physical smoke, camera, KPU, post-processing and LCD display were observed on
Maix-Bit. Formal FPS, stability and holdout accuracy remain unclaimed because
their complete records were not captured before project close.
