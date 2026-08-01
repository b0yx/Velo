from downloader import VeloDownloader, configure_subtitles, normalize_subtitle_languages


def test_normalize_subtitle_languages_accepts_explicit_codes_only():
    assert normalize_subtitle_languages([" en ", "ar", "en", "zh-Hans", ".*", "-live_chat"]) == [
        "en",
        "ar",
        "zh-Hans",
    ]


def test_configure_subtitles_downloads_and_embeds_multiple_languages():
    options = {}

    configure_subtitles(
        options,
        download_subtitles=True,
        subtitle_languages=["en", "ar"],
        embed_subtitles=True,
    )

    assert options["writesubtitles"] is True
    assert options["writeautomaticsub"] is True
    assert options["subtitleslangs"] == ["en", "ar"]
    assert options["subtitlesformat"] == "vtt/best"
    assert options["sleep_interval_subtitles"] == 1.5
    assert options["ignoreerrors"] is True
    assert options["retry_sleep_functions"]["http"](0) == 1
    assert options["retry_sleep_functions"]["http"](10) == 20
    assert options["postprocessors"] == [{
        "key": "FFmpegEmbedSubtitle",
        "already_have_subtitle": True,
    }]


def test_transcript_adds_english_without_enabling_embedded_subtitles():
    options = {}

    configure_subtitles(options, download_transcript=True)

    assert options["subtitleslangs"] == ["en"]
    assert options["writeautomaticsub"] is True
    assert "writesubtitles" not in options
    assert "postprocessors" not in options


def test_manual_srt_subtitles_are_converted_before_embedding():
    options = {}

    configure_subtitles(
        options,
        download_subtitles=True,
        subtitle_languages=["ar"],
        subtitle_source="manual",
        subtitle_format="srt",
    )

    assert options["writesubtitles"] is True
    assert options["writeautomaticsub"] is False
    assert options["postprocessors"][0] == {
        "key": "FFmpegSubtitlesConvertor",
        "format": "srt",
    }
    assert options["postprocessors"][1]["key"] == "FFmpegEmbedSubtitle"


def test_playlist_result_path_uses_a_real_downloaded_entry(tmp_path):
    downloaded = tmp_path / "episode.mp4"
    downloaded.write_bytes(b"video")
    info = {
        "_type": "playlist",
        "entries": [{
            "title": "Episode",
            "requested_downloads": [{"filepath": str(downloaded)}],
        }],
    }

    class FakeYDL:
        @staticmethod
        def prepare_filename(entry):
            return str(tmp_path / "playlist.NA")

    assert VeloDownloader._playlist_result_path(info, FakeYDL()) == str(downloaded)


def test_playlist_item_payload_reports_progress_and_processing():
    downloading = VeloDownloader._playlist_item_payload({
        "status": "downloading",
        "downloaded_bytes": 50,
        "total_bytes": 200,
        "info_dict": {
            "id": "episode-2",
            "title": "Episode 2",
            "playlist_index": 2,
            "playlist_count": 10,
        },
    })
    finished = VeloDownloader._playlist_item_payload({
        "status": "finished",
        "info_dict": {"title": "Episode 2", "playlist_index": 2},
    })

    assert downloading == {
        "index": 2,
        "total": 10,
        "id": "episode-2",
        "title": "Episode 2",
        "status": "downloading",
        "progress": 25.0,
    }
    assert finished["status"] == "processing"
    assert finished["progress"] == 100


def test_non_playlist_progress_does_not_create_checklist_item():
    assert VeloDownloader._playlist_item_payload({
        "status": "downloading",
        "info_dict": {"id": "single-video"},
    }) is None
