# 東北リペア営業ノート

東北6県の民泊・宿泊施設へ、床・建具・家具・水回りのキズ補修／コーティングを提案するための営業支援Webアプリです。

> **交換・リフォームする前に、補修という選択肢を。**

## MVP完成版でできること

1. 宮城県・仙台市・青森県・秋田県・山形県・福島県の公式公開資料から候補を収集。岩手県は公式の市町村別件数を調査優先順位に利用。
2. 施設名、運営会社、住所、電話、メール、問い合わせURL、根拠URLを候補DBへ保存。
3. ペット可、一棟貸し、木質床、複数施設運営などの営業属性を調査・記録。
4. S/A/B/Cと100点満点の営業優先スコアを自動計算し、理由と不足情報を表示。
5. 候補ごとの提案テーマと初回営業文を生成。自動送信はせず、人間確認を必須化。
6. 送信済み、返信あり、見積、成約、見送りを営業活動ログへ記録。
7. 未返信、返信あり、見積提出後を自動判定し、追客対象をフォローアップキューに表示。
8. 未返信・返信後・見積後に合わせた追客文を、標準／短め／やわらかめで生成。
9. 提案テーマ別・県別の返信率、見積化率、成約率を営業分析画面で確認。
10. 「今日の営業」画面で、要フォロー、新規営業、候補調査、分析を1画面から進行。
11. 候補と営業活動をまとめたUTF-8 BOM付きバックアップCSVを出力。

## 主要画面

- `/ops` 今日の営業（運用の起点）
- `/sales-priority` 営業優先順位
- `/follow-up` フォローアップ管理
- `/sales-activities` 営業活動履歴
- `/sales-analytics` 営業分析
- `/candidates` 収集候補
- `/collection-dashboard` 収集状況
- `/regional-sources` 東北各県の公式ソース
- `/enrichment` 宮城県公式HTML照合
- `/ops/export.csv` 候補＋営業活動のバックアップCSV

## 安全設計

- 営業メールや問い合わせフォームへの**自動送信はしません**。
- 未確認の傷・劣化を事実として営業文に断定しません。
- 公開情報の取得は公式資料中心で、CAPTCHA回避・ログイン突破・規約回避は行いません。
- 本番では `APP_USERNAME` / `APP_PASSWORD` を設定し、ログイン後のPOST操作にはCSRF保護を適用します。
- Cookieは HttpOnly / SameSite=Lax、RenderではSecureを使用し、HTTPSではHSTSとPermissions-Policyを付与します。
- 秘密情報は環境変数のみで扱い、GitHubへ保存しません。

## 技術構成

| 項目 | 技術 |
|---|---|
| Web | Python / Flask |
| DB | SQLite |
| HTML解析 | BeautifulSoup |
| PDF解析 | pypdf |
| XLSX解析 | openpyxl |
| 本番起動 | Gunicorn / Docker |
| 配置 | Render |
| CI | GitHub Actions / pytest |

外部AI APIは現時点で使っていないため、APIキーや従量課金なしで動作します。営業文生成は確認済み属性とルールベースのテンプレートで行います。

## Render運用

本番エントリポイントは `server:app` です。`server.py` が収集、公式照合、営業優先順位、営業アクション、活動ログ、分析、フォローアップ、追客文、統合トップ、CSRF保護を登録します。

Renderでは次の環境変数を設定してください。

- `APP_USERNAME`: 管理ユーザー名
- `APP_PASSWORD`: 他サービスで使っていない長いパスワード
- `SECRET_KEY`: 長いランダム値（Blueprint側で自動生成可能）
- `SESSION_COOKIE_SECURE=true`
- `DATABASE_PATH`: SQLite保存先

### 重要: 無料Render + SQLite

無料Web Serviceの一時ファイル領域では、再起動・再デプロイ等でSQLiteデータが消える可能性があります。検証中は `/ops/export.csv` を定期的に保存してください。

**実顧客データを継続運用する段階では、永続ディスクまたは永続DBへ移行してください。** これはコードではなくRender側の契約・構成変更が必要です。

## 実運用前チェック

- GitHubリポジトリをPrivateにする。
- Renderで `APP_USERNAME` / `APP_PASSWORD` / `SECRET_KEY` を設定する。
- `SESSION_COOKIE_SECURE=true` を確認する。
- SQLiteを永続ストレージへ移す、または定期バックアップ運用を決める。
- 実データを入れる前に `/ops/export.csv` の保存手順を確認する。
- 営業先の公開情報・連絡先の利用目的、サイト規約、関連法令を確認する。
- 営業文・追客文は必ず送信前に人が確認する。

## 開発・テスト

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

ローカルで拡張ルートを含む完成版を起動する場合は次を使います。

```bash
gunicorn server:app
```

## 完成範囲

このリポジトリのMVPは、**候補収集 → 調査 → 優先順位 → 営業文 → 人間確認 → 活動記録 → 追客 → 分析 → バックアップ**までを一連で実行できる状態を完成形としています。

今後追加するとすれば、複数ユーザー権限、外部CRM連携、永続PostgreSQL、メール送信サービス連携などの「事業規模拡大向け機能」です。単一担当者が東北の宿泊施設へ営業するMVPとしては、現行機能で一通り運用できます。
