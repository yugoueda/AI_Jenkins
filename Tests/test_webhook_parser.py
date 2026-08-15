import pytest

from Src.webhook.parser import AiCommand, ReviewCommand, parse


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            "/review 変数名が仕様と一致していない",
            ReviewCommand("変数名が仕様と一致していない", None, None),
        ),
        (
            "/review 変数名が仕様と一致していない\nfile: src/order.py\nline: 88",
            ReviewCommand(
                "変数名が仕様と一致していない", "src/order.py", 88
            ),
        ),
        ("/ai approve R1", AiCommand("approve", "R1")),
        ("/ai apply R1", AiCommand("apply", "R1")),
        ("/ai reject R2", AiCommand("reject", "R2")),
        ("/ai test", AiCommand("test", None)),
        ("/ai review", AiCommand("review", None)),
    ],
)
def test_parse_supported_commands(body, expected) -> None:
    assert parse(body) == expected


@pytest.mark.parametrize(
    "body",
    [
        "ordinary comment",
        "/review",
        "/ai unknown",
        "/ai approve R1 extra",
    ],
)
def test_parse_returns_none_for_unsupported_syntax(body: str) -> None:
    assert parse(body) is None
