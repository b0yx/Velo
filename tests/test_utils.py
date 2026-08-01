import json
from pathlib import Path

import utils


def test_settings_defaults_are_merged(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "get_app_dir", lambda: tmp_path)
    (tmp_path / utils.SETTINGS_FILE).write_text(
        json.dumps({"download_folder": "D:/Media"}),
        encoding="utf-8",
    )

    settings = utils.load_settings()

    assert settings["download_folder"] == "D:/Media"
    assert settings["default_quality"] == "best"
    assert settings["default_format"] == "video"
    assert settings["network_mode"] == "stable"
    assert settings["organize_playlists"] is True


def test_media_url_validation_blocks_local_targets():
    assert utils.validate_media_url("https://www.youtube.com/watch?v=abc") is True
    assert utils.validate_media_url("file:///etc/passwd") is False
    assert utils.validate_media_url("http://127.0.0.1:8000/private") is False
    assert utils.validate_media_url("http://localhost/private") is False


def test_open_path_is_limited_to_downloads_and_history(tmp_path):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    media = downloads / "video.mp4"
    media.write_bytes(b"video")
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")

    assert utils.is_allowed_open_path(media, downloads, []) is True
    assert utils.is_allowed_open_path(outside, downloads, []) is False
    assert utils.is_allowed_open_path(outside, downloads, [{"filepath": str(outside)}]) is True


def test_clear_history_empties_history_file(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "get_app_dir", lambda: tmp_path)
    (tmp_path / utils.HISTORY_FILE).write_text(
        json.dumps([{"title": "Example"}]),
        encoding="utf-8",
    )

    assert utils.clear_history() is True
    assert utils.load_history() == []


def test_history_stats_counts_files_channels_and_formats(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "get_app_dir", lambda: tmp_path)
    media = tmp_path / "video.mp4"
    media.write_bytes(b"12345")
    missing = tmp_path / "missing.mp3"
    history = [
        {
            "title": "Video",
            "channel": "Channel A",
            "filepath": str(media),
            "timestamp": "2026-05-17T10:00:00",
        },
        {
            "title": "Audio",
            "channel": "Channel A",
            "filepath": str(missing),
            "timestamp": "2026-05-17T11:00:00",
        },
    ]
    (tmp_path / utils.HISTORY_FILE).write_text(json.dumps(history), encoding="utf-8")

    stats = utils.get_history_stats()

    assert stats["total_items"] == 2
    assert stats["existing_files"] == 1
    assert stats["missing_files"] == 1
    assert stats["total_bytes"] == 5
    assert stats["channels"][0] == ("Channel A", 2)
    assert ("mp4", 1) in stats["formats"]
    assert stats["daily"][0] == ("2026-05-17", 2)
