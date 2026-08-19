import pytest

from Src.agent.parser import parse_and_save_review, parse_and_save_unit_tests
from Src.agent.prompts.review import REVIEW_SYSTEM


def test_review_parser_accepts_fenced_json(isolated_database) -> None:
    finding_ids = parse_and_save_review(
        "7",
        '```json\n{"findings":[]}\n```',
    )

    assert finding_ids == []


def test_review_parser_accepts_json_surrounded_by_prose(isolated_database) -> None:
    finding_ids = parse_and_save_review(
        "7",
        'Review complete.\n{"findings":[]}\nThat is all.',
    )

    assert finding_ids == []


def test_review_parser_accepts_fenced_json_after_prose(isolated_database) -> None:
    finding_ids = parse_and_save_review(
        "7",
        'Review result:\n```JSON\n{"findings":[]}\n```\nDone.',
    )

    assert finding_ids == []


def test_review_parser_skips_unrelated_object_before_review_json(
    isolated_database,
) -> None:
    finding_ids = parse_and_save_review(
        "7",
        'metadata: {"status":"complete"}\nresult: {"findings":[]}',
    )

    assert finding_ids == []


def test_review_parser_rejects_non_json(isolated_database) -> None:
    with pytest.raises(ValueError, match="invalid review JSON"):
        parse_and_save_review("7", "review complete")


def test_review_parser_restarts_finding_numbers_for_each_mr(
    isolated_database,
) -> None:
    review = '{"findings":[{"id":"ignored","description":"日本語の指摘"}]}'

    assert parse_and_save_review("7", review) == ["R1"]
    assert parse_and_save_review("8", review) == ["R1"]
    assert parse_and_save_review("7", review) == ["R2"]


def test_review_prompt_requires_japanese_findings() -> None:
    assert "description` は必ず自然な日本語で記述すること" in REVIEW_SYSTEM


def test_unit_test_parser_ignores_markdown_fences() -> None:
    output = """Generated tests:
```dart
// test/example_test.dart
void main() {}
```
"""

    assert parse_and_save_unit_tests("7", output) == [
        ("test/example_test.dart", "void main() {}")
    ]


def test_unit_test_parser_does_not_leak_fences_between_files() -> None:
    output = """```dart
// test/first_test.dart
void first() {}
```

```DART
// test/second_test.dart
void second() {}
```
"""

    assert parse_and_save_unit_tests("7", output) == [
        ("test/first_test.dart", "void first() {}"),
        ("test/second_test.dart", "void second() {}"),
    ]
