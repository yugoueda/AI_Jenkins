# Jenkinsを別PCへ導入する手順

## 1. 対象

本手順は、このリポジトリで作成したJenkins環境を別のWindows PCへ導入するための
ものです。導入先はWSL 2上のUbuntuとし、Docker Engine + Docker Compose v2、
またはDocker DesktopのWSL連携が利用できることを前提とします。

オフラインバンドルは作成元と導入先でCPUアーキテクチャを合わせてください。通常の
Intel/AMD版Windows PC同士は `amd64` です。ARM版Windowsへ移す場合は、ARM環境で
イメージをビルドするかmulti-architectureイメージをRegistryへ公開してください。

Jenkinsコンテナを単純に `docker export` すると、named volume内のジョブ、認証情報、
プラグイン設定が含まれません。本構成では次を個別に移送します。

- Jenkinsカスタムイメージ
- Docker-in-Dockerイメージ
- Compose定義と環境設定
- 必要な場合のみ、Jenkins homeデータ

## 2. 推奨: Container Registry経由

GitLab Container Registry、GHCR、Docker Hubなどを利用できる場合の推奨手順です。

### 配布元PC

`.env` の `JENKINS_IMAGE` を実際のRegistry名へ設定します。

```dotenv
JENKINS_IMAGE=registry.example.com/your-team/ai-jenkins:2.568.1-1
```

Registryへログインしてpushします。

```bash
docker login registry.example.com
./scripts/jenkins-image.sh push
```

導入先PCへ次のファイルをコピーします。

- `compose.yaml`
- `.env`
- 空の `jenkins/certs/` ディレクトリ

### 導入先PC

```bash
docker login registry.example.com
docker compose pull
docker compose up -d --no-build --wait
docker compose ps
```

新規環境の初回解除パスワードは次で確認します。

```bash
docker compose exec jenkins \
  cat /var/jenkins_home/secrets/initialAdminPassword
```

## 3. Registryを使わないオフライン移送

### 配布元PC

イメージと導入ファイルを1つのtarへまとめます。

```bash
./scripts/export-jenkins-bundle.sh
```

次の2ファイルをUSBメモリや安全なファイル転送で導入先へコピーします。

```text
dist/ai-jenkins-bundle-2.568.1-1.tar
dist/ai-jenkins-bundle-2.568.1-1.tar.sha256
```

### 導入先PC

まず外側のtarが破損していないことを確認します。

```bash
sha256sum -c ai-jenkins-bundle-2.568.1-1.tar.sha256
tar -xf ai-jenkins-bundle-2.568.1-1.tar
cd ai-jenkins-bundle-2.568.1-1
./install.sh
```

`install.sh` は内包ファイルのSHA-256検証、`docker load`、Compose起動、
ヘルスチェックを順番に実行します。Registryへの接続やイメージのビルドは不要です。

## 4. ジョブ・ユーザー・認証情報も移行する場合

Jenkins homeを含むバンドルを作成します。

```bash
./scripts/export-jenkins-bundle.sh --include-data
```

一貫したバックアップを取得するため、処理中はJenkinsだけが一時停止され、完了後に
自動再開します。出力名には `-with-data` が付き、通常版と区別されます。

このバンドルには以下の機密情報が含まれます。

- Jenkinsユーザーとパスワードハッシュ
- GitLabなどのCredentials
- ジョブ設定とビルド履歴
- Jenkins内部の暗号鍵

暗号化された媒体で運び、導入完了後は配布元・USBメモリ・導入先の不要なコピーを
削除してください。`install.sh` は既存の `ai-jenkins_jenkins-home` volumeを検出
した場合、データ上書きを防ぐため停止します。

## 5. 導入後の確認

```bash
docker compose ps
docker compose exec jenkins docker version
curl -I http://localhost:8080/login
```

期待する状態は次のとおりです。

- `jenkins` と `docker` が `healthy`
- JenkinsからDocker client/server両方のバージョンを取得可能
- `http://localhost:8080/login` が応答

## 6. LAN公開

初期設定では安全のため `127.0.0.1:8080` のみで待ち受けます。別PCからブラウザで
アクセスさせる場合は、導入先の `.env` を次のように変更します。

```dotenv
JENKINS_HTTP_HOST=0.0.0.0
```

変更後に再作成します。

```bash
docker compose up -d --no-build --force-recreate jenkins
```

本番ではnginxなどのリバースプロキシでTLSを有効にし、Windows Firewallの接続元を
社内ネットワークへ制限してください。WSLのネットワーク方式によってはWindows側の
`netsh interface portproxy` 設定も必要です。

## 7. 社内CA

社内GitLabなどが独自CAを利用する場合、CA証明書を導入先の
`jenkins/certs/` へ配置します。

```bash
docker compose up -d --no-build --force-recreate cert-init jenkins
```

証明書そのものは通常の配布バンドルへ自動同梱されません。組織の証明書配布ルールに
従って別途、安全に配布してください。
