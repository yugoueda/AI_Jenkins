# AI Review Jenkins

Jenkins LTS を Docker Compose で起動する構成です。Jenkins本体、プラグイン、
Python 3、Git、Docker CLIを配布用イメージに含めています。CIジョブ用のDocker
daemonはTLS付きの専用コンテナとして分離し、JenkinsのデータはDocker named
volumeへ永続化します。

## 前提

- WSL 2 上の Ubuntu（Ubuntuの細かなバージョンには非依存）
- Docker Engine + Docker Compose v2、または Docker Desktop のWSL連携
- 推奨: メモリ4 GB以上、空き容量50 GB以上

PowerShellでWSL 2か確認できます。

```powershell
wsl -l -v
```

`VERSION` が `1` の場合は、ディストリビューション名を指定して変換します。

```powershell
wsl --set-version Ubuntu 2
```

UbuntuのバージョンはWSL内で次のコマンドから確認できます。この構成はDocker内に
JavaやPythonを含めるため、特定のUbuntuリリースには依存しません。

```bash
cat /etc/os-release
./scripts/check-jenkins-host.sh
```

## WSLでの初回起動

リポジトリは `/mnt/c/...` ではなく、WSL側のファイルシステム
（例: `/opt/ai-review` または `~/ai-review`）へ置くことを推奨します。

```bash
./scripts/check-jenkins-host.sh
./scripts/setup-docker.sh
```

`setup-docker.sh` は初回のみ `.env.example` から `.env` を作成し、Compose定義の検証、
イメージのビルド、ヘルスチェック付き起動まで行います。WebhookとCLIエージェントも
同時に構築する場合は `./scripts/setup-docker.sh --with-agent` を使います。

起動完了後、WindowsまたはWSLのブラウザから
<http://localhost:8080> を開きます。初回解除パスワードは次で確認できます。

```bash
docker compose exec jenkins \
  cat /var/jenkins_home/secrets/initialAdminPassword
```

画面の案内に従い、管理者ユーザーを作成してください。必要なプラグインはイメージへ
導入済みなので、初回画面では追加インストールをスキップできます。

## Claude Code CLIエージェント

Claude Pro/Maxアカウントを利用する場合はAPIキー不要です。初回だけworkerコンテナの
Claude Codeからアカウント認証し、ログイン情報を専用Docker volumeへ保存します。

```bash
./scripts/agent-image.sh build
docker compose --profile agent up -d --no-build --wait
./scripts/claude-login.sh login
./scripts/claude-login.sh status
```

対話ログインの認証情報は専用Docker volumeへ保存されます。詳しいコンテナ内での
認証手順、疎通確認、別PCへの導入方法は
[Claude Code CLIエージェント導入手順](Doc/CLIエージェント導入手順.md)を参照して
ください。

個人GitLab.comを使うデモでは、Webhookポートを直接インターネットへ公開せず、
ngrokのHTTPSトンネルを使用します。認証要件と、将来社内GitLabへ移行する際の
ネットワーク・TLS・運用上の課題は
[デモ版 Webhook外部公開方針](Doc/デモ版_Webhook外部公開方針.md)を参照してください。
日常的な起動、Flutterイメージの準備、ngrok接続、疎通確認、停止については
[デモ環境の再開・停止手順](Doc/デモ環境_再開・停止手順.md)にまとめています。

### Webhook以降の連携設定

MR作成後の処理は `GitLab → webhook → Jenkins build → webhook callback →
job_queue → worker → GitLab` の順で動作します。`.env`には少なくとも次を設定します。

```dotenv
GITLAB_URL=https://gitlab.example.com
GITLAB_TOKEN=<API token>
JENKINS_USER=<Jenkins user>
JENKINS_TOKEN=<Jenkins API token>
JENKINS_BUILD_JOB=ai-review-build
JENKINS_TEST_JOB=ai-review-test
JENKINS_CALLBACK_TOKEN=<random internal token>
```

Flutter参照プロジェクトのBuild/Lint/Testは、標準Flutterイメージで実行します。
ビルド対象はWebのみで、`flutter build web`を使用します。
静的解析では`--no-fatal-infos`を使用し、infoレベルの指摘だけではAIレビューを
停止しません。warningまたはerrorで失敗した場合は、従来どおり失敗を通知します。
MR作成時には利用可能な`/ai`コマンドをMRコメントで案内します。ビルドに失敗した場合は
即時に失敗を通知し、workerによる解析完了後に原因と修正案を追加コメントします。
AIレビューの指摘は対象ファイルの対象行へ解決可能なDiscussionとして投稿します。
対象行が現在の差分に含まれない場合だけ、ファイル名と行番号を含む通常コメントへ
フォールバックします。
GitLab WebhookではMerge request eventsとNote eventsの両方を有効にしてください。

CLIエージェントの実行状況はworkerのログで確認できます。プロンプト本文やレビュー結果の
本文は出力せず、ジョブID、イベント種別、試行回数、経過時間、終了コードを表示します。

