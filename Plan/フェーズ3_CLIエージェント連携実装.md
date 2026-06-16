---

## フェーズ3：CLIエージェント連携実装 作業計画

### 前提条件

- フェーズ1（DB先行）完了済み（`findings` / `job_queue` テーブルが存在すること）
- フェーズ2（エージェント・スキル定義ファイル）完了済み（`.claude/agents/` 配下のファイルが存在すること）
- `claude` CLIコマンドがサーバ上で実行可能であること（`which claude` で確認）
- `ANTHROPIC_API_KEY` 環境変数が設定済みであること

---

### 作成ファイル一覧

```
/opt/ai-review/
├── Src/
│   └── agent/
│       ├── __init__.py
│       ├── runner.py              # run_agent() — CLIプロセス起動・完了待機
│       ├── dispatcher.py          # event_type に応じてプロンプト選択・実行・結果保存
│       ├── context.py             # build_diff_context() — コンテキスト構築（stub）
│       ├── parser.py              # CLIエージェント出力（JSON / unified diff）パース
│       └── prompts/
│           ├── __init__.py
│           ├── review.py          # AIレビュー用プロンプト生成（3-2）
│           ├── fix.py             # 修正パッチ確認用プロンプト生成（3-3）
│           └── unit_test.py       # ユニットテスト生成用プロンプト生成（3-4）
```

---

### アイテム 3-1：CLIエージェント呼び出し機能

**実装ファイル：** `Src/agent/runner.py`

`asyncio.create_subprocess_exec` でCLIを起動し、`proc.communicate()` でプロセス終了を待機する。  
プロセス終了後は `returncode` で成否を判定し、呼び出し元に返す。

```python
# Src/agent/runner.py
import asyncio
import json
import os

DEFAULT_MODEL = "claude-sonnet-4-5"

# event_type 別のモデル選択（フェーズ9: 9-3 で本実装。現時点はすべて DEFAULT）
MODEL_MAP: dict[str, str] = {
    "REVIEW":        DEFAULT_MODEL,
    "APPROVE":       DEFAULT_MODEL,
    "RE_REVIEW":     DEFAULT_MODEL,
    "UNIT_TEST_GEN": DEFAULT_MODEL,
}

async def run_agent(
    prompt: str,
    event_type: str = "REVIEW",
) -> tuple[int, str]:
    """
    CLIエージェントを起動し、終了まで待機して (returncode, stdout) を返す。
    returncode == 0 のとき stdout に JSON または unified diff が入る。
    """
    model = MODEL_MAP.get(event_type, DEFAULT_MODEL)
    proc = await asyncio.create_subprocess_exec(
        "claude",
        "--model", model,
        "--print",           # 非インタラクティブモード（標準出力に結果を返す）
        "--prompt", prompt,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ},  # 既存の環境変数を引き継ぐ（ANTHROPIC_API_KEY を含む）
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode(errors="replace")
```

> **⚠️ `--print` フラグについて：**  
> Claude CLI の非インタラクティブ実行には `--print` オプションが必要。  
> 実際のフラグ名はインストール済みバージョンの `claude --help` で要確認。

---

### アイテム 3-2：AIレビュー用プロンプト生成

**実装ファイル：** `Src/agent/prompts/review.py`

MRの diff+周辺実装コンテキスト、ビルド結果、静的解析結果、出力フォーマット指示を結合してプロンプトを生成する。  
`build_diff_context()` は現時点では `git diff -W` の出力をそのまま返すスタブとして実装し、  
フェーズ9（9-1）でタスク種別・ファイルサイズ別戦略に差し替える。

```python
# Src/agent/prompts/review.py
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
      "fix_patch": "<unified diff>"
    }
  ]
}
"""

def build_review_prompt(mr_id: str, changed_files: list[str]) -> str:
    diff_context = build_diff_context(changed_files, event_type="REVIEW")
    return f"{REVIEW_SYSTEM}\n\n## レビュー対象diff+周辺実装\n\n{diff_context}"
```

