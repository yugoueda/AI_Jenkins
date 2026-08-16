# TODO：Webhook以降の実環境E2E確認

実装とローカル自動テストは完了済み。以下は実GitLab・JenkinsのCredentialが必要なため、
環境準備後に実施する。

- [x] `.env`へ`GITLAB_URL`、`GITLAB_TOKEN`、`JENKINS_USER`、`JENKINS_TOKEN`、`JENKINS_CALLBACK_TOKEN`を設定
- [x] JenkinsへGitLab Checkout用Credential（既定ID：`gitlab-token`）を登録
- [x] 更新イメージで`jenkins`、`webhook`、`worker`を再作成し、2つのPipelineジョブが存在することを確認
- [x] GitLabプロジェクトへMerge Request HookとNote Hookを登録
- [x] AIレビューの上限を`CLAUDE_MAX_TURNS=30`へ見直し、MR !3で`/ai review`を再実行して指摘保存・コメント投稿まで確認
- [x] MR !3でBuild/Lint成功 → AIレビューコメント投稿を確認
- [x] MR !3で`/ai approve R1` → 修正コミット作成を確認
- [x] 最後の指摘適用後にWeb再ビルド → 再レビューが起動することを確認（新規R2を検出）
- [x] `/ai test` → テスト生成コミット → Jenkinsテスト → 失敗結果のMR通知を確認
- [ ] 全Discussion Resolve → 再レビュー → テスト生成 → Jenkinsテスト → C0/C1投稿を確認
- [ ] Build/Lint/CLI/GitLab APIの各失敗系で、ジョブ状態とMR通知を確認

Webhookの外部公開を行う場合は、`Plan/全体アクションアイテム.md`の5-6〜5-9
（ngrok、入力制限、重複排除、異常系運用手順）も併せて実施する。
