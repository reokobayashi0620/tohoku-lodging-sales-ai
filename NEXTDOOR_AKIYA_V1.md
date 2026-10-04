# NexT DooR Akiya Buyer Funnel v1

This repository now contains the first end-to-end content pipeline for overseas Tohoku akiya buyer acquisition.

Daily flow: public municipal sources → resilient parsers → merged factual candidate data → static English SEO property summaries → social drafts → NexT DooR buyer inquiry.

## Guardrails
- Never bypass access controls. A blocked municipal source is skipped and logged.
- Do not copy listing photographs unless reuse permission is confirmed.
- Property pages summarize factual public data and link to the original source.
- NexT DooR/officeMK is positioned for local field support, not unlicensed brokerage.
- Social publishing remains approval-gated.
- One source failure must not stop the other prefectures.

## Generated output
- `docs/index.html`
- `docs/properties/*.html`
- `docs/sitemap.xml`
- `docs/robots.txt`
- `akiya_content_engine/output/social_drafts.md`

The workflow is scheduled daily and can also be run manually from GitHub Actions.
