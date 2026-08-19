# デモ版 Webhook外部公開方針

**決定日：** 2026年8月10日
**対象：** 個人GitLab.comリポジトリを利用するデモ環境

## 1. 決定事項

デモ版では、Webhook受信サーバをGitLab.comから呼び出せるように外部公開する。
公開には **ngrok FreeのHTTPSトンネル**を使用し、ルーターのポート開放やWebhook
受信ポートのインターネットへの直接公開は行わない。

```text
GitLab.com
  │ HTTPS
  │ ngrok用認証 + GitLab Webhook Secret Token
  ▼
ngrok Edge
  │ パス・メソッド制限 + GitLab Webhook検証
  ▼
webhook:8000/webhook（Docker内部ネットワーク）
  │ アプリケーションでSecret Tokenを再検証
  ▼
Webhook受信サーバ
```

GitLabに登録するWebhook URLは次の形式とする。

```text
https://<ngrokから割り当てられたドメイン>.ngrok.app/webhook
```

ngrokの無料枠や提供条件は変更される可能性があるため、導入時に公式情報を再確認する。
無料枠を超える、固定URLを維持できない、またはデモ期間を超えて継続運用する場合は、
有料プランへ自動移行せず、公開方式を改めて判断する。

## 2. 採用理由

- 独自ドメインを用意せず、デモ用のHTTPS URLを取得できる
- ngrokエージェントからの外向き接続でトンネルを確立するため、受信ポートの開放が不要
- TLS証明書の取得・更新をデモ実施者が管理しなくてよい
- GitLab WebhookのSecret Tokenをngrok Edgeで検証し、不正な要求をローカル環境へ
  到達させない構成にできる
- デモ終了時はトンネルを停止するだけで外部から到達不能にできる

Cloudflare Quick TunnelはURLが起動ごとに変わり、可用性保証がないため採用しない。
独自ドメインをすでに保有し、デモ後も継続運用する場合は、Cloudflare Named Tunnelと
Access Service Tokenの組み合わせを代替候補とする。

## 3. セキュリティ要件

### 3.1 ネットワーク

- `.env`の`WEBHOOK_HTTP_HOST`は`127.0.0.1`を維持する
- `8000/tcp`をルーター、Windows Firewall、クラウドFWなどで外部へ直接開放しない
- ngrokはComposeサービスとしてWebhookと同じDockerネットワークへ参加させ、転送先を
  `http://webhook:8000`とする。ホストで一時実行する場合だけ
  `http://127.0.0.1:8000`を使用する
- 外部公開する経路は`POST /webhook`だけとし、`/healthz`、Jenkins、DB、workerを
  公開しない
- GitLab側のSSL verificationを有効にする

### 3.2 認証・署名

- `GITLAB_WEBHOOK_SECRET`には32バイト以上の暗号学的乱数を設定する
- GitLabのSecret Token、ngrok Edge、Webhook受信サーバで同じWebhook要求を検証する
- ngrok用の認証情報はGitLabのカスタムヘッダーで送信し、GitLab Secret Tokenとは
  別の値を使用する
- 認証情報をリポジトリ、コマンド履歴、ngrok設定ファイル、スクリーンショットへ
  平文で残さない。ngrokのSecret/Vault機能またはOSのシークレット管理機能を使用する
- デモ終了後、GitLabのWebhookを削除し、Secret Tokenとngrok用認証情報を失効させる

現行実装は`X-Gitlab-Token`の固定値比較のみであり、リプレイ攻撃を検知できない。
GitLabでSigning tokenを利用できる場合は、本文のHMAC署名とWebhook timestampを検証し、
許容時間を過ぎた要求を拒否する機能を追加する。Signing token対応が完了するまでは、
トンネルの稼働時間をデモ準備・実施中だけに限定する。

### 3.3 リクエスト制御

- ngrok Edgeで`POST /webhook`以外を拒否する
- リクエストボディの最大サイズと単位時間当たりの要求数に上限を設ける
- 対象のGitLab project IDを許可リスト化し、別プロジェクトのペイロードを拒否する
- 対応対象をMerge Request eventsとCommentsに限定する
- Webhook IDを一定期間記録して重複配信を冪等に処理する

### 3.4 ログ・データ

- ngrokのリクエスト／レスポンス本文キャプチャを有効にしない
- アプリケーションログに認証ヘッダー、アクセストークン、ソースコード全文を出力しない
- デバッグのため一時的に本文を記録した場合は、デモ終了直後に安全に削除する

## 4. 開発項目と完了条件

| 項目                         | 現在の状態 | デモ公開前の完了条件                                     |
| ---------------------------- | ---------- | -------------------------------------------------------- |
| localhost限定公開            | 実装済み   | `WEBHOOK_HTTP_HOST=127.0.0.1`を維持                    |
| Secret Token検証             | 実装済み   | `change-me`を廃止し、十分に長い乱数へ変更              |
| ngrokサービス                | 未実装     | Webhookと同じ内部ネットワークへComposeサービスとして追加 |
| ngrok Edge検証               | 未実装     | パス・メソッド・GitLab Secret Token・追加認証を検証      |
| リクエストサイズ／レート制限 | 未実装     | 上限超過時に処理せず、適切なHTTPエラーを返す             |
| project ID許可リスト         | 未実装     | デモ対象以外のproject IDを拒否                           |
| 冪等性／リプレイ対策         | 未実装     | Webhook ID重複排除。可能ならHMACとtimestampも検証        |
| 運用手順                     | 未実装     | 起動、疎通確認、停止、失効、ログ確認手順を文書化         |

