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

## Flutter Widget Testの必須条件
- `showDialog`、`Navigator`、`ScaffoldMessenger`を呼ぶ場合は、`MaterialApp`配下の
  `Builder`が提供する`BuildContext`を使用する。`MaterialApp`を返すStatefulWidget自身の
  `BuildContext`を渡してはいけない。
- 対象アプリの`pubspec.yaml`にある既存アセットだけを参照する。存在しない画像名を
  テストデータへ設定せず、不要なら画像を描画しないテストデータを選ぶ。
- 画面幅に依存するWidgetを描画する場合は、テスト開始時に十分な`tester.view.physicalSize`を
  設定し、`addTearDown`で`resetPhysicalSize`と`resetDevicePixelRatio`を必ず呼ぶ。
- `MaterialApp`には対象アプリが要求するローカライゼーションdelegateとsupportedLocalesを
  設定し、生成後にダイアログ・アセット・RenderFlex overflowが起きないことを確認する。

## 出力制約
- 作業ツリーや一時ファイルを作成・変更しない。Write/Edit系ツールを使用しない。
- 生成したテストコードは必ず標準出力へ返す。説明文は含めない。
- テストファイル単位でコードを出力する。
- 各ファイルの1行目は必ずパスコメントにする（例: // test/foo_test.dart）。
- Markdownコードブロック（```）で囲まない。
- 各ファイルは単独でコンパイル可能な完全なDartソースにする。
- MapEntryなど同値演算子を実装していない型をオブジェクト同士で比較せず、key/valueや各プロパティを検証する。
- 実装されていない仕様を仮定せず、提示された実装と公開APIだけを使用する。
"""


def build_unit_test_prompt(
    mr_id: str,
    changed_files: list[str],
    uncovered_lines: dict[str, list[int]],
    working_directory: str | None = None,
    target_branch: str = "main",
) -> str:
    diff_context = build_diff_context(
        changed_files,
        event_type="UNIT_TEST_GEN",
        working_directory=working_directory,
        target_branch=target_branch,
    )
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
