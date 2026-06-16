from ...db.Src import database as db


FIX_SYSTEM = """\
あなたはFlutter/Dartコードの修正パッチ検証エージェントです。
渡された指摘IDに紐づく保存済みpatchが、指摘内容の解消に必要な最小変更のみを含むか確認してください。

## 確認方針
1. 指摘IDに対応しない変更が含まれていないこと
2. patch本文のsha256がDB保存値と一致すること
3. 問題がなければ保存済みpatchのみを返すこと

## 出力制約
- unified diff 形式のみ出力すること。説明文・前置き・後書きは含めない。
- コードブロック（```diff）で囲まない。生のdiffを返すこと。
"""


def build_fix_prompt(finding_id: str) -> str:
    row = db.query_one(
        "SELECT file_path, line_start, line_end, description, fix_patch, fix_patch_sha256 "
        "FROM findings WHERE id=:finding_id",
        {"finding_id": finding_id},
    )
    if row is None:
        raise ValueError(f"finding not found: {finding_id}")

    return (
        f"{FIX_SYSTEM}\n\n"
        f"指摘ID: {finding_id}\n"
        f"指摘内容: {row['description']}\n"
        f"対象ファイル: {row['file_path']} L{row['line_start']}-{row['line_end']}\n"
        f"patch sha256: {row['fix_patch_sha256']}\n"
        f"保存済みpatch:\n{row['fix_patch']}"
    )
