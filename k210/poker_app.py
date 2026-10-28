"""MaixPy 0.6.x poker-card detector and physical benchmark runner."""

# ruff: noqa: I001

import gc
import os
import time

import KPU as kpu
import lcd
import sensor
import ujson

import config


COLORS = (
    (255, 0, 0),
    (0, 220, 80),
    (0, 140, 255),
    (255, 210, 0),
    (230, 0, 220),
    (0, 230, 230),
)
UNKNOWN_COLOR = (255, 190, 0)


def _mem_free():
    try:
        return gc.mem_free()
    except Exception:
        return None


def _emit(event, **fields):
    fields["event"] = event
    try:
        payload = ujson.dumps(fields)
    except Exception as exc:
        payload = '{"event":"serialization_error","message":"%s"}' % repr(exc)
    print("PVJSON " + payload)


def _phase(name, **fields):
    _emit("phase", phase=name, mem_free=_mem_free(), **fields)


def _show(lines):
    lcd.clear(lcd.BLACK)
    y = 8
    for text, color in lines:
        lcd.draw_string(8, y, text, color, lcd.BLACK)
        y += 20


def _wait_start(mode):
    _phase(
        "ready",
        mode=mode,
        delay_ms=config.START_DELAY_MS,
        model_path=config.MODEL_PATH,
    )
    _show((("Mode: " + mode, lcd.WHITE), ("Starting...", lcd.YELLOW)))
    remaining = config.START_DELAY_MS
    while remaining > 0:
        chunk = min(remaining, 100)
        time.sleep(chunk / 1000.0)
        remaining -= chunk


def _load_model():
    _phase("model_load", path=config.MODEL_PATH)
    try:
        stat = os.stat(config.MODEL_PATH)
        _phase("model_file", path=config.MODEL_PATH, file_bytes=int(stat[6]))
    except Exception:
        pass
    task = kpu.load(config.MODEL_PATH)
    if task is None:
        raise RuntimeError("kpu.load returned None")
    kpu.init_yolo2(
        task,
        config.BOX_THRESHOLD,
        config.NMS_THRESHOLD,
        config.NUM_ANCHORS,
        config.ANCHORS,
        config.NUM_CLASSES,
    )
    _phase("model_ready")
    return task


def _init_camera():
    sensor.reset()
    sensor.set_pixformat(sensor.RGB565)
    sensor.set_framesize(sensor.QQVGA)
    sensor.set_hmirror(False)
    sensor.set_vflip(False)
    sensor.run(1)
    lcd.freq(16000000)
    _phase(
        "camera_ready",
        input_width=config.INPUT_WIDTH,
        input_height=config.INPUT_HEIGHT,
        frame="QQVGA",
    )


def _describe(obj):
    rect = obj.rect()
    x, y, width, height = int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3])
    score = float(obj.value())
    class_id = int(obj.classid())
    if score >= config.IDENTITY_THRESHOLD and 0 <= class_id < len(config.CLASS_CODES):
        label = config.CLASS_CODES[class_id]
        identity = label
    else:
        label = "unknown"
        identity = None
    return {
        "label": label,
        "identity": identity,
        "score": round(score, 4),
        "class_id": class_id,
        "bbox": [x, y, x + width, y + height],
    }


def _draw_result(frame, obj, detection):
    rect = obj.rect()
    if detection["identity"] is None:
        color = UNKNOWN_COLOR
    else:
        color = COLORS[int(detection["class_id"]) % len(COLORS)]
    label = "{} {:.2f}".format(detection["label"], float(detection["score"]))
    frame.draw_rectangle(rect, color=color, thickness=2)
    label_y = rect[1] - 12
    if label_y < 0:
        label_y = rect[1] + 2
    frame.draw_string(rect[0], label_y, label, color=color, scale=1)


def _run_frame(task):
    t0 = time.ticks_ms()
    frame = sensor.snapshot()
    t1 = time.ticks_ms()
    objects = kpu.run_yolo2(task, frame)
    t2 = time.ticks_ms()

    detections = []
    if objects:
        for obj in objects:
            detection = _describe(obj)
            detections.append(detection)
            _draw_result(frame, obj, detection)
    t3 = time.ticks_ms()
    lcd.display(frame)
    t4 = time.ticks_ms()

    return (
        frame,
        detections,
        {
            "latency_ms": time.ticks_diff(t4, t0),
            "capture_ms": time.ticks_diff(t1, t0),
            "kpu_ms": time.ticks_diff(t2, t1),
            "post_ms": time.ticks_diff(t3, t2),
            "display_ms": time.ticks_diff(t4, t3),
        },
    )


def _percentile(values, ratio):
    if not values:
        return 0
    ordered = sorted(values)
    index = int((len(ordered) - 1) * ratio)
    return ordered[index]


def _encode_detections(detections):
    compact = []
    for item in detections:
        compact.append(
            {
                "label": item["label"],
                "score": item["score"],
                "bbox": item["bbox"],
            }
        )
    return compact