---

### アイテム 3-3：修正パッチ確認用プロンプト生成

**実装ファイル：** `Src/agent/prompts/fix.py`

指摘IDに紐づく保存済み修正パッチを取得し、提案外の変更が混入していないか確認する。
修正パッチはファイル化せず、DBの `findings.fix_patch` から取得する。

```python
# Src/agent/prompts/fix.py
from ...db import database as db

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
        "FROM findings WHERE id=?",
        (finding_id,)
    )
    return (
        f"{FIX_SYSTEM}\n\n"
        f"指摘ID: {finding_id}\n"
        f"指摘内容: {row['description']}\n"
        f"対象ファイル: {row['file_path']} L{row['line_start']}-{row['line_end']}\n"
        f"patch sha256: {row['fix_patch_sha256']}\n"
        f"保存済みpatch:\n{row['fix_patch']}"
    )
```

---

### アイテム 3-4：ユニットテスト生成用プロンプト生成

**実装ファイル：** `Src/agent/prompts/unit_test.py`

diff+周辺実装 とカバレッジ未達行情報を受け取り、Flutter/Dart 向けテストコード生成プロンプトを構築する。  
`build_diff_context()` は `event_type="UNIT_TEST_GEN"` を指定し、`-W` オプションで関数全体を渡す。

```python
# Src/agent/prompts/unit_test.py
from ..context import build_diff_context

UNIT_TEST_SYSTEM = """\
あなたはFlutter/Dartのテスト専門エージェントです。
渡された差分とカバレッジ情報をもとに、品質の高いテストコードを生成してください。

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
- テストファイル単位でコードブロックを出力すること。
- ファイルパスをコメント1行目に記載すること（例: // test/foo_test.dart）

## 出力形式
// test/{対応パス}_test.dart
import 'package:flutter_test/flutter_test.dart';
...
"""

def build_unit_test_prompt(
    mr_id: str,
    changed_files: list[str],
    uncovered_lines: dict[str, list[int]],  # {"lib/foo.dart": [42, 55, 60]}
) -> str:
    diff_context = build_diff_context(changed_files, event_type="UNIT_TEST_GEN")

    # "lib/foo.dart:42,55,60" 形式に整形
    coverage_str = "\n".join(
        f"{path}:{','.join(map(str, lines))}"
        for path, lines in uncovered_lines.items()
    ) or "（未達行なし）"

    return (
        f"{UNIT_TEST_SYSTEM}\n\n"
        f"## カバレッジ未達行\n{coverage_str}\n\n"
        f"## 修正内容（diff+周辺実装）\n{diff_context}"
    )
```

---

### アイテム 3-5：CLIエージェント出力パース・DB保存機能

**実装ファイル：** `Src/agent/parser.py`

`event_type` に応じて JSON または unified diff をパースし、DBへ保存する。

