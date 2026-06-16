---
name: flutter-code-review
description: >
  Flutter/Dartコードのレビュー手順とチェックリスト。コード品質・バグ検出・セキュリティ確認・
  Dartスタイルガイド準拠チェックが必要な場合に自動ロード。
user-invocable: false
---

# Flutter/Dart コードレビュースキル

## 使用タイミング

- MRのdiff+周辺実装をレビューする場合
- Flutter/Dartコードの品質・バグ・セキュリティを確認する場合

## 手順

1. [コード品質チェックリスト](./checklists/quality.md) を参照し、観点ごとに差分を確認する
2. [セキュリティチェックリスト](./checklists/security.md) でOWASP Top 10相当の問題を確認する
3. [Dartスタイルガイド要約](./references/dart-style-guide.md) に照らして命名・フォーマットを確認する
4. 問題を検出したら `ai-reviewer` エージェントの出力形式に従ってJSONを構築する

## 出力方針

- JSONのみを返す
- 指摘なしの場合は `{"findings":[]}` のみ返す
- `file`、`line_start`、`line_end`、`description` は必ず埋める
