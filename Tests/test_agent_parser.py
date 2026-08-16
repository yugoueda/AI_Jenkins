import pytest

from Src.agent.parser import parse_and_save_review, parse_and_save_unit_tests


def test_review_parser_accepts_fenced_json(isolated_database) -> None:
    finding_ids = parse_and_save_review(
        "7",
        '```json\n{"findings":[]}\n```',
    )

    assert finding_ids == []


def test_review_parser_rejects_non_json(isolated_database) -> None:
    with pytest.raises(ValueError, match="invalid review JSON"):
        parse_and_save_review("7", "review complete")


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
