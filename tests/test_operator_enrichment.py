import sqlite3

from app import create_app
from operator_enrichment import discover_operator_pages, extract_operator_evidence, ready_candidates, register_operator_enrichment
from sales_activity import register_sales_activity


def test_extract_operator_evidence_from_body_and_contacts():
    html = '''
    <html><body>
      <div>運営会社：株式会社東北ステイ</div>
      <a href="tel:022-123-4567">電話</a>
      <a href="mailto:hello@example.jp">メール</a>
      <a href="/contact">お問い合わせ</a>
    </body></html>
    '''
    result = extract_operator_evidence(html, "https://example.jp/", "サンプル宿")
    assert result["company_name"] == "株式会社東北ステイ"
    assert result["phone"] == "022-123-4567"
    assert result["email"] == "hello@example.jp"
    assert result["contact_url"] == "https://example.jp/contact"


def test_discover_operator_pages_stays_same_origin_and_limits():
    html = '''
    <a href="/company">会社概要</a>
    <a href="/about">About</a>
    <a href="https://other.example/operator">運営会社</a>
    <a href="/legal">特定商取引</a>
    <a href="/extra-company">会社情報</a>
    '''
    pages = discover_operator_pages(html, "https://example.jp/stay", max_pages=3)
    assert pages == [
        "https://example.jp/company",
        "https://example.jp/about",
        "https://example.jp/legal",
    ]


def test_ready_candidates_returns_a_band(tmp_path):
    db_path = tmp_path / "operator-ready.db"
    app = create_app({"TESTING": True, "DATABASE": db_path, "APP_USERNAME": "", "APP_PASSWORD": ""})
    with sqlite3.connect(db_path) as con:
        con.execute('''INSERT INTO lead_candidates
          (name,company_name,prefecture,city,address,official_url,phone,pet_friendly,whole_house,
           research_status,source_url,source_type,normalized_key,status)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'pending')''',
          ("犬宿", "株式会社犬宿", "宮城県", "仙台市", "仙台市1", "https://example.jp", "022-000-0000", 1, 1,
           "researching", "src", "test", "operator|ready"))
        con.commit()
    rows = ready_candidates(db_path)
    assert len(rows) == 1
    assert rows[0]["band"] == "A"
    assert rows[0]["candidate"]["name"] == "犬宿"


def test_operator_enrichment_route_renders(tmp_path):
    db_path = tmp_path / "operator-route.db"
    app = create_app({"TESTING": True, "DATABASE": db_path, "APP_USERNAME": "", "APP_PASSWORD": ""})
    register_sales_activity(app)
    register_operator_enrichment(app)
    with sqlite3.connect(db_path) as con:
        con.execute('''INSERT INTO lead_candidates
          (name,prefecture,city,address,official_url,phone,pet_friendly,whole_house,
           research_status,source_url,source_type,normalized_key,status)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'pending')''',
          ("調査宿", "宮城県", "仙台市", "仙台市2", "https://example.jp", "022-111-1111", 1, 1,
           "researching", "src", "test", "operator|route"))
        con.commit()
    response = app.test_client().get("/operator-enrichment")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "運営会社・連絡先の自動特定" in body
    assert "調査宿" in body
    assert "営業文を作成" in body