```bash
docker compose logs -f worker
```

既定の最大ターン数は`CLAUDE_MAX_TURNS=30`、進行ログの間隔は
`AGENT_PROGRESS_INTERVAL_SECONDS=15`秒です。必要に応じて`.env`で変更できます。

Open状態かつDB上の指摘が0件のMRへコミットが追加されると、Webビルドを自動で
再実行します。ビルド・静的解析が成功するとAIレビューへ進みます。同じコミットSHAの
Webhook再送は重複実行せず、同一MRのビルド中に追加されたコミットはDBへ保留して、
現行ビルド完了後に順次実行します。

最後の指摘を`/ai approve Rn`で適用した場合、または最後のDiscussionをResolveした
場合も、対象コミットをWebビルドしてから再レビューします。再レビューの指摘が0件なら
テスト生成を自動実行し、生成テストをMRのsource branchへコミットして
`ai-review-test`を起動します。テスト結果とC0/C1カバレッジはMRコメントへ通知され、
コンパイルエラーやテスト失敗時も失敗結果とログの要約が投稿されます。

`/ai test`をコメントするとテスト生成だけを手動実行できます。未解決の指摘が残る状態で
実行すると、修正前コードで失敗するバグ再現テストが生成される可能性があるため、通常は
自動フロー（指摘0件 → 再レビュー成功）の利用を推奨します。

新規Jenkins環境では次のPipelineジョブがイメージ初期化時に自動作成されます。

- `ai-review-build`: `jenkins/Jenkinsfile.build`
- `ai-review-test`: `jenkins/Jenkinsfile.test`

GitLab用Credential IDは既定で`gitlab-token`です。別名を使う場合は
`GITLAB_CREDENTIALS_ID`を変更してください。Jenkinsコールバック先はCompose内部の
`http://webhook:8000`で、外部公開しません。

## 他環境へ配布

詳細は [Jenkinsを別PCへ導入する手順](Doc/Jenkins_別PC導入手順.md) を参照して
ください。Container Registry経由と、Registryを使わないオフライン移送の両方に
対応しています。

配布先のDocker Registry（GitLab Container Registry、GHCR、Docker Hubなど）を
決め、`.env` の `JENKINS_IMAGE` を実際の名前へ変更します。

```dotenv
JENKINS_IMAGE=registry.example.com/your-team/ai-jenkins:2.568.1-1
```

`.env` の `AGENT_IMAGE` も同じRegistry配下の名前に変更します。Registryへログインした
状態で、ビルド元から両方のイメージをまとめてpushします。

```bash
./scripts/publish-images.sh
```

導入先には `compose.yaml`、`.env`、空の `jenkins/certs/` を配置すれば、ビルドせずに
取得して起動できます。CLIエージェントも使う場合は `scripts/claude-login.sh` もコピー
してください。

```bash
docker compose --profile agent pull
docker compose up -d --no-build
```

Registryを利用できない場合は、Jenkins、DinD、Claude Codeエージェントの各イメージを
オフラインバンドルにできます。

```bash
./scripts/export-jenkins-bundle.sh
```

Jenkinsの設定・ジョブ・認証情報は `ai-jenkins_jenkins-home` volumeに保存されます。
コンテナやイメージを更新しても保持されます。

## 運用コマンド

```bash
# 状態
docker compose ps

# Jenkinsログ
docker compose logs -f jenkins

# 停止（データは保持）
docker compose --profile agent down

# 配布済みイメージへ更新
docker compose pull
docker compose up -d --no-build

# バックアップ
docker run --rm \
  -v ai-jenkins_jenkins-home:/source:ro \
  -v "$PWD/backups:/backup" \
  alpine tar czf /backup/jenkins-home.tgz -C /source .
```

`docker compose down -v` はJenkinsの全データを削除するため、通常運用では実行
しないでください。

## LAN公開と社内CA

初期値では `127.0.0.1:8080` のみに公開します。社内LANからアクセスさせる場合は、
`.env` の `JENKINS_HTTP_HOST=0.0.0.0` に変更し、nginx等でTLS・アクセス制限を
設定してください。WSLのネットワーク方式によっては、Windows側のファイアウォール
設定や `netsh interface portproxy` も必要です。

社内GitLabなどが独自CAを使う場合は、CA証明書（`.crt` または `.pem`）を
`jenkins/certs/` に置いてから再起動します。

```bash
docker compose up -d --force-recreate cert-init jenkins
```

## 設計上の注意

- Jenkins controllerは非rootユーザーで動作します。
- Docker操作は特権のDinDサービスへTLS接続します。DinDはホストへポート公開しません。
- inbound agent用の50000番ポートは未公開です。現在の単一ノード構成では不要です。
- `jenkins/jenkins:2.568.1-jdk21` を基底に固定しています。更新時はバックアップ後に
  `JENKINS_BASE_IMAGE` と配布イメージのタグを更新し、検証してからpushしてください。
