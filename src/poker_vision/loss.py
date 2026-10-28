from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F

from .model import YOLOv2Tiny


class YOLOv2Loss(nn.Module):
    def __init__(
        self,
        num_classes: int,
        num_anchors: int,
        object_scale: float = 5.0,
        no_object_scale: float = 1.0,
        class_scale: float = 1.0,
        coordinate_scale: float = 1.0,
        label_smoothing: float = 0.05,
    ) -> None:
        super().__init__()
        self.num_classes = num_classes
        self.num_anchors = num_anchors
        self.object_scale = object_scale
        self.no_object_scale = no_object_scale
        self.class_scale = class_scale
        self.coordinate_scale = coordinate_scale
        self.label_smoothing = label_smoothing

    def forward(
        self,
        model: YOLOv2Tiny,
        raw: torch.Tensor,
        targets: list[torch.Tensor],
    ) -> tuple[torch.Tensor, dict[str, float]]:
        decoded = model.decode(raw)
        batch, anchors, height, width, _ = decoded.shape
        device = raw.device

        object_mask = torch.zeros((batch, anchors, height, width), dtype=torch.bool, device=device)
        ignore_mask = torch.zeros_like(object_mask)
        class_target = torch.zeros((batch, anchors, height, width), dtype=torch.long, device=device)
        box_target = torch.zeros(
            (batch, anchors, height, width, 4), dtype=torch.float32, device=device
        )

        anchors_t = model.anchors.to(device)
        for batch_index, target in enumerate(targets):
            for row in target.to(device):
                cx, cy, bw, bh, class_value = row
                class_id = int(class_value.item())
                grid_x = float(cx * width)
                grid_y = float(cy * height)
                cell_x = min(max(int(grid_x), 0), width - 1)
                cell_y = min(max(int(grid_y), 0), height - 1)
                box_wh = torch.tensor([bw * width, bh * height], device=device, dtype=torch.float32)
                anchor_ious = box_iou_wh(box_wh.unsqueeze(0), anchors_t)[0]
                best_anchor = int(anchor_ious.argmax().item())

                object_mask[batch_index, best_anchor, cell_y, cell_x] = True
                class_target[batch_index, best_anchor, cell_y, cell_x] = class_id
                box_target[batch_index, best_anchor, cell_y, cell_x, 0] = grid_x - cell_x
                box_target[batch_index, best_anchor, cell_y, cell_x, 1] = grid_y - cell_y
                box_target[batch_index, best_anchor, cell_y, cell_x, 2] = torch.log(
                    box_wh[0] / anchors_t[best_anchor, 0] + 1e-7
                )
                box_target[batch_index, best_anchor, cell_y, cell_x, 3] = torch.log(
                    box_wh[1] / anchors_t[best_anchor, 1] + 1e-7
                )

                ious = box_iou_wh(
                    box_wh.unsqueeze(0),
                    anchors_t,
                )[0]
                for anchor_index, iou in enumerate(ious):
                    if anchor_index != best_anchor and float(iou) > 0.5:
                        ignore_mask[batch_index, anchor_index, cell_y, cell_x] = True

        no_object_mask = ~object_mask & ~ignore_mask
        objectness = decoded[..., 4]
        object_logits = raw.view(batch, anchors, 5 + self.num_classes, height, width)[
            :, :, 4
        ].permute(0, 1, 2, 3)
        xy_loss = F.mse_loss(
            torch.sigmoid(
                raw.view(batch, anchors, 5 + self.num_classes, height, width)[:, :, 0:2].permute(
                    0, 1, 3, 4, 2
                )[object_mask]
            ),
            box_target[object_mask][:, :2],
            reduction="sum",
        )
        wh_loss = F.mse_loss(
            raw.view(batch, anchors, 5 + self.num_classes, height, width)[:, :, 2:4]
            .permute(0, 1, 3, 4, 2)[object_mask]
            .clamp(-10.0, 10.0),
            box_target[object_mask][:, 2:4],
            reduction="sum",
        )
        object_loss = F.binary_cross_entropy_with_logits(
            object_logits[object_mask],
            torch.ones_like(objectness[object_mask]),
            reduction="sum",
        )
        no_object_loss = F.binary_cross_entropy_with_logits(
            object_logits[no_object_mask],
            torch.zeros_like(objectness[no_object_mask]),
            reduction="sum",
        )
        class_logits = raw.view(batch, anchors, 5 + self.num_classes, height, width)[
            :, :, 5:
        ].permute(0, 1, 3, 4, 2)[object_mask]
        class_loss = F.cross_entropy(
            class_logits,
            class_target[object_mask],
            reduction="sum",
            label_smoothing=self.label_smoothing,
        )

        normalizer = max(batch, 1)
        total = (
            self.coordinate_scale * (xy_loss + wh_loss)
            + self.object_scale * object_loss
            + self.no_object_scale * no_object_loss
            + self.class_scale * class_loss
        ) / normalizer
        components = {
            "xy": float((xy_loss / normalizer).detach()),
            "wh": float((wh_loss / normalizer).detach()),
            "obj": float((object_loss / normalizer).detach()),
            "noobj": float((no_object_loss / normalizer).detach()),
            "cls": float((class_loss / normalizer).detach()),
        }
        return total, components


def box_iou_wh(box_a: torch.Tensor, box_b: torch.Tensor) -> torch.Tensor:
    area_a = box_a[:, 0] * box_a[:, 1]
    area_b = box_b[:, 0] * box_b[:, 1]
    intersection_w = torch.minimum(box_a[:, None, 0], box_b[None, :, 0])
    intersection_h = torch.minimum(box_a[:, None, 1], box_b[None, :, 1])
    intersection = intersection_w * intersection_h
    union = area_a[:, None] + area_b[None, :] - intersection
    return intersection / union.clamp_min(1e-7)
