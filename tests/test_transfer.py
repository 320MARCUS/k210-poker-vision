from __future__ import annotations

import torch
from torch import nn

from poker_vision.train import load_prefix_compatible_state


def test_load_prefix_compatible_state_slices_and_skips() -> None:
    model = nn.Sequential(nn.Linear(4, 2), nn.BatchNorm1d(2), nn.Linear(2, 3))
    source = {
        "0.weight": torch.arange(24, dtype=torch.float32).reshape(4, 6),
        "0.bias": torch.arange(6, dtype=torch.float32),
        "1.weight": torch.arange(6, dtype=torch.float32),
        "1.bias": torch.arange(6, dtype=torch.float32),
        "1.running_mean": torch.arange(6, dtype=torch.float32),
        "1.running_var": torch.arange(6, dtype=torch.float32) + 1,
        "1.num_batches_tracked": torch.tensor(7),
        "2.weight": torch.arange(18, dtype=torch.float32).reshape(3, 6),
        "2.bias": torch.arange(3, dtype=torch.float32),
    }

    copied, skipped = load_prefix_compatible_state(model, source)

    assert copied == 9
    assert skipped == 0
    assert torch.equal(model[0].weight, source["0.weight"][:2, :4])
    assert torch.equal(model[1].running_mean, source["1.running_mean"][:2])
    assert torch.equal(model[2].weight, source["2.weight"][:, :2])


def test_load_prefix_compatible_state_skips_rank_mismatch() -> None:
    model = nn.Linear(2, 2)
    copied, skipped = load_prefix_compatible_state(
        model,
        {"weight": torch.zeros(2, 2, 1), "bias": torch.zeros(2)},
    )
    assert copied == 1
    assert skipped == 1
