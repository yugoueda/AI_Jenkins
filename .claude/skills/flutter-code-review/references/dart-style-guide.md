# Dartスタイルガイド要約

- ファイル名は `lower_snake_case.dart`
- クラス、enum、typedef、extension は `UpperCamelCase`
- 変数、関数、メソッド、引数は `lowerCamelCase`
- 定数は `lowerCamelCase` を基本とし、既存規約があれば従う
- privateメンバーは `_` で始める
- 1ファイルに複数責務を詰め込まない
- `var` と明示型は可読性を基準に使い分ける
- 不要な `this.`、不要な型注釈、到達不能コードを避ける
- `dart format` 前提の整形に従う
