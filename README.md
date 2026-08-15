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
cp .env.example .env
./scripts/jenkins-image.sh build
docker compose up -d
docker compose ps
```

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

Registryへログインした状態で、ビルド元からpushします。

```bash
./scripts/jenkins-image.sh push
```

導入先には `compose.yaml`、`.env`、空の `jenkins/certs/` だけを配置すれば、
ビルドせずに取得して起動できます。

```bash
docker compose pull
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
docker compose down

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
