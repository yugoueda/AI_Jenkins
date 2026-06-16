# flutter_test 規約まとめ

- Unit Testは `test()`、Widget Testは `testWidgets()` を使用する
- テストは Arrange / Act / Assert の順に構成する
- 非同期処理は `await` し、Widget Testでは必要に応じて `pump()` / `pumpAndSettle()` を使う
- UI変更を伴う場合は主要Widgetの表示、入力、状態変化を確認する
- `SharedPreferences` は `SharedPreferences.setMockInitialValues({})` で初期化する
- 外部通信、DB、ファイルI/Oは直接呼ばずモックまたはFakeを使う
- 生成するテストは差分とカバレッジ未達行に関連する範囲へ限定する
