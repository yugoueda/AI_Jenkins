---
name: flutter-unit-test
description: >
  Flutter/Dartのユニットテスト・ウィジェットテスト生成手順と規約。flutter_testを使用した
  テストコード生成・カバレッジ向上・テストテンプレート参照が必要な場合に自動ロード。
user-invocable: false
---

# Flutter/Dart ユニットテスト生成スキル

## 使用タイミング

- `unit-test-generator` エージェントがテストコードを生成する場合
- カバレッジ未達箇所に対してテストを追加する場合

## 手順

1. 差分とカバレッジ未達情報を確認する
2. Widgetクラスへの変更は [Widget Testテンプレート](./templates/widget_test.dart.tmpl) を使用する
3. それ以外は [Unit Testテンプレート](./templates/unit_test.dart.tmpl) を使用する
4. [flutter_test 規約まとめ](./references/flutter-test-guide.md) に従ってテストを実装する
5. テストファイルは `test/` 配下に配置し、`lib/` の構造を反映する

## 命名規則

| 対象 | 規則 | 例 |
|---|---|---|
| テストファイル名 | `{ソースファイル名}_test.dart` | `order_service_test.dart` |
| `group` 名 | テスト対象クラス名または関数名 | `OrderService` |
| `test` 名 | 条件と期待結果を動詞句で記述 | `returns null when input is empty` |

## モック方針

- HTTP通信は `http.Client` をモック化する
- `SharedPreferences` は `SharedPreferences.setMockInitialValues()` を使用する
- ファイルI/Oは抽象インタフェース経由でモック化する
- モックが不要な純粋関数にはモックを導入しない
