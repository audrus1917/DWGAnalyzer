from parsedwg.utils.args import build_args_parser


def test_build_args_parser_does_not_expose_agent_commands() -> None:
    parser = build_args_parser()

    help_text = parser.format_help()

    assert "agent-run" not in help_text
    assert "agent-status" not in help_text
