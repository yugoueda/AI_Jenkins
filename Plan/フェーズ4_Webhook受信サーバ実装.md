---

## フェーズ4：Webhook受信サーバ実装 作業計画

### 前提条件

- Python 3.11+
- FastAPI 0.100+
- フェーズ1（DB先行）完了済み（`findings` / `job_queue` テーブルが存在すること）
- フェーズ3（CLIエージェント連携）は未完でも可。ジョブをキューに積むまでが本フェーズのスコープ
- `GITLAB_WEBHOOK_SECRET` 環境変数が設定済みであること

---

### 作成ファイル一覧

```
/opt/ai-review/
├── Src/
│   ├── webhook/
│   │   ├── __init__.py
│   │   ├── router.py              # FastAPI ルーター（POST /webhook）
│   │   ├── signature.py           # X-Gitlab-Token 署名検証
│   │   ├── parser.py              # コマンドパーサー（/review / /ai コマンド）
│   │   └── handlers/
│   │       ├── __init__.py
│   │       ├── mr_opened.py       # MR作成イベント（REVIEW ジョブ登録）
│   │       ├── note.py            # コメントイベント（/review, /ai コマンド振り分け）
│   │       └── mr_updated.py      # MR更新イベント（blocking_discussions_resolved）
│   └── main.py                    # FastAPI アプリ本体（ルーター登録）
└── requirements.txt               # fastapi, uvicorn, python-gitlab, httpx
```

---

### アイテム 2-1：Webhookイベント受信機能

**実装ファイル：** `Src/webhook/router.py`

`X-Gitlab-Event` ヘッダーの値でイベント種別を判定し、対応するハンドラへ振り分ける。

| ヘッダー値 | サブアクション | 振り分け先 |
|---|---|---|
| `Merge Request Hook` | `action: opened` | `mr_opened.handle()` |
| `Note Hook` | （コメント本文で判定） | `note.handle()` |
| `Merge Request Hook` | `action: update` + `blocking_discussions_resolved: true` | `mr_updated.handle()` |

```python
# Src/webhook/router.py
from fastapi import APIRouter, Header, Request, HTTPException
from .signature import verify_signature
from .handlers import mr_opened, note, mr_updated

router = APIRouter()

@router.post("/webhook")
async def receive_webhook(
    request: Request,
    x_gitlab_token: str = Header(...),
    x_gitlab_event: str = Header(...),
):
    verify_signature(x_gitlab_token)          # 2-2で実装
    payload = await request.json()

    if x_gitlab_event == "Merge Request Hook":
        action = payload.get("object_attributes", {}).get("action")
        if action == "opened":
            await mr_opened.handle(payload)
        elif action == "update":
            changes = payload.get("changes", {})
            if changes.get("blocking_discussions_resolved", {}).get("current") is True:
                await mr_updated.handle(payload)
    elif x_gitlab_event == "Note Hook":
        await note.handle(payload)

    return {"status": "ok"}
```

---

### アイテム 2-2：Webhook署名検証機能

**実装ファイル：** `Src/webhook/signature.py`

`X-Gitlab-Token` ヘッダーと環境変数 `GITLAB_WEBHOOK_SECRET` を `hmac.compare_digest` で比較する。  
文字列比較には必ず `compare_digest` を使用すること（タイミング攻撃対策）。

```python
# Src/webhook/signature.py
import hmac
import os
from fastapi import HTTPException

def verify_signature(token: str) -> None:
    secret = os.environ["GITLAB_WEBHOOK_SECRET"]
    if not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="Invalid token")
```

---

### アイテム 2-3：コマンドパーサー実装

**実装ファイル：** `Src/webhook/parser.py`

コメント本文を正規表現で解析し、コマンド種別と引数を返す。  
マッチしない場合は `None` を返し、ハンドラ側でスキップする。

