# MVP Release Checklist

## 完成済み

- 東北公式ソースから候補収集
- 宮城県公式HTML照合
- 候補調査・属性記録
- 営業優先順位 S/A/B/C + 100点スコア
- 初回営業文生成
- 営業活動ログ
- 営業分析
- フォローアップキュー
- 追客文生成
- 「今日の営業」統合ダッシュボード
- 候補＋営業活動バックアップCSV
- ログイン保護
- 認証後POSTのCSRF保護
- セキュリティヘッダー
- GitHub Actionsテスト

## 実運用前に外部サービス側で必要な作業

コードだけでは完了できないため、実データ投入前に以下を確認します。

1. GitHubリポジトリをPrivateへ変更する。
2. RenderでAPP_USERNAME / APP_PASSWORD / SECRET_KEYを設定する。
3. SESSION_COOKIE_SECURE=trueを確認する。
4. 無料Renderの一時SQLiteから永続ストレージへ移行する、またはバックアップ運用を決める。
5. `/ops/export.csv` からバックアップを保存できることを確認する。

このチェックが完了すれば、単一営業担当者向けMVPとして実運用開始できる状態です。
