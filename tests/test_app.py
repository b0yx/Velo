import app as app_module


def test_security_headers_and_local_url_rejection():
    client = app_module.app.test_client()

    response = client.get("/api/meta")
    assert response.status_code == 200
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"

    assert client.post("/api/fetch", json={"url": "file:///etc/passwd"}).status_code == 400
    assert client.post("/api/download", json={"url": "http://127.0.0.1/private"}).status_code == 400


def test_recovery_lists_partial_downloads(tmp_path, monkeypatch):
    partial = tmp_path / "video.mp4.part"
    partial.write_bytes(b"partial")
    settings = app_module.load_settings()
    settings["download_folder"] = str(tmp_path)
    monkeypatch.setattr(app_module, "load_settings", lambda: settings)

    response = app_module.app.test_client().get("/api/recovery")

    assert response.status_code == 200
    assert response.get_json()[0]["path"] == str(partial)