```python
# Src/webhook/parser.py
import re
from dataclasses import dataclass
from typing import Literal

REVIEW_PATTERN = re.compile(
    r"^/review\s+(?P<content>.+?)(?:\nfile:\s*(?P<file>.+?))?(?:\nline:\s*(?P<line>\d+))?$",
    re.DOTALL,
)
AI_PATTERN = re.compile(
    r"^/ai\s+(?P<cmd>approve|reject|test)(?:\s+(?P<id>\w+))?",
)

@dataclass
class ReviewCommand:
    content: str
    file: str | None
    line: int | None

@dataclass
class AiCommand:
    cmd: Literal["approve", "reject", "test"]
    finding_id: str | None   # approve / reject 時に必須

def parse(body: str) -> ReviewCommand | AiCommand | None:
    body = body.strip()
    if m := REVIEW_PATTERN.match(body):
        line = int(m.group("line")) if m.group("line") else None
        return ReviewCommand(m.group("content").strip(), m.group("file"), line)
    if m := AI_PATTERN.match(body):
        return AiCommand(m.group("cmd"), m.group("id"))
    return None
```

---

### アイテム 2-4：`/review` コマンド処理

**実装ファイル：** `Src/webhook/handlers/note.py`（`_handle_review()` として実装）

| 処理 | 詳細 |
|---|---|
| DB登録 | 行わない |
| Close管理 | GitLab Discussionを正とし、`blocking_discussions_resolved` で全Closeを判断 |
| 返信コメント | 任意。通常はGitLab上の人間指摘コメントをそのまま扱う |

```python
async def _handle_review(mr_id: str, author: str, cmd: ReviewCommand) -> None:
    # 人間指摘はGitLab Discussionで管理するためDB登録しない
    return
```

---

### アイテム 2-5〜2-7：`/ai` コマンド処理

**実装ファイル：** `Src/webhook/handlers/note.py`（`_handle_ai()` として実装）

各コマンドはジョブキューへの登録のみを行う。実際のCLI実行はフェーズ3・4のワーカーが担当する。

| コマンド | バリデーション | ジョブ登録 | 状態遷移 |
|---|---|---|---|
| `/ai approve <ID>` | ID存在確認・`OPEN` 状態確認・修正パッチ存在確認 | `APPROVE` ジョブ登録 | ワーカー完了後に `APPLIED` |
| `/ai reject <ID>` | ID存在確認 | なし（即時処理） | `REJECTED` に変更 |
| `/ai test` | なし | `UNIT_TEST_GEN` ジョブ登録 | なし |

`/ai approve <ID>` は `.patch` ファイルを参照せず、DBの `findings.fix_patch` / `fix_patch_sha256` を正とする。

```python
async def _handle_ai(mr_id: str, cmd: AiCommand) -> None:
    if cmd.cmd == "approve":
        _get_finding_or_error(mr_id, cmd.finding_id, required_status="OPEN")
        _enqueue(mr_id, "APPROVE", {"finding_id": cmd.finding_id})

    elif cmd.cmd == "reject":
        _get_finding_or_error(mr_id, cmd.finding_id)
        db.execute(
            "UPDATE findings SET status='REJECTED', updated_at=CURRENT_TIMESTAMP "
            "WHERE id=?", (cmd.finding_id,)
        )

    elif cmd.cmd == "test":
        _enqueue(mr_id, "UNIT_TEST_GEN", {})
```

---

### アイテム 2-9：`blocking_discussions_resolved` イベント処理

**実装ファイル：** `Src/webhook/handlers/mr_updated.py`

`blocking_discussions_resolved` が `true` に変化した時点では全Discussionが確かにResolveされているとは限らないため、  
Discussions APIで再確認してから `RE_REVIEW` ジョブを登録する。

```python
# Src/webhook/handlers/mr_updated.py
async def handle(payload: dict) -> None:
    mr_id = str(payload["object_attributes"]["iid"])
    project_id = str(payload["project"]["id"])

    # Discussions API で全Resolve確認（5-2 GitLab連携完了後に有効化）
    all_resolved = await gitlab.all_discussions_resolved(project_id, mr_id)
    if not all_resolved:
        return   # 未Resolveが残っている場合はスキップ

    _enqueue(mr_id, "RE_REVIEW", {"project_id": project_id})
```