公開前に、認証情報なし・不正な認証情報・許可外project ID・過大な本文・重複した
Webhookが拒否または安全に無視されることを自動テストする。

## 5. 社内公開へ移行する場合の課題

本来の構成は、社内セルフホストGitLabから社内ネットワーク上のWebhook受信サーバへ
到達させる想定である。デモ版のngrok構成をそのまま社内運用へ持ち込まず、次の課題を
解決したうえで公開方式を決定する。

### 5.1 公開経路の設計不整合

技術設計書にはWebhook受信サーバを`0.0.0.0:8000`で社内NICへ直接公開する記述がある。
一方、フェーズ5計画にはWebhookコンテナの外向きポートを持たせず、nginx経由にする
記述があるが、現状のnginx案はJenkinsへの転送しか定義していない。

社内導入前に、次のどちらかへ統一する。

1. 推奨：社内リバースプロキシだけを社内NICへ公開し、`/webhook`をDocker内部の
   Webhookサービスへ転送する
2. 暫定：`8000/tcp`を社内NICへ直接公開し、ホストFWでGitLabサーバの送信元IPだけを
   許可する

推奨構成ではJenkins UIとWebhook APIのホスト名またはパスを分離し、Webhook経由で
Jenkinsや管理画面へ到達できないルーティングにする。

### 5.2 社内ネットワーク・WSL2

- GitLabサーバから導入先PCへの経路、VLAN、プロキシ、FWルールを確認する
- WSL2のNAT／ミラーモードとDocker Desktopのポート公開動作を導入先ごとに確認する
- 必要な場合だけWindowsの`netsh interface portproxy`を設定し、設定内容を台帳化する
- DHCPアドレスを直接URLに使わず、固定IPまたは社内DNS名を割り当てる
- GitLabサーバ以外の端末からWebhookポートへ接続できないことをテストする

### 5.3 TLS・証明書

- 社内CAでWebhook用サーバー証明書を発行し、リバースプロキシでTLS終端する
- 証明書のSAN、期限、更新責任者、自動更新または更新手順を決める
- GitLab側へ社内CAを信頼させ、SSL verificationを無効化しない
- リバースプロキシからWebhookコンテナまで暗号化が必要か、脅威モデルに基づいて決める

### 5.4 認証・アクセス制御

- GitLab Secret Tokenに加えて、送信元IP制限またはmTLSを採用するか決める
- 複数GitLab／複数プロジェクトを扱う場合、プロジェクトごとのSecret Tokenと
  project ID許可リストを管理する
- Secret Tokenの保管、配布、ローテーション、退職・異動時の失効手順を決める
- リバースプロキシ経由でも実送信元IPを監査できるよう、信頼するプロキシと
  `X-Forwarded-For`の扱いを固定する

### 5.5 運用・可用性・監査

- Webhook、リバースプロキシ、workerをOS／Compose起動時に自動復旧させる
- GitLabの再送仕様を前提に、重複排除、キュー永続化、障害復旧を検証する
- ヘルスチェック、ディスク使用量、キュー滞留、認証失敗を監視する
- ログの保存期間、閲覧権限、ソースコードや個人情報のマスキング方針を決める
- nginx、FastAPI、コンテナイメージ、CA証明書の更新手順と担当者を決める
- 外部SaaSトンネルが社内規程上許可されない場合、ngrok関連設定を社内環境へ
  配布・起動しない構成に分離する

## 6. 環境別の最終形

| 項目               | デモ版                                 | 社内運用版                                   |
| ------------------ | -------------------------------------- | -------------------------------------------- |
| GitLab             | GitLab.com個人リポジトリ               | 社内セルフホストGitLab                       |
| 公開経路           | ngrok HTTPS Tunnel                     | 社内リバースプロキシを推奨                   |
| ホストの受信ポート | localhostのみ                          | 社内NICのTLSポートのみ                       |
| インターネット公開 | デモ実施中だけ有効                     | 原則なし                                     |
| 主な接続制限       | ngrok認証 + Secret Token + project ID  | 送信元制限／mTLS + Secret Token + project ID |
| TLS                | ngrokで終端                            | 社内CA証明書で終端                           |
| URL                | `https://<domain>.ngrok.app/webhook` | `https://<internal-fqdn>/webhook`          |

## 7. 参考資料

- [ngrok GitLab Repository Webhooks](https://ngrok.com/docs/integrations/webhooks/gitlab-webhooks)
- [ngrok Pricing and Limits](https://ngrok.com/docs/pricing-limits)
- [GitLab Webhooks](https://docs.gitlab.com/user/project/integrations/webhooks/)
- [Cloudflare Tunnel](https://developers.cloudflare.com/tunnel/)
- [Cloudflare Quick Tunnels](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/)
