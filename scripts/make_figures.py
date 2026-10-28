from __future__ import annotations

import argparse
import json
from pathlib import Path
from xml.sax.saxutils import escape


def training_curve(history_path: Path, output: Path) -> None:
    rows = [
        json.loads(line)
        for line in history_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    epochs = [row["epoch"] for row in rows]
    valid = [row["valid_loss"] for row in rows]
    mappro = [row["valid_mAP50"] for row in rows]
    width, height = 1200, 680
    margin_left, margin_right = 100, 70
    margin_top, margin_bottom = 100, 90
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    max_loss = max(valid) * 1.08 if valid else 1.0

    def loss_points() -> str:
        return " ".join(
            f"{margin_left + (epoch - epochs[0]) / max(epochs[-1] - epochs[0], 1) * plot_w:.2f},"
            f"{margin_top + plot_h - value / max_loss * plot_h:.2f}"
            for epoch, value in zip(epochs, valid, strict=True)
        )

    def map_points() -> str:
        return " ".join(
            f"{margin_left + (epoch - epochs[0]) / max(epochs[-1] - epochs[0], 1) * plot_w:.2f},"
            f"{margin_top + plot_h - value * plot_h:.2f}"
            for epoch, value in zip(epochs, mappro, strict=True)
        )

    grid = []
    for index in range(6):
        y = margin_top + index * plot_h / 5
        grid.append(
            f'<line x1="{margin_left}" y1="{y:.1f}" x2="{margin_left + plot_w}" '
            f'y2="{y:.1f}" stroke="#294257" stroke-width="1"/>'
        )
    text_style = 'fill="#91aec1" font-family="Segoe UI, Arial"'
    title_style = 'fill="#f4f7fb" font-family="Segoe UI, Arial" font-size="32"'
    svg = "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
            '<rect width="100%" height="100%" fill="#081722"/>',
            (
                f'<text x="{margin_left}" y="48" {title_style} '
                'font-weight="700">Training evidence</text>'
            ),
            (
                f'<text x="{margin_left}" y="80" {text_style} font-size="18">'
                "checkpoint selection uses validation mAP@0.50</text>"
            ),
            (
                f'<rect x="{margin_left}" y="{margin_top}" width="{plot_w}" '
                f'height="{plot_h}" fill="#0d2232" stroke="#294257"/>'
            ),
            "".join(grid),
            (f'<polyline points="{loss_points()}" fill="none" stroke="#e8845d" stroke-width="4"/>'),
            (f'<polyline points="{map_points()}" fill="none" stroke="#4ac6b7" stroke-width="4"/>'),
            f'<circle cx="{margin_left + plot_w - 310}" cy="112" r="6" fill="#e8845d"/>',
            (
                f'<text x="{margin_left + plot_w - 294}" y="118" fill="#e8845d" '
                'font-family="Segoe UI, Arial" font-size="18">valid loss</text>'
            ),
            f'<circle cx="{margin_left + plot_w - 160}" cy="112" r="6" fill="#4ac6b7"/>',
            (
                f'<text x="{margin_left + plot_w - 144}" y="118" fill="#4ac6b7" '
                'font-family="Segoe UI, Arial" font-size="18">valid mAP50</text>'
            ),
            (
                f'<text x="{margin_left}" y="{height - 35}" {text_style} '
                'font-size="17">epoch 1</text>'
            ),
            (
                f'<text x="{margin_left + plot_w}" y="{height - 35}" '
                f'text-anchor="end" {text_style} font-size="17">'
                f"epoch {epochs[-1] if epochs else 0}</text>"
            ),
            "</svg>",
        ]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg, encoding="utf-8")


def per_class_chart(metrics_path: Path, output: Path) -> None:
    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    values = [item for item in payload["metrics"]["per_class"] if item["ap50"] is not None]
    width, height = 1400, 720
    left, right, top, bottom = 90, 40, 110, 100
    plot_w = width - left - right
    plot_h = height - top - bottom
    bar_width = plot_w / max(len(values), 1)
    bars = []
    labels = []
    for index, item in enumerate(values):
        value = max(0.0, min(1.0, float(item["ap50"])))
        x = left + index * bar_width + bar_width * 0.12
        bar_h = value * plot_h
        y = top + plot_h - bar_h
        bars.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_width * 0.76:.2f}" '
            f'height="{bar_h:.2f}" fill="#4ac6b7"/>'
        )
        labels.append(
            f'<text x="{left + (index + 0.5) * bar_width:.2f}" '
            f'y="{height - 48}" text-anchor="end" fill="#b9cbd7" '
            f'font-family="Segoe UI, Arial" font-size="12" '
            f'transform="rotate(-55 {left + (index + 0.5) * bar_width:.2f},{height - 48})">'
            f"{escape(str(item['code']))}</text>"
        )
    svg = "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
            '<rect width="100%" height="100%" fill="#081722"/>',
            (
                f'<text x="{left}" y="48" fill="#f4f7fb" '
                'font-family="Segoe UI, Arial" font-size="32" '
                'font-weight="700">Per-class AP@0.50</text>'
            ),
            (
                f'<text x="{left}" y="80" fill="#91aec1" '
                'font-family="Segoe UI, Arial" font-size="18">'
                "reviewed 52-class test split</text>"
            ),
            (
                f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" '
                f'y2="{top + plot_h}" stroke="#91aec1"/>'
            ),
            (f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#91aec1"/>'),
            "".join(bars),
            "".join(labels),
            "</svg>",
        ]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", required=True)
    parser.add_argument("--metrics", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    training_curve(Path(args.history), output_dir / "training_curve.svg")
    per_class_chart(Path(args.metrics), output_dir / "per_class_ap50.svg")


if __name__ == "__main__":
    main()
