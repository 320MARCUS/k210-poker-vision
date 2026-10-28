from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if "," in value:
        return [float(item.strip()) for item in value.split(",")]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def parse_cfg(path: str | Path) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            if current:
                blocks.append(current)
            current = {"type": line.strip("[]")}
            continue
        if "=" not in line:
            raise ValueError(f"invalid cfg line: {raw_line}")
        key, value = line.split("=", 1)
        current[key.strip()] = _parse_scalar(value)
    if current:
        blocks.append(current)
    return blocks


class DarknetMaxPool2d(nn.Module):
    """Padding-compatible max-pool used by the original YOLOv2 graph."""

    def __init__(
        self,
        kernel_size: int,
        stride: int,
        k210_compatible: bool = False,
    ) -> None:
        super().__init__()
        self.kernel_size = kernel_size
        self.stride = stride
        self.pad = kernel_size // 2
        self.k210_compatible = k210_compatible

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        if not self.k210_compatible:
            outputs = F.max_pool2d(
                inputs,
                self.kernel_size,
                self.stride,
                padding=self.pad,
                ceil_mode=True,
            )
            height = (inputs.size(2) + self.pad - self.kernel_size) // self.stride + 1
            width = (inputs.size(3) + self.pad - self.kernel_size) // self.stride + 1
            return outputs[:, :, :height, :width]
        if self.stride == 1:
            return inputs
        return F.max_pool2d(
            inputs,
            self.kernel_size,
            self.stride,
            padding=0,
            ceil_mode=False,
        )


class YOLOv2Tiny(nn.Module):
    """YOLOv2-tiny graph returning the raw region tensor [B, A*(5+C), H, W]."""

    def __init__(self, cfg_path: str | Path) -> None:
        super().__init__()
        self.blocks = parse_cfg(cfg_path)
        self.net = self.blocks[0]
        self.input_width = int(self.net["width"])
        self.input_height = int(self.net["height"])
        self.k210_compatible = bool(int(self.net.get("k210_compatible", 0))) or (
            self.input_width == 320 and self.input_height == 320
        )
        self.modules_list = self._build_modules()
        region = next(block for block in self.blocks if block["type"] == "region")
        anchors = [float(value) for value in region["anchors"]]
        self.register_buffer(
            "anchors",
            torch.tensor(anchors, dtype=torch.float32).reshape(-1, 2),
            persistent=False,
        )
        self.num_classes = int(region["classes"])
        self.num_anchors = int(region["num"])
        # Retain the historical square-size attribute for callers that only
        # understand square inputs. New callers should use input_shape.
        self.input_size = self.input_width

    @property
    def input_shape(self) -> tuple[int, int]:
        """Return ``(width, height)`` in model-input pixels."""
        return self.input_width, self.input_height

    def _build_modules(self) -> nn.ModuleList:
        modules = nn.ModuleList()
        previous_filters = 3
        for block in self.blocks[1:]:
            block_type = block["type"]
            if block_type == "convolutional":
                filters = int(block["filters"])
                kernel = int(block["size"])
                stride = int(block["stride"])
                padding = (kernel - 1) // 2 if int(block.get("pad", 0)) else 0
                batch_norm = int(block.get("batch_normalize", 0))
                layers: list[nn.Module] = [
                    nn.Conv2d(
                        previous_filters,
                        filters,
                        kernel,
                        stride,
                        padding,
                        bias=not batch_norm,
                    )
                ]
                if batch_norm:
                    layers.append(nn.BatchNorm2d(filters))
                if block.get("activation") == "leaky":
                    layers.append(nn.LeakyReLU(0.1, inplace=True))
                module = nn.Sequential(*layers)
                previous_filters = filters
            elif block_type == "maxpool":
                kernel = int(block["size"])
                stride = int(block["stride"])
                module = DarknetMaxPool2d(
                    kernel,
                    stride,
                    k210_compatible=self.k210_compatible,
                )
            else:
                module = nn.Identity()
            modules.append(module)
        return modules

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        output = inputs
        for block, module in zip(self.blocks[1:], self.modules_list, strict=True):
            output = module(output)
            if block["type"] == "region":
                break
        return output

    def decode(self, raw: torch.Tensor) -> torch.Tensor:
        """Return decoded boxes as [B, A, H, W, 5+C] in normalized coordinates."""
        batch, _, height, width = raw.shape
        values_per_anchor = 5 + self.num_classes
        if raw.shape[1] != self.num_anchors * values_per_anchor:
            raise ValueError(
                f"expected {self.num_anchors * values_per_anchor} channels, got {raw.shape[1]}"
            )
        reshaped = raw.view(batch, self.num_anchors, values_per_anchor, height, width)
        reshaped = reshaped.permute(0, 1, 3, 4, 2).contiguous()
        grid_y, grid_x = torch.meshgrid(
            torch.arange(height, device=raw.device, dtype=raw.dtype),
            torch.arange(width, device=raw.device, dtype=raw.dtype),
            indexing="ij",
        )
        xy = torch.sigmoid(reshaped[..., 0:2])
        xy[..., 0] = (xy[..., 0] + grid_x) / width
        xy[..., 1] = (xy[..., 1] + grid_y) / height
        wh = torch.exp(reshaped[..., 2:4].clamp(max=6.0))
        wh = wh * self.anchors.to(raw.device).view(1, self.num_anchors, 1, 1, 2)
        wh[..., 0] /= width
        wh[..., 1] /= height
        objectness = torch.sigmoid(reshaped[..., 4:5])
        class_probs = torch.softmax(reshaped[..., 5:], dim=-1)
        return torch.cat([xy, wh, objectness, class_probs], dim=-1)