---

### アイテム 2-10：エラー時MRコメント返信機能

**実装ファイル：** `Src/webhook/handlers/note.py`（`_post_error()` ヘルパー）

コマンド不正・対象IDが存在しない・状態遷移不正の場合にMRへエラーコメントを投稿する。

| エラー種別 | コメント内容 |
|---|---|
| コマンド構文不正 | `/review` または `/ai approve\|reject\|test` の形式で入力してください |
| ID不存在 | `{ID}` は存在しません |
| 状態遷移不正 | `{ID}` は現在 `{status}` のため `{cmd}` を実行できません |

```python
async def _post_error(mr_id: str, message: str) -> None:
    await gitlab.post_comment(mr_id, f"⚠️ エラー：{message}")
```

各ハンドラは `try/except` で `CommandError` を捕捉し、`_post_error()` を呼び出す。

---

### 実装ステップ

| ステップ | 内容 | 対応アイテム | 依存 |
|---|---|---|---|
| ① | `requirements.txt` に `fastapi`, `uvicorn[standard]`, `python-gitlab`, `httpx` を追加 | 4-1 | なし |
| ② | `Src/main.py` 作成（FastAPI アプリ + ルーター登録） | 4-1 | なし |
| ③ | `Src/webhook/signature.py` 作成・単体テスト | 4-2 | なし |
| ④ | `Src/webhook/parser.py` 作成・単体テスト（各コマンドの正規表現検証） | 4-3 | なし |
| ⑤ | `Src/webhook/router.py` 作成（イベント振り分けのみ、ハンドラはスタブ） | 4-1 | ③ |
| ⑥ | `Src/webhook/handlers/note.py` 作成（`/review` 処理） | 4-4 | ④、DB完了 |
| ⑦ | `Src/webhook/handlers/note.py` に `/ai` コマンド処理を追加 | 4-5〜4-8 | ⑥ |
| ⑧ | `Src/webhook/handlers/mr_opened.py` 作成（`REVIEW` ジョブ登録） | 4-1 | DB完了 |
| ⑨ | `Src/webhook/handlers/mr_updated.py` 作成（`RE_REVIEW` ジョブ登録） | 4-9 | ⑦ |
| ⑩ | `_post_error()` ヘルパー実装・エラーケースを各ハンドラに組み込み | 4-10 | ⑥〜⑨ |
| ⑪ | `uvicorn Src.main:app --host 0.0.0.0 --port 8000` で起動確認 | 4-1 | ①〜⑩ |

> **⚠️ GitLab連携（フェーズ6）完了前の暫定対応：**  
> `gitlab.post_comment()` / `gitlab.all_discussions_resolved()` はスタブ（ログ出力のみ）として実装し、フェーズ6完了後に差し替える。

---

### 実施状況

| ステップ | 状態 | 備考 |
|---|---|---|
| ① | 完了 | `requirements.txt` 更新済み |
| ② | 完了 | `Src/main.py` 作成済み |
| ③ | 完了 | `Src/webhook/signature.py` 作成済み |
| ④ | 完了 | `Src/webhook/parser.py` 作成済み |
| ⑤ | 完了 | `Src/webhook/router.py` 作成済み |
| ⑥ | 完了 | `/review` 処理実装済み |
| ⑦ | 完了 | `/ai approve/reject/test` 処理実装済み |
| ⑧ | 完了 | `MR opened` の `REVIEW` ジョブ登録実装済み |
| ⑨ | 完了 | `blocking_discussions_resolved` の `RE_REVIEW` ジョブ登録実装済み |
| ⑩ | 完了 | エラー返信スタブ実装済み |
| ⑪ | 未実施 | FastAPI依存未導入のWindows環境のため、WSL/コンテナ配置後に起動確認 |
