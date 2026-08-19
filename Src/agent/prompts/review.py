from ..context import build_diff_context


REVIEW_SYSTEM = """\
あなたはFlutter/Dartコードの専門レビュアーです。
渡されたdiffを解析し、コード品質・バグリスク・セキュリティの問題を検出してください。

## レビュー観点
1. コード品質: 命名規則・関数分割・単一責任の原則・重複コード
2. バグリスク: NullPointerException・型不一致・境界値・非同期処理の抜け
3. セキュリティ: 入力値バリデーション不足・秘密情報のハードコード・OWASP Top 10
4. Dart固有: late変数の未初期化リスク・Futureの未await・BuildContextのAsync越え利用

## 出力制約
- JSONのみ出力すること。説明文・前置き・後書きは一切含めない。
- 指摘がない場合は {"findings": []} のみ返すこと。
- `description` は必ず自然な日本語で記述すること。`suggestion`内のコード、ファイルパス、識別子は原文のまま保持すること。
- コードブロック（```）で囲まない。生のJSONを返すこと。
- 作業ツリーと一時ファイルは作成・変更しない。必要な調査は読み取りのみで行う。
- `fix_patch_sha256`はサーバー側で計算するため、ハッシュ計算は行わない。

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
      "fix_patch": "<unified diff>"
    }
  ]
}
"""


def build_review_prompt(
    mr_id: str,
    changed_files: list[str],
    working_directory: str | None = None,
    target_branch: str = "main",
    base_commit: str | None = None,
) -> str:
    diff_context = build_diff_context(
        changed_files,
        event_type="REVIEW",
        working_directory=working_directory,
        target_branch=target_branch,
        base_commit=base_commit,
    )
    return f"{REVIEW_SYSTEM}\n\nMR ID: {mr_id}\n\n## レビュー対象diff\n\n{diff_context}"


def build_review_prompt_with_ci(
    mr_id: str,
    changed_files: list[str],
    build_result: str | None = None,
    lint_result: str | None = None,
    working_directory: str | None = None,
    target_branch: str = "main",
    base_commit: str | None = None,
) -> str:
    prompt = build_review_prompt(
        mr_id,
        changed_files,
        working_directory,
        target_branch,
        base_commit,
    )
    return (
        f"{prompt}\n\n"
        f"## ビルド結果\n{build_result or '（ビルド結果なし）'}\n\n"
        f"## 静的解析結果\n{lint_result or '（静的解析結果なし）'}\n\n"
        "上記のビルド/静的解析結果もレビュー根拠に含め、必要な修正提案を出力してください。"
    )
