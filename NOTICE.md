# Third-party attribution

This project is an independent engineering reproduction built around the
YOLOv2 object-detection family. It does not redistribute the Darknet source
tree, MaixPy firmware, vendor drivers or the original training checkpoints.

## Dataset

- Name: **poker cards** (`poker-cards-cxcvz`)
- Publisher: Roboflow Universe / Object Detection
- Source: <https://universe.roboflow.com/object-detection/poker-cards-cxcvz>
- License: **CC BY 4.0**
- Export date recorded by the source bundle: 2022-07-25

The dataset images and labels are not committed to this repository. Users must
obtain the dataset from its publisher and comply with the CC BY 4.0 attribution
requirements.

Selected small, metadata-stripped CC BY 4.0 dataset crops are included under
`docs/images/` solely to document source-label auditing and inference output.
They remain subject to the same source and license.

## Algorithm and pretrained weights

- Redmon and Farhadi, *YOLO9000: Better, Faster, Stronger*:
  <https://arxiv.org/abs/1612.08242>
- Darknet/YOLO: <https://github.com/AlexeyAB/darknet>
- YOLO license notice supplied with the historical source bundle: version 2,
  dated 2016-07-29.

The COCO `yolov2-tiny.weights` file is downloaded locally for initialization
and is not part of this repository.

## Hardware tooling

MaixPy, nncase and K210 firmware are separate projects. Their source,
licenses and release notes remain authoritative; this repository only keeps a
thin application script and deployment instructions.
