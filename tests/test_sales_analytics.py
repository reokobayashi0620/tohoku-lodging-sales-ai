import sqlite3

from app import create_app
from sales_activity import register_sales_activity
from sales_analytics import build_metrics, register_sales_analytics, safe_rate


def test_safe_rate_handles_zero_and_rounding():
    assert safe_rate(1, 3) == 33.3
    assert safe_rate(0, 0) == 0.0


def test_build_metrics_calculates_theme_and_prefecture_rates():
    rows = [
        {"activity_type": "sent", "theme_key": "floor_repair", "prefecture": "宮城県"},
        {"activity_type": "sent", "theme_key": "floor_repair", "prefecture": "宮城県"},
        {"activity_type": "replied", "theme_key": "floor_repair", "prefecture": "宮城県"},
        {"activity_type": "estimate", "theme_key": "floor_repair", "prefecture": "宮城県"},
        {"activity_type": "won", "theme_key": "floor_repair", "prefecture": "宮城県"},
    ]
    overall, themes, prefectures, best_theme, best_prefecture = build_metrics(rows)
    assert overall["sent"] == 2
    assert overall["reply_rate"] == 50.0
    assert overall["estimate_rate"] == 50.0
    assert overall["win_rate"] == 50.0
    assert best_theme["key"] == "floor_repair"
    assert best_theme["win_rate"] == 50.0
    assert best_prefecture["prefecture"] == "宮城県"
    assert next(r for r in prefectures if r["prefecture"] == "宮城県")["reply_rate"] == 50.0
    assert next(r for r in themes if r["key"] == "floor_repair")["sent"] == 2


def test_sales_analytics_route_renders_metrics(tmp_path):
    db_path = tmp_path / "analytics.db"
    app = create_app({"TESTING": True, "DATABASE": db_path, "APP_USERNAME": "", "APP_PASSWORD": ""})
    register_sales_activity(app)
    register_sales_analytics(app)

    with sqlite3.connect(db_path) as con:
        cursor = con.execute("""INSERT INTO lead_candidates
          (name,prefecture,city,address,source_url,source_type,normalized_key,status)
          VALUES (?,?,?,?,?,?,?,'pending')""",
          ("分析宿", "宮城県", "仙台市", "仙台市青葉区1", "src", "test", "analytics|1"))
        candidate_id = cursor.lastrowid
        con.executemany(
            "INSERT INTO sales_activities (candidate_id,activity_type,theme_key,channel,note) VALUES (?,?,?,?,?)",
            [
                (candidate_id, "sent", "pet_damage", "email", "送信"),
                (candidate_id, "replied", "pet_damage", "email", "返信"),
                (candidate_id, "estimate", "pet_damage", "email", "見積"),
            ],
        )

    response = app.test_client().get("/sales-analytics")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "営業分析ダッシュボード" in body
    assert "返信率" in body
    assert "100.0%" in body
    assert "宮城県" in body
    assert "ペット傷・汚れ対策" in body
