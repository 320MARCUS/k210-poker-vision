from pathlib import Path

from poker_vision.classes import load_catalog

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_is_52_cards_and_source_map_is_complete() -> None:
    catalog = load_catalog(ROOT / "configs" / "classes.json")
    assert catalog.num_classes == 52
    assert len(catalog.names) == len(set(catalog.names)) == 52
    assert sorted(catalog.source_id_to_code) == list(range(53))
    assert catalog.source_id_to_code[19] is None
    assert catalog.source_id_to_code[20] == "10D"
    assert catalog.source_id_to_code[52] == "QC"


def test_known_shifted_source_ids() -> None:
    catalog = load_catalog(ROOT / "configs" / "classes.json")
    assert catalog.source_to_canonical(0) == catalog.code_to_id["10H"]
    assert catalog.source_to_canonical(18) == catalog.code_to_id["5C"]
    assert catalog.source_to_canonical(19) is None
    assert catalog.source_to_canonical(20) == catalog.code_to_id["10D"]
    assert catalog.source_to_canonical(21) == catalog.code_to_id["6D"]