def load_darknet_weights(
    model: YOLOv2Tiny,
    weights_path: str | Path,
    skip_last_conv: bool = True,
) -> tuple[int, int]:
    """Load matching Darknet convolution layers; stop safely at a shape mismatch."""
    loaded = 0
    skipped = 0
    with Path(weights_path).open("rb") as handle:
        header = np.frombuffer(handle.read(16), dtype=np.int32)
        if header.size != 4:
            raise ValueError("invalid Darknet weight header")
        convolution_indexes = [
            index
            for index, block in enumerate(model.blocks[1:])
            if block["type"] == "convolutional"
        ]
        last_convolution = convolution_indexes[-1] if convolution_indexes else -1
        for index, (block, module) in enumerate(
            zip(model.blocks[1:], model.modules_list, strict=True)
        ):
            if block["type"] != "convolutional":
                continue
            if skip_last_conv and index == last_convolution:
                skipped += 1
                break
            conv = next(child for child in module if isinstance(child, nn.Conv2d))
            bn = next(
                (child for child in module if isinstance(child, nn.BatchNorm2d)),
                None,
            )
            if bn is not None:
                count = bn.num_features
                values = {}
                for key, target in (
                    ("bias", bn.bias),
                    ("weight", bn.weight),
                    ("running_mean", bn.running_mean),
                    ("running_var", bn.running_var),
                ):
                    raw = np.frombuffer(handle.read(count * 4), dtype=np.float32)
                    if raw.size != count:
                        return loaded, skipped
                    values[key] = torch.from_numpy(raw.copy())
                if conv.weight.shape[0] != count:
                    skipped += 1
                    break
                bn.bias.data.copy_(values["bias"])
                bn.weight.data.copy_(values["weight"])
                bn.running_mean.data.copy_(values["running_mean"])
                bn.running_var.data.copy_(values["running_var"].clamp_min(0.0))
            else:
                count = conv.out_channels
                raw = np.frombuffer(handle.read(count * 4), dtype=np.float32)
                if raw.size != count or conv.bias is None:
                    skipped += 1
                    break
                conv.bias.data.copy_(torch.from_numpy(raw.copy()))

            weight_count = conv.weight.numel()
            raw_weights = np.frombuffer(handle.read(weight_count * 4), dtype=np.float32)
            if raw_weights.size != weight_count:
                skipped += 1
                break
            conv.weight.data.copy_(torch.from_numpy(raw_weights.copy()).view_as(conv.weight))
            loaded += 1
    return loaded, skipped
