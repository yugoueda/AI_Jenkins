---

## フェーズ6：GitLab連携実装 作業計画

### 前提条件

- フェーズ4のWebhookコマンド処理が実装済みであること
- `GITLAB_URL`、`GITLAB_TOKEN` が環境変数で設定済みであること
- API失敗時はMRコメントまたはジョブ失敗状態で通知できること

### 作成ファイル一覧

```
src/gitlab/
├── client.py
├── comments.py
├── discussions.py
└── commits.py
```

### アイテム別設計

#### 6-1 MRコメント投稿機能

- `POST /projects/:id/merge_requests/:mr_iid/notes` を使用
- AIレビュー結果は設計書§7.2のMarkdown形式へ変換
- `finding_id`、対象ファイル、行番号、指摘、修正提案を含める
- 投稿失敗時は対象ジョブを `FAILED` に更新

#### 6-2 Discussions API連携

- `GET /projects/:id/merge_requests/:mr_iid/discussions` を使用
- `blocking_discussions_resolved` 受信後、全discussionのresolved状態を再確認
- 未Resolveが残る場合は再レビューを起動しない
- 全Resolveなら `RE_REVIEW` ジョブを登録

#### 6-3 ブランチへの修正コミット機能

- 第一候補: `POST /projects/:id/repository/commits`
- 代替: 作業ディレクトリでpatch適用後に `git push`
- コミットメッセージに指摘IDを含める
- `/ai approve <ID>` の対象findingのみコミットする

### 実装ステップ

| # | ステップ | 対応アイテム |
|---|---|---|
| 1 | GitLab API共通clientを作成（URL、token、timeout、エラー処理） | 6-1〜6-3 |
| 2 | AIレビュー結果のMarkdown整形関数を実装 | 6-1 |
| 3 | MR note投稿処理を実装 | 6-1 |
| 4 | discussions取得と全Resolve判定を実装 | 6-2 |
| 5 | commit APIまたはgit pushによる修正コミット処理を実装 | 6-3 |
| 6 | Webhook handler / dispatcher からGitLab連携を呼び出す | 6-1〜6-3 |

### 実装結果（2026-08-15）

- `Src/gitlab/` に共通HTTPクライアント、コメント、Discussions、権限確認、Commits API連携を実装
- AIレビュー結果を設計書 §7.2 のMarkdown形式でMRへ投稿
- `/ai apply` は保存済み差分を提示し、`/ai approve` はハッシュを再検証してCommits APIで反映
- AIコマンドはGitLab Developer以上に制限（`GITLAB_ENFORCE_COMMAND_ROLES=true`が既定）
- 単体テストはモックAPIで確認済み。実GitLabとの疎通確認は接続情報設定後に実施する
