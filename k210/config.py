# Generated deployment configuration.
# Rebuild with scripts/generate_k210_config.py.
MODEL_PATH = "/sd/models/yolov2_k210.kmodel"
INPUT_WIDTH = 160
INPUT_HEIGHT = 120
NUM_CLASSES = 52
NUM_ANCHORS = 5
ANCHORS = (
    1.74977827,
    3.59291291,
    2.84562254,
    2.81788826,
    2.54105973,
    3.89533687,
    2.75403380,
    4.70919466,
    3.71267533,
    4.82321167,
)
BOX_THRESHOLD = 0.2500
IDENTITY_THRESHOLD = 0.2000
NMS_THRESHOLD = 0.45
RUN_MODE = "SMOKE"
START_DELAY_MS = 10000
SMOKE_FRAMES = 30
BENCHMARK_WARMUP_FRAMES = 30
BENCHMARK_RUNS = 3
BENCHMARK_FRAMES = 100
STABILITY_SECONDS = 300
HOLDOUT_SCENES = 26
HOLDOUT_WAIT_MS = 10000
HOLDOUT_CAPTURE_FRAMES = 5
HOLDOUT_OUTPUT_DIR = "/sd/holdout"
TARGET_FPS = 5.0
HOLDOUT_TARGET_ACCURACY = 0.70
HOLDOUT_TARGET_COVERAGE = 0.70
HOLDOUT_SLOT_LABELS = (
    "TL",
    "TR",
    "BL",
    "BR",
)
HOLDOUT_LAYOUT = (
    ("2D", "2H", "2S", "2C"),
    ("3C", "3D", "3H", "3S"),
    ("4S", "4C", "4D", "4H"),
    ("5H", "5S", "5C", "5D"),
    ("6D", "6H", "6S", "6C"),
    ("7C", "7D", "7H", "7S"),
    ("8S", "8C", "8D", "8H"),
    ("9H", "9S", "9C", "9D"),
    ("10D", "10H", "10S", "10C"),
    ("JC", "JD", "JH", "JS"),
    ("QS", "QC", "QD", "QH"),
    ("KH", "KS", "KC", "KD"),
    ("AD", "AH", "AS", "AC"),
    ("3H", "2S", "2C", "3D"),
    ("4D", "4H", "3S", "3C"),
    ("4C", "5D", "5H", "4S"),
    ("5S", "5C", "6D", "6H"),
    ("7H", "6S", "6C", "7D"),
    ("8D", "8H", "7S", "7C"),
    ("8C", "9D", "9H", "8S"),
    ("9S", "9C", "10D", "10H"),
    ("JH", "10S", "10C", "JD"),
    ("QD", "QH", "JS", "JC"),
    ("QC", "KD", "KH", "QS"),
    ("KS", "KC", "AD", "AH"),
    ("2H", "AS", "AC", "2D"),
)
CLASS_CODES = (
    "2D",
    "2H",
    "2S",
    "2C",
    "3D",
    "3H",
    "3S",
    "3C",
    "4D",
    "4H",
    "4S",
    "4C",
    "5D",
    "5H",
    "5S",
    "5C",
    "6D",
    "6H",
    "6S",
    "6C",
    "7D",
    "7H",
    "7S",
    "7C",
    "8D",
    "8H",
    "8S",
    "8C",
    "9D",
    "9H",
    "9S",
    "9C",
    "10D",
    "10H",
    "10S",
    "10C",
    "JD",
    "JH",
    "JS",
    "JC",
    "QD",
    "QH",
    "QS",
    "QC",
    "KD",
    "KH",
    "KS",
    "KC",
    "AD",
    "AH",
    "AS",
    "AC",
)
