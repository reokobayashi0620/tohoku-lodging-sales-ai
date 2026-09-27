# Akiya Buyer Content Engine

海外の「日本・東北の空き家を買いたい人」を集客するための投稿生成MVPです。

## MVP flow

1. 東北6県の自治体・空き家バンク等の公開ページを監視
2. 新着/更新候補のURLと事実情報を保存
3. 投稿候補を英語向けに再構成
4. Instagram / Facebook 用の原稿を生成
5. 人間が内容・出典・画像利用可否を確認
6. 承認済みだけ投稿
7. CTAは NexT DooR の購入希望者フォームへ
8. 問い合わせを officeMK が確認し、購入支援パートナーへ引き継ぐ

## Safety rules

- 物件ページの文章をそのまま転載しない。
- 元ページURLと取得日時を必ず保存する。
- 価格、所在地、面積等は「掲載時点の情報」として扱い、最新情報は元ページで確認する。
- 写真は利用許可/ライセンスが確認できた場合のみ再利用する。不明ならNexT DooR独自の情報カードを使う。
- 各サイトの利用規約、robots.txt、アクセス制限に従う。禁止サイトは収集対象にしない。
- 売買の仲介・契約業務をNexT DooR/officeMK自身が行う表現は避ける。
- 初期運用は自動投稿せず、必ず human approval を通す。

## Initial post format

**Akiya Find — [Prefecture], Japan**

A home currently listed in [area], Tohoku.

- Asking price: [price]
- Property type: [type]
- Building: [size]
- Land: [size]
- Notable features: [facts only]

Interested in finding a home in Tohoku?
Tell us your preferred area and budget through NexT DooR.

Source: [official listing URL]
Listing information may change. Please confirm current availability and details with the original source.

## Data schema

See `data/akiya_content_candidates.example.csv`.

## Next implementation

The next step is to add source adapters only for pages whose terms permit the intended retrieval/reuse, then generate approval-ready drafts. Meta publishing credentials are intentionally not stored in this repository.
