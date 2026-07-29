# Claude Code CLIエージェント導入手順

## 1. 構成

Claude Codeを含む専用Dockerイメージを使い、次のサービスを`agent`プロファイルで
起動します。

- `webhook`: GitLab Webhookを受信してジョブをDBへ登録
- `worker`: 待機中のジョブを1件ずつ取得し、Claude Code CLIを非対話で実行
- `agent-init`: DBマイグレーションとvolumeの初期化

Claude ProまたはMax契約ではAPIキーは不要です。workerコンテナ内でClaude Codeへ
対話ログインします。認証状態は`ai-jenkins_claude-home`というDocker named volume
に保存され、workerコンテナの再作成後も維持されます。

認証情報はイメージ、Gitリポジトリ、配布バンドルには含めません。別PCへ導入した
場合は、そのPCで一度アカウント認証を行います。

## 2. 初回セットアップ

リポジトリ直下で環境ファイルとエージェントイメージを用意します。

```bash
cp .env.example .env
./scripts/agent-image.sh build
```

`.env`の`GITLAB_WEBHOOK_SECRET`を推測されにくい値へ変更してください。
Pro/Maxログインを使う場合、次の2項目は空のままにします。

```dotenv
CLAUDE_CODE_OAUTH_TOKEN=
ANTHROPIC_API_KEY=
```

サービスを起動し、workerコンテナへ入ります。

```bash
docker compose --profile agent up -d --no-build --wait
docker compose --profile agent exec worker bash
```

コンテナ内でClaude Codeが利用可能か確認します。配布イメージにはインストール済み
なので、通常はバージョンが表示されます。

```bash
claude --version
```

コマンドが存在しない場合だけ、コンテナ内で公式インストーラーを実行します。

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

続けてClaude Codeを起動します。

```bash
claude
```

画面に表示されたURLをWindows側のブラウザで開き、Claude Pro/Maxを契約した
アカウントを認証します。ブラウザに認証コードが表示された場合は、Claude Codeが
待機しているコンテナのターミナルへ貼り付けます。

ログイン後、Claude Codeを終了して認証状態と疎通を確認します。

```bash
claude auth status --text
claude --print --max-turns 1 "OKとのみ回答してください"
exit
```

ホスト側からも確認します。

```bash
docker compose --profile agent exec worker claude auth status --text
docker compose --profile agent run --rm --no-deps worker \
  claude --print --max-turns 1 "OKとのみ回答してください"
```

`Login method: Claude Pro account`と`OK`が表示されればセットアップ完了です。
対話画面を使わず直接ログイン処理を開始する場合は、ホスト側から
`./scripts/claude-login.sh login`を実行しても同じ認証volumeへ保存されます。

## 3. 起動と確認

```bash
docker compose --profile agent up -d --no-build --wait
docker compose --profile agent ps
```

Claude Code単体の疎通確認は次で行います。このコマンドは契約の利用枠を消費します。

```bash
docker compose --profile agent run --rm --no-deps worker \
  claude --print --max-turns 1 "OKとのみ回答してください"
```

Webhookとworkerのログは次で確認できます。

```bash
docker compose --profile agent logs -f webhook worker
```

初期値ではWebhookは`127.0.0.1:8000`のみで待ち受けます。GitLabから直接到達させる
場合は、`.env`の`WEBHOOK_HTTP_HOST`を変更し、リバースプロキシでTLSとアクセス制限を
設定してください。

## 4. 停止・再起動・ログアウト

```bash
# 停止。DB、作業領域、volume内のClaude認証は保持
docker compose --profile agent down

# 再起動
docker compose --profile agent up -d --no-build --wait

# 認証状態の確認
./scripts/claude-login.sh status

# volumeへ保存した対話ログインを解除
./scripts/claude-login.sh logout
```

`docker compose down -v`はJenkinsデータ、ジョブDB、Claude認証を含む全named volumeを
削除するため、通常運用では実行しないでください。

## 5. 別PCへ導入

### Container Registryを使う場合

配布元の`.env`へRegistry上のイメージ名を設定します。

```dotenv
AGENT_IMAGE=registry.example.com/your-team/ai-agent:2.1.220-1
```

ログイン後にビルド・pushします。

```bash
docker login registry.example.com
./scripts/agent-image.sh push
```

導入先でリポジトリ一式を配置してイメージを取得し、アカウント認証します。

```bash
cp .env.example .env
docker compose --profile agent pull
./scripts/claude-login.sh login
docker compose --profile agent up -d --no-build --wait
```

### オフラインバンドルを使う場合

`./scripts/export-jenkins-bundle.sh`で作成したバンドルには、Jenkins、DinD、
Claude Codeエージェントの各イメージが含まれます。導入先で`./install.sh`を実行後、
次を実行します。

```bash
./claude-login.sh login
docker compose --env-file .env --profile agent up -d --no-build --wait
```

OAuthログインにはインターネット接続が必要です。認証情報はセキュリティ上、
オフラインバンドルへ同梱しません。

認証期限切れや失効時は`./scripts/claude-login.sh login`で再認証してください。

```bash
docker compose --profile agent up -d --no-build --force-recreate worker
```

## 6. APIキーを使う場合（任意）

Claude Pro/MaxではなくAnthropic Consoleの従量課金を使う場合だけ、導入先の`.env`
へAPIキーを設定します。APIキーを設定した場合はOAuthログインは不要です。

```dotenv
ANTHROPIC_API_KEY=設定したAPIキー
```

実値を含む`.env`やログをGitへコミットしないでください。

## 7. 利用枠

2026年6月15日以降、Claude Pro/Max契約での`claude --print`やAgent SDKの自動実行は、
通常の対話利用枠とは別の月間Agent SDKクレジットを消費します。大量のWebhookを
投入する前に、Claudeの利用状況画面で残量を確認してください。
