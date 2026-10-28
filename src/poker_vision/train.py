from __future__ import annotations

import json
import math
import time
from pathlib import Path

import torch
from torch import nn

from .anchors import estimate_dataset_anchors, set_model_anchors
from .data import PokerDataset, make_loader
from .loss import YOLOv2Loss
from .metrics import decode_predictions, evaluate_metrics
from .model import YOLOv2Tiny, load_darknet_weights
from .utils import ensure_dir, runtime_metadata, select_device, set_seed, write_json


def train_command(args) -> dict:
    set_seed(args.seed)
    device = select_device(args.device)
    output_dir = ensure_dir(args.output_dir)
    model = YOLOv2Tiny(args.cfg).to(device)
    resume_checkpoint = None
    initialization_checkpoint = None
    if args.resume:
        resume_checkpoint = torch.load(
            args.resume,
            map_location=device,
            weights_only=False,
        )
        model.load_state_dict(resume_checkpoint["model_state_dict"])
    elif getattr(args, "initialize_from", None):
        initialization_checkpoint = torch.load(
            args.initialize_from,
            map_location=device,
            weights_only=False,
        )
        copied, skipped = load_prefix_compatible_state(
            model,
            initialization_checkpoint["model_state_dict"],
        )
        print(f"compatible checkpoint tensors copied={copied}, skipped={skipped}")
    elif args.weights:
        loaded, skipped = load_darknet_weights(model, args.weights)
        print(f"Darknet layers loaded={loaded}, skipped={skipped}")

    train_dataset = PokerDataset(
        args.data_dir,
        "train",
        input_size=model.input_shape,
        augment=True,
    )
    valid_dataset = PokerDataset(
        args.data_dir,
        "valid",
        input_size=model.input_shape,
        augment=False,
    )
    train_loader = make_loader(train_dataset, args.batch_size, True, args.num_workers)
    valid_loader = make_loader(valid_dataset, args.batch_size, False, args.num_workers)

    checkpoint_metadata = resume_checkpoint or initialization_checkpoint
    if checkpoint_metadata and checkpoint_metadata.get("anchors"):
        anchors = checkpoint_metadata["anchors"]
    elif args.anchors:
        anchors = [
            tuple(float(value) for value in pair)
            for pair in json.loads(Path(args.anchors).read_text(encoding="utf-8"))
        ]
    elif args.estimate_anchors:
        grid_height, grid_width = infer_grid_shape(model, device)
        anchors = estimate_dataset_anchors(
            args.data_dir,
            grid_width=grid_width,
            grid_height=grid_height,
            num_anchors=model.num_anchors,
        )
    else:
        anchors = model.anchors.cpu().tolist()
    set_model_anchors(model, anchors)
    write_json(output_dir / "anchors.json", anchors)

    criterion = YOLOv2Loss(
        num_classes=model.num_classes,
        num_anchors=model.num_anchors,
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(args.epochs, 1))
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")
    if resume_checkpoint:
        if resume_checkpoint.get("optimizer_state_dict"):
            optimizer.load_state_dict(resume_checkpoint["optimizer_state_dict"])
        if resume_checkpoint.get("scheduler_state_dict") and not args.reset_scheduler:
            scheduler.load_state_dict(resume_checkpoint["scheduler_state_dict"])

    best_loss = (
        float(resume_checkpoint.get("valid_loss", math.inf)) if resume_checkpoint else math.inf
    )
    best_map = float(resume_checkpoint.get("valid_mAP50", -1.0)) if resume_checkpoint else -1.0
    stale_epochs = 0
    history_path = output_dir / "history.jsonl"
    start_epoch = int(resume_checkpoint["epoch"]) if resume_checkpoint else 0
    if resume_checkpoint and history_path.exists():
        history = [
            json.loads(line)
            for line in history_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    elif resume_checkpoint:
        history = []
    else:
        history = []
        history_path.unlink(missing_ok=True)
    if resume_checkpoint and args.reset_scheduler:
        for parameter_group in optimizer.param_groups:
            parameter_group["lr"] = args.lr
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            optimizer,
            T_max=max(args.epochs - start_epoch, 1),
            eta_min=args.lr * 0.1,
        )
    elif resume_checkpoint and not resume_checkpoint.get("scheduler_state_dict"):
        for _ in range(start_epoch):
            scheduler.step()

    for epoch in range(start_epoch, args.epochs):
        start = time.time()
        model.train()
        train_total = 0.0
        train_components = {
            "xy": 0.0,
            "wh": 0.0,
            "obj": 0.0,
            "noobj": 0.0,
            "cls": 0.0,
        }
        for images, targets, _ in train_loader:
            images = images.to(device, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            with torch.amp.autocast("cuda", enabled=device.type == "cuda"):
                raw = model(images)
                loss, components = criterion(model, raw, targets)
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=10.0)
            scaler.step(optimizer)
            scaler.update()
            train_total += float(loss.detach())
            for key, value in components.items():
                train_components[key] += value

        model.eval()
        valid_total = 0.0
        valid_components = {
            "xy": 0.0,
            "wh": 0.0,
            "obj": 0.0,
            "noobj": 0.0,
            "cls": 0.0,
        }
        valid_predictions = []
        valid_targets = []
        with torch.no_grad():
            for images, batch_targets, _ in valid_loader:
                images = images.to(device, non_blocking=True)
                with torch.amp.autocast("cuda", enabled=device.type == "cuda"):
                    raw = model(images)
                    loss, components = criterion(model, raw, batch_targets)
                    decoded = model.decode(raw)
                valid_total += float(loss)
                for key, value in components.items():
                    valid_components[key] += value
                valid_predictions.extend(
                    decode_predictions(
                        decoded,
                        confidence_threshold=0.001,
                        iou_threshold=0.45,
                    )
                )
                valid_targets.extend(target.cpu() for target in batch_targets)

        train_loss = train_total / max(len(train_loader), 1)
        valid_loss = valid_total / max(len(valid_loader), 1)
        validation_metrics = evaluate_metrics(
            valid_predictions,
            valid_targets,
            model.num_classes,
            report_threshold=0.25,
        )
        validation_map = validation_metrics["mAP50"]
        train_average = {
            key: value / max(len(train_loader), 1) for key, value in train_components.items()
        }
        valid_average = {
            key: value / max(len(valid_loader), 1) for key, value in valid_components.items()
        }
        row = {
            "epoch": epoch + 1,
            "seconds": time.time() - start,
            "lr": optimizer.param_groups[0]["lr"],
            "train_loss": train_loss,
            "valid_loss": valid_loss,
            "valid_mAP50": validation_map,
            "valid_identity_accuracy": validation_metrics["identity_accuracy"],
            "train": train_average,
            "valid": valid_average,
        }
        history.append(row)
        with history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(
            f"epoch={epoch + 1}/{args.epochs} train={train_loss:.4f} "
            f"valid={valid_loss:.4f} mAP50={validation_map:.4f} "
            f"seconds={row['seconds']:.1f}"
        )
        scheduler.step()

        checkpoint = {
            "epoch": epoch + 1,
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "scheduler_state_dict": scheduler.state_dict(),
            "valid_loss": valid_loss,
            "valid_mAP50": validation_map,
            "input_size": model.input_size,
            "input_shape": list(model.input_shape),
            "num_classes": model.num_classes,
            "num_anchors": model.num_anchors,
            "anchors": anchors,
            "cfg": str(Path(args.cfg).resolve()),
        }
        torch.save(checkpoint, output_dir / "latest.pth")
        if valid_loss < best_loss:
            best_loss = valid_loss
        if validation_map > best_map:
            best_map = validation_map
            stale_epochs = 0
            torch.save(checkpoint, output_dir / "best.pth")
        else:
            stale_epochs += 1
            if args.early_stopping and stale_epochs >= args.early_stopping:
                print(f"early stopping after {stale_epochs} stale epochs")
                break

    summary = {
        "best_valid_loss": best_loss,
        "best_valid_mAP50": best_map,
        "epochs_completed": len(history),
        "anchors": anchors,
        "input_size": model.input_size,
        "input_shape": list(model.input_shape),
        "num_classes": model.num_classes,
        "runtime": runtime_metadata(),
        "history": history,
    }
    write_json(output_dir / "train_summary.json", summary)
    return summary


def load_prefix_compatible_state(
    model: nn.Module,
    source_state: dict[str, torch.Tensor],
) -> tuple[int, int]:
    """Copy equal-shape tensors and leading slices into a narrower model."""
    target_state = model.state_dict()
    copied = 0
    skipped = 0
    with torch.no_grad():
        for name, target in target_state.items():
            source = source_state.get(name)
            if source is None or source.ndim != target.ndim:
                skipped += 1
                continue
            if any(source_size < target_size for source_size, target_size in zip(
                source.shape, target.shape, strict=True
            )):
                skipped += 1
                continue
            source_slice = tuple(
                slice(0, target_size) if source_size != target_size else slice(None)
                for source_size, target_size in zip(source.shape, target.shape, strict=True)
            )
            target.copy_(source[source_slice].to(device=target.device, dtype=target.dtype))
            copied += 1
    return copied, skipped


def infer_grid_shape(model: YOLOv2Tiny, device: torch.device) -> tuple[int, int]:
    was_training = model.training
    model.eval()
    with torch.no_grad():
        output = model(
            torch.zeros(
                1,
                3,
                model.input_height,
                model.input_width,
                device=device,
            )
        )
    if was_training:
        model.train()
    return int(output.shape[-2]), int(output.shape[-1])