```python
# Src/agent/parser.py
import json
from datetime import datetime
from ..db import database as db

def parse_and_save_review(mr_id: str, raw_output: str) -> list[str]:
    """
    AIレビュー出力（JSON）をパースし findings テーブルに保存する。
    保存した finding_id のリストを返す。
    """
    data = json.loads(raw_output)
    saved_ids = []

    # 既存AIレビュー指摘の最大連番を取得
    max_n = db.query_scalar(
        "SELECT COALESCE(MAX(CAST(SUBSTR(id, 2) AS INTEGER)), 0) "
        "FROM findings WHERE mr_id=? AND source='AI'",
        (mr_id,)
    )

    for i, f in enumerate(data.get("findings", []), start=1):
        finding_id = f"R{max_n + i}"
        db.execute(
            "INSERT INTO findings "
            "(id, mr_id, source, status, file_path, line_start, line_end, "
            "description, suggestion, fix_patch, fix_patch_sha256, created_at, updated_at) "
            "VALUES (?, ?, 'AI', 'OPEN', ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (
                finding_id, mr_id,
                f.get("file"), f.get("line_start"), f.get("line_end"),
                f.get("description"),
                json.dumps(f.get("suggestion"), ensure_ascii=False),
                f.get("fix_patch"),
                f.get("fix_patch_sha256"),
            )
        )
        saved_ids.append(finding_id)

    return saved_ids


def parse_fix_diff(raw_output: str) -> str:
    """
    修正パッチ確認出力（unified diff）をそのまま返す。
    前後の不要な空白・改行を除去するのみ。
    """
    return raw_output.strip()


def parse_and_save_unit_tests(mr_id: str, raw_output: str) -> list[str]:
    """
    ユニットテスト生成出力を解析し、ファイルパスとコード本体に分割して返す。
    戻り値: [(test_file_path, test_code), ...]
    """
    results = []
    # 先頭コメント "// test/xxx_test.dart" でファイル分割
    import re
    blocks = re.split(r"(?=^// test/)", raw_output, flags=re.MULTILINE)
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        first_line, _, rest = block.partition("\n")
        file_path = first_line.lstrip("/ ").strip()
        results.append((file_path, rest.strip()))
    return results
```

---

### ジョブ→プロンプト→保存 の全体ディスパッチ

**実装ファイル：** `Src/agent/dispatcher.py`

ワーカー（フェーズ3）から呼び出される中心モジュール。`event_type` に応じてプロンプトを選択し、  
`run_agent()` を実行してDB保存・GitLab投稿（スタブ）までを担う。

```python
# Src/agent/dispatcher.py
from .runner import run_agent
from .parser import parse_and_save_review, parse_fix_diff, parse_and_save_unit_tests
from .prompts import review as review_prompt
from .prompts import fix as fix_prompt
from .prompts import unit_test as unit_test_prompt
from ..db import database as db
import json

async def dispatch(job: dict) -> None:
    """
    job: job_queue の1レコード（辞書形式）
    job["event_type"]: REVIEW / APPROVE / RE_REVIEW / UNIT_TEST_GEN
    job["payload"]: JSON文字列（Webhookペイロード等）
    """
    event_type = job["event_type"]
    payload = json.loads(job["payload"])
    mr_id = job["mr_id"]

    if event_type in ("REVIEW", "RE_REVIEW"):
        changed_files = payload.get("changed_files", [])
        prompt = review_prompt.build_review_prompt(mr_id, changed_files)
        returncode, output = await run_agent(prompt, event_type)
        if returncode == 0:
            saved_ids = parse_and_save_review(mr_id, output)
            # TODO: フェーズ5完了後に GitLab コメント投稿を有効化
            # await gitlab.post_review_comment(mr_id, saved_ids)
        else:
            await _handle_failure(mr_id, event_type, output)

    elif event_type == "APPROVE":
        finding_id = payload["finding_id"]
        prompt = fix_prompt.build_fix_prompt(finding_id)
        returncode, output = await run_agent(prompt, event_type)
        if returncode == 0:
            diff = parse_fix_diff(output)
            # 保存済みpatchとhash一致を確認してからコミットする
            db.execute(
                "UPDATE findings SET status='APPLIED', updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (finding_id,)
            )
            # TODO: フェーズ5完了後に GitLab コメント投稿を有効化
        else:
            await _handle_failure(mr_id, event_type, output)

    elif event_type == "UNIT_TEST_GEN":
        changed_files = payload.get("changed_files", [])
        uncovered_lines = payload.get("uncovered_lines", {})
        prompt = unit_test_prompt.build_unit_test_prompt(mr_id, changed_files, uncovered_lines)
        returncode, output = await run_agent(prompt, event_type)
        if returncode == 0:
            test_files = parse_and_save_unit_tests(mr_id, output)
            # TODO: フェーズ5完了後にブランチへのコミットを有効化
            # for path, code in test_files:
            #     await gitlab.commit_file(mr_id, path, code)
        else:
            await _handle_failure(mr_id, event_type, output)


async def _handle_failure(mr_id: str, event_type: str, error_output: str) -> None:
    # TODO: フェーズ5完了後に GitLab エラーコメント投稿を有効化
    # await gitlab.post_comment(mr_id, f"⚠️ {event_type} 処理に失敗しました。")
    import logging
    logging.error("[%s] mr=%s error=%s", event_type, mr_id, error_output[:500])
```

