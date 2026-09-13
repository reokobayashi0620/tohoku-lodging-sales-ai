# 東北リペア営業ノート — MVP 1.0

東北6県の民泊・宿泊施設へ、床・建具・家具・水回りのキズ補修／コーティングを提案するための営業支援Webアプリです。

> **交換・リフォームする前に、補修という選択肢を。**

このMVPは「候補を見つける → 調べる → 優先順位を付ける → 営業文を作る → 人が送る → 返信・見積・成約を記録する → 追客する → 成果を分析する」までを1つのブラウザ画面で回せる状態です。

## 完成済みの機能

- 宮城県・仙台市・青森県・秋田県・山形県・福島県の公式公開資料から候補収集
- 岩手県は公式の市町村別件数を使った安全な調査優先順位付け
- 宮城県公式HTMLとの住所照合と公開連絡先の補完
- 候補調査、重複抑制、調査進捗、公開ページからの半自動情報抽出
- ペット可・一棟貸し・木質床・複数施設運営などを使ったS/A/B/C営業優先順位
- S/A候補向けの提案テーマ推奨と営業文たたき台生成
- 営業活動ログ（送信・返信・見積・成約・見送り）
- 提案テーマ別・県別の返信率／見積化率／成約率分析
- 最新活動からのフォローアップ自動抽出
- 未返信・返信あり・見積後の追客文自動生成
- 「今日やること」統合ダッシュボード
- SQLite完全バックアップのダウンロード
- ログイン、セキュリティヘッダー、CSRF対策
- GitHub Actionsによるpytest自動テスト

営業文・追客文は**下書きだけ**を生成します。自動送信や大量送信は行いません。宛先、公開情報、相手の返信内容を人が確認してから送信する設計です。

## 日常の使い方

1. `/today` の「今日やること」を開く
2. 返信あり・見積後・未返信の要フォローを先に処理
3. S/A候補へ新規営業文を作成して、人が確認して送信
4. 送信・返信・見積・成約・見送りを営業活動ログへ記録
5. 候補が減ったら公式資料から追加収集し、候補調査と公式照合を行う
6. `/sales-analytics` で成果の出ているテーマ・県を確認する
7. 定期的に `/system` からSQLiteバックアップを保存する

## 技術構成

- Python / Flask
- SQLite
- HTML / CSS / JavaScript（ビルド不要）
- Gunicorn / Docker
- Render
- pytest / GitHub Actions

外部AI APIは使用していないため、APIキーや従量課金は不要です。

## Render運用

`render.yaml` は無料Web Service向けの検証構成です。`main` 更新時に自動デプロイされ、`/healthz` を死活監視に使用します。

必須の秘密情報はRenderのEnvironmentにのみ設定します。

- `APP_USERNAME`
- `APP_PASSWORD`
- `SECRET_KEY`（Blueprintでは自動生成）
- `SESSION_COOKIE_SECURE=true`

### 重要: データ永続化

無料構成では `DATABASE_PATH=/tmp/sales.db` のため、再起動・再デプロイ・休止復帰でデータが消える可能性があります。**実データを継続運用する前に、Renderの永続ディスク等へDB保存先を移してください。**

永続ディスクを `/var/data` にマウントする場合は、Render側で次のように変更します。

```text
DATABASE_PATH=/var/data/sales.db
```

アプリ内 `/system` でも、ログイン・SECRET_KEY・HTTPS Cookie・CSRF・DB永続化の準備状況を確認できます。

## セキュリティ

- 営業画面はフォームログインで保護
- セッションCookieはHttpOnly / SameSite=Lax、RenderではSecure
- 全POST/PUT/PATCH/DELETEにCSRFトークン検証
- `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` を付与
- APIキー・パスワード・実顧客DBはGitへ保存しない
- `/healthz` は認証不要だが営業情報を返さない

現在のリポジトリがPublicの間は、**実顧客の個人情報・秘密情報・DBファイルをコミットしないでください。**

## バックアップ

`/system` → 「SQLiteバックアップを保存」で、候補・施設・営業活動・分析元データを含むDB全体を保存できます。CSV出力より完全な復旧用バックアップです。

## ローカル実行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app server run
```

テスト:

```bash
pip install -r requirements-dev.txt
pytest -q
```

## 運用上の原則

- 公開情報・公式資料を優先し、各サイトの規約とrobots.txtを尊重する
- CAPTCHA、ログイン、アクセス制限を回避しない
- 未確認の傷・劣化を営業文で事実として断定しない
- 営業優先度は判断補助であり、人の確認を置き換えない
- 自動送信・無差別大量送信は行わない

MVP 1.0では、候補収集から営業・追客・分析・バックアップまでの一連の営業運用を完成範囲としています。