def run_smoke(task):
    _wait_start("SMOKE")
    frames = 0
    detections = 0
    try:
        while frames < config.SMOKE_FRAMES:
            _, found, _ = _run_frame(task)
            frames += 1
            detections += len(found)
        _emit(
            "summary",
            phase="smoke",
            status="passed" if detections > 0 else "no_detections",
            frames=frames,
            detections=detections,
            mem_free=_mem_free(),
        )
    except Exception as exc:
        _emit(
            "error",
            phase="smoke",
            message=repr(exc),
            frame=frames,
            mem_free=_mem_free(),
        )


def run_benchmark(task):
    _wait_start("BENCHMARK")
    for _ in range(config.BENCHMARK_WARMUP_FRAMES):
        _run_frame(task)
    _phase("warmup_complete", frames=config.BENCHMARK_WARMUP_FRAMES)

    run_fps = []
    total_detections = 0
    for run_index in range(config.BENCHMARK_RUNS):
        latencies = []
        phase_totals = {
            "capture_ms": 0,
            "kpu_ms": 0,
            "post_ms": 0,
            "display_ms": 0,
        }
        detections = 0
        for _ in range(config.BENCHMARK_FRAMES):
            _, found, timing = _run_frame(task)
            latencies.append(timing["latency_ms"])
            detections += len(found)
            total_detections += len(found)
            for key in phase_totals:
                phase_totals[key] += timing[key]
        total_ms = sum(latencies)
        fps = config.BENCHMARK_FRAMES * 1000.0 / max(total_ms, 1)
        run_fps.append(fps)
        _emit(
            "benchmark_run",
            phase="benchmark",
            run=run_index + 1,
            frames=config.BENCHMARK_FRAMES,
            fps=round(fps, 4),
            latency_p50_ms=round(_percentile(latencies, 0.50), 4),
            latency_p95_ms=round(_percentile(latencies, 0.95), 4),
            phase_mean_ms={
                key: round(value / max(config.BENCHMARK_FRAMES, 1), 4)
                for key, value in phase_totals.items()
            },
            detections=detections,
            mem_free=_mem_free(),
        )

    ordered_fps = sorted(run_fps)
    median_fps = ordered_fps[len(ordered_fps) // 2]
    if median_fps < config.TARGET_FPS:
        benchmark_status = "below_target"
    elif total_detections == 0:
        benchmark_status = "no_detections"
    else:
        benchmark_status = "passed"
    _emit(
        "summary",
        phase="benchmark",
        status=benchmark_status,
        runs=[round(value, 4) for value in run_fps],
        median_fps=round(median_fps, 4),
        detections=total_detections,
        target_fps=config.TARGET_FPS,
        pipeline="capture+kpu+yolo2+decode+nms+draw+lcd",
        mem_free=_mem_free(),
    )


def run_stability(task, duration_seconds):
    _wait_start("STABILITY")
    started = time.ticks_ms()
    batch_started = started
    batch_frames = 0
    batch_detections = 0
    total_frames = 0
    total_detections = 0
    min_batch_fps = None
    max_batch_fps = 0.0
    fps_sum = 0.0
    batches = 0
    batches_with_detections = 0

    deadline_ms = duration_seconds * 1000
    try:
        while time.ticks_diff(time.ticks_ms(), started) < deadline_ms:
            _, found, _ = _run_frame(task)
            batch_frames += 1
            total_frames += 1
            total_detections += len(found)
            batch_detections += len(found)
            if batch_frames >= 100:
                elapsed = time.ticks_diff(time.ticks_ms(), batch_started)
                batch_fps = batch_frames * 1000.0 / max(elapsed, 1)
                if batch_detections > 0:
                    batches_with_detections += 1
                if min_batch_fps is None or batch_fps < min_batch_fps:
                    min_batch_fps = batch_fps
                if batch_fps > max_batch_fps:
                    max_batch_fps = batch_fps
                fps_sum += batch_fps
                batches += 1
                _emit(
                    "frame_batch",
                    phase="stability",
                    batch=batches,
                    frames=batch_frames,
                    elapsed_ms=time.ticks_diff(time.ticks_ms(), started),
                    fps=round(batch_fps, 4),
                    detections=total_detections,
                    mem_free=_mem_free(),
                )
                batch_frames = 0
                batch_detections = 0
                batch_started = time.ticks_ms()
                gc.collect()

        elapsed = time.ticks_diff(time.ticks_ms(), started)
        completed = elapsed >= deadline_ms
        stability_status = "passed"
        if not completed or total_frames == 0:
            stability_status = "failed"
        elif total_detections == 0:
            stability_status = "no_detections"
        _emit(
            "summary",
            phase="stability",
            status=stability_status,
            duration_seconds=duration_seconds,
            elapsed_ms=elapsed,
            frames=total_frames,
            detections=total_detections,
            batches=batches,
            batches_with_detections=batches_with_detections,
            min_batch_fps=round(min_batch_fps or 0.0, 4),
            mean_batch_fps=round(fps_sum / max(batches, 1), 4),
            max_batch_fps=round(max_batch_fps, 4),
            mem_free=_mem_free(),
        )
    except Exception as exc:
        _emit(
            "error",
            phase="stability",
            message=repr(exc),
            elapsed_ms=time.ticks_diff(time.ticks_ms(), started),
            frames=total_frames,
            mem_free=_mem_free(),
        )


def _ensure_holdout_dir():
    try:
        os.stat(config.HOLDOUT_OUTPUT_DIR)
    except Exception:
        try:
            os.mkdir(config.HOLDOUT_OUTPUT_DIR)
        except Exception:
            pass


def run_holdout(task, scene_count):
    _ensure_holdout_dir()
    _wait_start("HOLDOUT")
    scene = 0
    captured_scenes = 0
    try:
        if len(config.HOLDOUT_LAYOUT) < scene_count:
            raise ValueError("HOLDOUT_LAYOUT does not contain enough scenes")
        for scene in range(1, scene_count + 1):
            cards = config.HOLDOUT_LAYOUT[scene - 1]
            labels = config.HOLDOUT_SLOT_LABELS
            _show(
                (
                    ("Scene %d/%d" % (scene, scene_count), lcd.WHITE),
                    ("%s:%s  %s:%s" % (labels[0], cards[0], labels[1], cards[1]), lcd.YELLOW),
                    ("%s:%s  %s:%s" % (labels[2], cards[2], labels[3], cards[3]), lcd.YELLOW),
                    ("Arrange, then wait 10 s", lcd.GREEN),
                    ("Capturing shortly", lcd.GREEN),
                )
            )
            _phase(
                "holdout_wait",
                scene=scene,
                wait_ms=config.HOLDOUT_WAIT_MS,
                cards=list(cards),
            )
            remaining = config.HOLDOUT_WAIT_MS
            while remaining > 0:
                chunk = min(remaining, 100)
                time.sleep(chunk / 1000.0)
                remaining -= chunk

            final_frame = None
            final_found = []
            for _ in range(config.HOLDOUT_CAPTURE_FRAMES):
                final_frame, final_found, _ = _run_frame(task)
            image_path = "%s/scene_%02d.jpg" % (config.HOLDOUT_OUTPUT_DIR, scene)
            saved = False
            if final_frame is not None:
                try:
                    final_frame.save(image_path)
                    saved = True
                    captured_scenes += 1
                except Exception as exc:
                    _emit(
                        "error",
                        phase="holdout_save",
                        scene=scene,
                        message=repr(exc),
                    )
            _emit(
                "holdout_scene",
                phase="holdout",
                scene=scene,
                image=image_path,
                image_saved=saved,
                detections=_encode_detections(final_found),
                mem_free=_mem_free(),
            )
        _emit(
            "summary",
            phase="holdout",
            status="complete" if captured_scenes == scene_count else "incomplete",
            scenes=scene_count,
            captured_scenes=captured_scenes,
            mem_free=_mem_free(),
        )
    except Exception as exc:
        _emit(
            "error",
            phase="holdout",
            message=repr(exc),
            scene=scene,
            mem_free=_mem_free(),
        )


def run_demo(task):
    _wait_start("DEMO")
    frame_count = 0
    detection_count = 0
    batch_started = time.ticks_ms()
    while True:
        _, found, _ = _run_frame(task)
        frame_count += 1
        detection_count += len(found)
        if frame_count % 100 == 0:
            elapsed = time.ticks_diff(time.ticks_ms(), batch_started)
            _emit(
                "frame_batch",
                phase="demo",
                frames=frame_count,
                fps=round(100000.0 / max(elapsed, 1), 4),
                detections=detection_count,
                mem_free=_mem_free(),
            )
            batch_started = time.ticks_ms()
            gc.collect()


def main(mode_override=None):
    task = None
    mode = str(mode_override or getattr(config, "RUN_MODE", "DEMO")).upper()
    lcd.init()
    lcd.clear(lcd.BLACK)
    _show((("K210 Poker Vision", lcd.WHITE), ("Loading model...", lcd.YELLOW)))
    try:
        task = _load_model()
        _init_camera()
        _phase("mode_start", mode=mode)
        if mode == "SMOKE":
            run_smoke(task)
        elif mode == "BENCHMARK":
            run_benchmark(task)
        elif mode == "STABILITY":
            run_stability(task, config.STABILITY_SECONDS)
        elif mode == "HOLDOUT":
            run_holdout(task, config.HOLDOUT_SCENES)
        elif mode == "DEMO":
            run_demo(task)
        else:
            raise ValueError("unsupported RUN_MODE: " + mode)
    except Exception as exc:
        _emit("error", phase="main", message=repr(exc), mem_free=_mem_free())
        _show((("Runtime error", lcd.RED), (repr(exc)[:30], lcd.WHITE)))
    finally:
        try:
            sensor.run(0)
        except Exception:
            pass
        if task is not None:
            try:
                kpu.deinit(task)
            except Exception:
                pass
        gc.collect()


if __name__ == "__main__":
    main()