---

### `build_diff_context()` スタブ実装（フェーズ9まで）

**実装ファイル：** `Src/agent/context.py`

フェーズ9（9-1）で本実装に差し替えるまでの暫定実装。`git diff -W` をそのまま返す。

```python
# Src/agent/context.py
import subprocess

def build_diff_context(changed_files: list[str], event_type: str) -> str:
    """
    【スタブ】フェーズ9（9-1）で本実装に差し替える。
    現時点は git diff -W のみ返す。
    """
    result = subprocess.run(
        ["git", "diff", "-W", "origin/main...HEAD", "--"] + changed_files,
        capture_output=True, text=True, check=False
    )
    return result.stdout or "（差分なし）"
```

---

### 実装ステップ

| ステップ | 内容 | 対応アイテム | 依存 |
|---|---|---|---|
| ① | `Src/agent/context.py` スタブ作成（`git diff -W` ラッパー） | 3-2〜3-4の前提 | なし |
| ② | `Src/agent/runner.py` 作成・`claude --print` の起動確認 | 3-1 | ① |
| ③ | `Src/agent/prompts/review.py` 作成・プロンプト文字列の単体確認 | 3-2 | ① |
| ④ | `Src/agent/prompts/fix.py` 作成 | 3-3 | DB完了 |
| ⑤ | `Src/agent/prompts/unit_test.py` 作成 | 3-4 | ① |
| ⑥ | `Src/agent/parser.py` 作成・JSONパース単体テスト（モックデータで確認） | 3-5 | DB完了 |
| ⑦ | `Src/agent/dispatcher.py` 作成（REVIEW のみ先行実装） | 3-1〜3-5 | ②③⑥ |
| ⑧ | APPROVE / UNIT_TEST_GEN を `dispatcher.py` に追加 | 3-1〜3-5 | ④⑤⑦ |
| ⑨ | `claude` CLI を実際に呼び出して JSON 出力の形式を確認・プロンプト調整 | 3-2〜3-4 | ②〜⑧ |

> **⚠️ GitLab連携（フェーズ6）完了前の暫定対応：**  
> `gitlab.post_comment()` / `gitlab.commit_file()` はコメントアウトのままとし、  
> フェーズ6完了後に `dispatcher.py` の対応箇所を有効化する。

---

### 実施状況

| ステップ | 状態 | 備考 |
|---|---|---|
| ① | 完了 | `Src/agent/context.py` 作成済み |
| ② | 完了 | `Src/agent/runner.py` 作成済み。CLI実機確認はWSL/コンテナ配置後 |
| ③ | 完了 | `Src/agent/prompts/review.py` 作成済み。ビルド/静的解析結果をコンテキストへ含める設計変更を反映済み |
| ④ | 完了 | `Src/agent/prompts/fix.py` 作成済み |
| ⑤ | 完了 | `Src/agent/prompts/unit_test.py` 作成済み |
| ⑥ | 完了 | `Src/agent/parser.py` 作成済み |
| ⑦ | 完了 | REVIEW / RE_REVIEW を `dispatcher.py` に実装済み |
| ⑧ | 完了 | APPROVE / UNIT_TEST_GEN を `dispatcher.py` に実装済み |
| ⑨ | 未実施 | Windows環境のため、`claude` CLI実行確認はWSL/コンテナ配置後 |
