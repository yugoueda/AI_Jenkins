---

## フェーズ7：Jenkinsパイプライン実装 作業計画

### 前提条件

- フェーズ5のJenkins環境が起動済みであること
- フェーズ6のGitLabコメント投稿機能が利用可能であること
- `BUILD_COMMAND`、`LINT_COMMAND`、`TEST_COMMAND`、`COVERAGE_REPORT_PATH` が環境変数化されていること

### 作成ファイル一覧

```
jenkins/
├── Jenkinsfile.build
├── Jenkinsfile.test
└── scripts/
    ├── gitlab_reporter.py
    └── coverage_lcov.groovy
```

### アイテム別設計

#### 7-1 ビルドパイプライン

- Checkout → Build & Lint → AI Review の順に実行
- Build/Lint結果は成功/失敗に関わらずAIレビューのコンテキストへ含める
- AI ReviewはWebhook受信サーバまたはCLI dispatcher経由で `REVIEW` ジョブを起動
- REVIEWジョブpayloadには `build_result` と `lint_result` を含める

#### 7-2 テスト実行パイプライン

- 既存テスト実行 → LCOV集計 → 目標未達なら `UNIT_TEST_GEN` ジョブ登録
- AI生成完了まで `job_queue` をポーリング
- `MAX_ITER` 到達時は未達結果をMRへ投稿して終了

#### 7-3 JenkinsビルドジョブAPI呼び出し

- Webhook受信サーバからJenkinsのbuild APIを呼び出す
- MR IID、project id、branch、commit shaをパラメータで渡す
- Jenkins起動失敗時はMRへエラーコメント投稿

#### 7-4 カバレッジ取得機能

- `flutter test --coverage` 等でLCOVを生成
- `DA:` からC0、`BRDA:` からC1を算出
- 未実行行を `{file: [line]}` 形式で抽出し、テスト生成ジョブへ渡す

### 実装ステップ

| # | ステップ | 対応アイテム |
|---|---|---|
| 1 | `Jenkinsfile.build` を作成 | 7-1 |
| 2 | `Jenkinsfile.test` を作成 | 7-2 |
| 3 | LCOV解析・未達行抽出処理を共通化 | 7-4 |
| 4 | Webhook受信サーバからJenkins build APIを呼ぶ処理を実装 | 7-3 |
| 5 | カバレッジ結果投稿スクリプトを作成 | 7-2 / 7-4 |
| 6 | Jenkinsジョブの成功・失敗時コメントを確認 | 7-1〜7-4 |
