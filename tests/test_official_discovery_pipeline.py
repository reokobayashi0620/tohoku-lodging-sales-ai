from official_discovery_pipeline import register_official_discovery_pipeline


def test_official_pipeline_route_registered(tmp_path):
    import app as app_module
    app = app_module.create_app({"TESTING": True, "DATABASE": str(tmp_path / "sales.db"), "SECRET_KEY": "test"})
    register_official_discovery_pipeline(app)
    rules = {rule.rule: rule.methods for rule in app.url_map.iter_rules()}
    assert "/targets/run-official-pipeline" in rules
    assert "POST" in rules["/targets/run-official-pipeline"]
