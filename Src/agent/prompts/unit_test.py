from ..context import build_diff_context


UNIT_TEST_SYSTEM = """\
あなたはFlutter/Dartのテスト専門エージェントです。
渡された差分+周辺実装とカバレッジ情報をもとに、品質の高いテストコードを生成してください。

## 生成するテストの種別
- Unit Test（常に必須）: flutter_test / test パッケージを使用
- Widget Test（UI変更を含む場合）: testWidgets を使用
- Integration Test は生成対象外

## テスト設計方針
1. バグ再現テスト: 修正前コードで失敗し、修正後で成功するケースを作成
2. 正常系テスト: 主要なユースケースをカバー
3. 境界値テスト: null・空文字・最大値・最小値を網羅
4. 分岐網羅: カバレッジ未達の分岐を優先的にテスト

## 出力制約
- テストファイル単位でコードを出力すること。
- ファイルパスをコメント1行目に記載すること（例: // test/foo_test.dart）
"""


def build_unit_test_prompt(
    mr_id: str,
    changed_files: list[str],
    uncovered_lines: dict[str, list[int]],
) -> str:
    diff_context = build_diff_context(changed_files, event_type="UNIT_TEST_GEN")
    coverage_str = "\n".join(
        f"{path}:{','.join(map(str, lines))}"
        for path, lines in uncovered_lines.items()
    ) or "（未達行なし）"
    return (
        f"{UNIT_TEST_SYSTEM}\n\n"
        f"MR ID: {mr_id}\n\n"
        f"## カバレッジ未達行\n{coverage_str}\n\n"
        f"## 修正内容（diff+周辺実装）\n{diff_context}"
    )
