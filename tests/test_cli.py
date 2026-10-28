from poker_vision.cli import build_parser


def test_all_public_commands_exist() -> None:
    parser = build_parser()
    subparsers_action = next(action for action in parser._actions if action.dest == "command")
    assert set(subparsers_action.choices) == {
        "audit-data",
        "train",
        "evaluate",
        "predict",
        "export",
        "checksums",
    }
