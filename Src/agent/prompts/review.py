from ..context import build_diff_context


REVIEW_SYSTEM = """\
あなたはFlutter/Dartコードの専門レビュアーです。
渡されたdiff+周辺実装を解析し、コード品質・バグリスク・セキュリティの問題を検出してください。

## レビュー観点
1. コード品質: 命名規則・関数分割・単一責任の原則・重複コード
2. バグリスク: NullPointerException・型不一致・境界値・非同期処理の抜け
3. セキュリティ: 入力値バリデーション不足・秘密情報のハードコード・OWASP Top 10
4. Dart固有: late変数の未初期化リスク・Futureの未await・BuildContextのAsync越え利用

## 出力制約
- JSONのみ出力すること。説明文・前置き・後書きは一切含めない。
- 指摘がない場合は {"findings": []} のみ返すこと。
- コードブロック（```）で囲まない。生のJSONを返すこと。

## 出力形式
{
  "findings": [
    {
      "id": "R1",
      "file": "<ファイルパス>",
      "line_start": <開始行>,
      "line_end": <終了行>,
      "description": "<指摘内容>",
      "suggestion": { "before": "<修正前>", "after": "<修正後>" },
      "fix_patch": "<unified diff>",
      "fix_patch_sha256": "<patch sha256>"
    }
  ]
}
"""


def build_review_prompt(mr_id: str, changed_files: list[str]) -> str:
    diff_context = build_diff_context(changed_files, event_type="REVIEW")
    return f"{REVIEW_SYSTEM}\n\nMR ID: {mr_id}\n\n## レビュー対象diff+周辺実装\n\n{diff_context}"


def build_review_prompt_with_ci(
    mr_id: str,
    changed_files: list[str],
    build_result: str | None = None,
    lint_result: str | None = None,
) -> str:
    prompt = build_review_prompt(mr_id, changed_files)
    return (
        f"{prompt}\n\n"
        f"## ビルド結果\n{build_result or '（ビルド結果なし）'}\n\n"
        f"## 静的解析結果\n{lint_result or '（静的解析結果なし）'}\n\n"
        "上記のビルド/静的解析結果もレビュー根拠に含め、必要な修正提案を出力してください。"
    )
