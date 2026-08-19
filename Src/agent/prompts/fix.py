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


def build_fix_prompt(mr_id: str, finding_id: str) -> str:
    row = db.query_one(
        "SELECT file_path, line_start, line_end, description, fix_patch, fix_patch_sha256 "
        "FROM findings WHERE mr_id=:mr_id AND id=:finding_id",
        {"mr_id": mr_id, "finding_id": finding_id},
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


PATCH_REBASE_SYSTEM = """\
あなたはFlutter/Dartコードの修正パッチを最新ブランチへ再構成するエージェントです。
保存済みpatchは、先に承認された別の修正によって文脈が変化したため適用できません。
現在の作業ツリーを読み取り、元の指摘を解消する同等かつ最小のunified diffを作成してください。

## 厳守事項
1. 元の指摘と無関係な変更を含めないこと
2. 指定された対象ファイル以外を変更しないこと
3. 作業ツリーと一時ファイルを作成・変更しないこと

## 出力制約
- unified diff形式のみ出力すること。説明文・前置き・後書きは含めない。
- コードブロック（```diff）で囲まない。生のdiffを返すこと。
"""


def build_patch_rebase_prompt(
    finding_id: str,
    description: str,
    file_paths: list[str],
    patch: str,
) -> str:
    return (
        f"{PATCH_REBASE_SYSTEM}\n\n"
        f"指摘ID: {finding_id}\n"
        f"指摘内容: {description}\n"
        f"変更を許可するファイル: {', '.join(file_paths)}\n\n"
        f"元の保存済みpatch:\n{patch}"
    )
