import os
import re
import csv
import io
import shutil
import subprocess
import uuid
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response
import threading
import queue
import time
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import tkinter as tk
from tkinter import filedialog

from downloader import VeloDownloader
from clipper import process_clip
from job_store import JobStore
from utils import (
    add_to_history, clear_history, find_incomplete_downloads, get_database_path,
    get_history_stats, get_logger, is_allowed_open_path, load_history,
    load_settings, open_file, open_folder, save_settings, validate_media_url,
    validate_settings,
)

APP_VERSION = "1.1.0-pro"

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True

progress_queue = queue.Queue()
downloader = None
logger = get_logger()
job_store = JobStore(get_database_path())


@app.after_request
def secure_response(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
    return response

# Batch Queue System
batch_queue = queue.Queue()
is_batch_running = False
batch_control = {
    "paused": False,
    "stop_requested": False,
    "total": 0,
    "completed": 0,
    "failed": 0,
    "current_url": "",
    "current_index": 0,
    "last_started_at": None,
    "failed_jobs": [],
    "logs": [],
}
batch_lock = threading.Lock()
active_batch_downloader = None
background_jobs_initialized = False
current_batch_id = job_store.latest_batch_id()


def download_config_from_request(data):
    """Normalize request options against saved, whitelisted preferences."""
    data = data if isinstance(data, dict) else {}
    saved = load_settings()
    candidate = dict(saved)
    candidate.update({
        "default_format": data.get("format", saved["default_format"]),
        "default_quality": data.get("quality", saved["default_quality"]),
        "network_mode": data.get("network_mode", saved["network_mode"]),
        "download_subtitles": data.get("download_subtitles", saved["download_subtitles"]),
        "subtitle_languages": data.get("subtitle_languages", saved["subtitle_languages"]),
        "subtitle_source": data.get("subtitle_source", saved["subtitle_source"]),
        "subtitle_format": data.get("subtitle_format", saved["subtitle_format"]),
        "embed_subtitles": data.get("embed_subtitles", saved["embed_subtitles"]),
        "burn_subtitles": data.get("burn_subtitles", saved["burn_subtitles"]),
        "browser_cookie_source": data.get("browser_cookie_source", saved["browser_cookie_source"]),
        "browser_profile": data.get("browser_profile", saved["browser_profile"]),
        "organize_playlists": data.get("organize_playlists", saved["organize_playlists"]),
        "include_video_id": data.get("include_video_id", saved["include_video_id"]),
    })
    normalized = validate_settings(candidate)
    playlist_items = data.get("playlist_items")
    if not isinstance(playlist_items, str) or not re.fullmatch(
            r"[1-9][0-9]*(?:,[1-9][0-9]*){0,999}", playlist_items):
        playlist_items = None
    return {
        "folder": normalized["download_folder"],
        "format": normalized["default_format"],
        "quality": normalized["default_quality"],
        "network_mode": normalized["network_mode"],
        "single_video": bool(data.get("single_video", True)),
        "playlist_items": playlist_items,
        "download_transcript": bool(data.get("download_transcript", False)),
        "sponsorblock": bool(data.get("sponsorblock", saved["sponsorblock"])),
        "embed_metadata": bool(data.get("embed_metadata", saved["embed_metadata"])),
        "download_archive": bool(data.get("download_archive", saved["download_archive"])),
        "download_subtitles": normalized["download_subtitles"],
        "subtitle_languages": normalized["subtitle_languages"],
        "subtitle_source": normalized["subtitle_source"],
        "subtitle_format": normalized["subtitle_format"],
        "embed_subtitles": normalized["embed_subtitles"],
        "burn_subtitles": normalized["burn_subtitles"],
        "browser_cookie_source": normalized["browser_cookie_source"],
        "browser_profile": normalized["browser_profile"],
        "organize_playlists": normalized["organize_playlists"],
        "include_video_id": normalized["include_video_id"],
        "night_mode": bool(data.get("night_mode", False)),
    }

def reset_batch_state(total, batch_id=""):
    global current_batch_id
    current_batch_id = batch_id or current_batch_id
    with batch_lock:
        batch_control.update({
            "paused": False,
            "stop_requested": False,
            "total": total,
            "completed": 0,
            "failed": 0,
            "current_url": "",
            "current_index": 0,
            "last_started_at": None,
            "failed_jobs": [],
            "logs": [],
        })

def add_batch_log(status, url, message, filepath=None):
    entry = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "url": url,
        "message": message,
        "filepath": filepath or "",
    }
    with batch_lock:
        batch_control["logs"].insert(0, entry)
        batch_control["logs"] = batch_control["logs"][:200]

def get_batch_state():
    with batch_lock:
        state = dict(batch_control)
        state["queued"] = batch_queue.qsize()
        state["running"] = is_batch_running
    persisted = job_store.state(batch_id=current_batch_id)
    state.update({
        "queued": persisted["queued"],
        "completed": persisted["completed"],
        "failed": persisted["failed"],
        "failed_jobs": persisted["failed_jobs"],
        "jobs": persisted["jobs"],
    })
    return state

def batch_worker():
    global is_batch_running, active_batch_downloader
    while True:
        try:
            job = batch_queue.get(timeout=1.0)
        except queue.Empty:
            break

        if job is None:
            batch_queue.task_done()
            break
            
        url = job['url']
        config = job['config']
        job_id = job.get('id') or job.get('job_id')
        index = job['index']
        total = job['total']

        if job_id:
            persisted_job = job_store.get(job_id)
            if not persisted_job or persisted_job['status'] != 'queued':
                batch_queue.task_done()
                continue

        while get_batch_state()["paused"]:
            progress_queue.put({'type': 'batch_paused'})
            time.sleep(0.8)

        night_mode = config.get('night_mode', False)
        if night_mode:
            while datetime.now().hour != 2:
                if get_batch_state()["stop_requested"] or get_batch_state()["paused"]:
                    break
                progress_queue.put({'type': 'batch_status', 'index': index, 'total': total, 'url': url, 'message': 'Waiting for 2 AM...'})
                time.sleep(10)

        if get_batch_state()["stop_requested"]:
            add_batch_log("skipped", url, "Skipped because queue was stopped")
            if job.get('id'):
                job_store.update(job['id'], status="skipped")
            batch_queue.task_done()
            continue

        with batch_lock:
            batch_control["current_url"] = url
            batch_control["current_index"] = index
            batch_control["last_started_at"] = datetime.now().isoformat(timespec="seconds")
        if job_id:
            job_store.update(job_id, status="running", progress=0)
        
        progress_queue.put({'type': 'batch_status', 'index': index, 'total': total, 'url': url})
        
        # Block until download completes
        event = threading.Event()
        last_progress_write = [0.0]
        
        def c_prog(d):
            if d['status'] == 'downloading':
                t = d.get('total_bytes') or d.get('total_bytes_estimate', 1)
                dl = d.get('downloaded_bytes', 0)
                if t:
                    p = (dl / t) * 100
                    progress_queue.put({'type': 'batch_progress', 'percent': f"{p:.1f}%"})
                    if job_id and time.monotonic() - last_progress_write[0] >= 1:
                        job_store.update(job_id, progress=p)
                        last_progress_write[0] = time.monotonic()
                    
        def c_succ(filepath, info):
            add_to_history(info, filepath)
            missing_subtitles = info.get('velo_missing_subtitles', [])
            subtitle_warnings = info.get('velo_subtitle_warnings', [])
            with batch_lock:
                batch_control["completed"] += 1
            message = info.get('title', url)
            if missing_subtitles:
                message += f" (subtitles unavailable: {', '.join(missing_subtitles)})"
            if subtitle_warnings:
                message += f" ({'; '.join(subtitle_warnings)})"
            add_batch_log("warning" if missing_subtitles or subtitle_warnings else "success", url, message, filepath)
            if job_id:
                job_store.update(job_id, status="completed", progress=100, filepath=filepath, error="")
            progress_queue.put({
                'type': 'batch_item_success',
                'filepath': filepath,
                'title': info.get('title', url),
                'missing_subtitles': missing_subtitles,
                'subtitle_warnings': subtitle_warnings,
            })
            event.set()
            
        def c_err(msg):
            stopped = get_batch_state()["stop_requested"]
            if stopped:
                add_batch_log("skipped", url, "Stopped by user")
                if job_id:
                    job_store.update(job_id, status="skipped", error="Stopped by user")
            else:
                with batch_lock:
                    batch_control["failed"] += 1
                    batch_control["failed_jobs"].append(job)
                add_batch_log("error", url, msg)
                if job_id:
                    job_store.update(job_id, status="failed", error=msg)
                progress_queue.put({'type': 'batch_item_error', 'message': msg, 'url': url})
            event.set()
            
        def c_info(info):
            pass # Ignore info fetches in batch

        batch_dl = VeloDownloader(on_progress=c_prog, on_success=c_succ, on_error=c_err, on_info_fetched=c_info)
        active_batch_downloader = batch_dl
        folder = config.get("folder", str(Path.home() / "Downloads"))
        
        batch_dl.download(
            url, folder, 
            format_type=config.get('format', 'video'), 
            quality=config.get('quality', 'best'), 
            single_video=True, 
            download_transcript=config.get('download_transcript', False),
            sponsorblock=config.get('sponsorblock', False),
            embed_metadata=config.get('embed_metadata', False),
            network_mode=config.get('network_mode', 'stable'),
            download_archive=config.get('download_archive', False),
            download_subtitles=config.get('download_subtitles', False),
            subtitle_languages=config.get('subtitle_languages', []),
            embed_subtitles=config.get('embed_subtitles', True),
            subtitle_source=config.get('subtitle_source', 'prefer_manual'),
            subtitle_format=config.get('subtitle_format', 'vtt'),
            browser_cookie_source=config.get('browser_cookie_source', 'none'),
            browser_profile=config.get('browser_profile', ''),
            organize_playlists=config.get('organize_playlists', True),
            include_video_id=config.get('include_video_id', True),
            burn_subtitles=config.get('burn_subtitles', False),
        )
        
        event.wait() # Wait for this download to finish before taking the next
        active_batch_downloader = None
        batch_queue.task_done()

    is_batch_running = False
    with batch_lock:
        batch_control["current_url"] = ""
        batch_control["current_index"] = 0
    progress_queue.put({'type': 'batch_complete'})


def initialize_background_jobs():
    """Restore queued jobs once when the actual server process starts."""
    global background_jobs_initialized, is_batch_running, current_batch_id
    if background_jobs_initialized:
        return
    background_jobs_initialized = True
    pending = job_store.pending()
    if not pending:
        return
    current_batch_id = pending[-1].get("batch_id") or current_batch_id
    total = len(pending)
    reset_batch_state(total, current_batch_id)
    for index, job in enumerate(pending, 1):
        job.update({"index": index, "total": total})
        batch_queue.put(job)
    is_batch_running = True
    threading.Thread(target=batch_worker, daemon=True).start()
    logger.info("Restored %s queued download jobs", total)

def handle_progress(d):
    progress_queue.put({'type': 'progress', 'data': d})

def handle_success(filepath, info):
    logger.info("Web download succeeded: %s", filepath)
    add_to_history(info, filepath)
    progress_queue.put({'type': 'success', 'filepath': filepath, 'info': info})

def handle_error(msg):
    logger.error("Web operation failed: %s", msg)
    progress_queue.put({'type': 'error', 'message': msg})

def handle_info(info):
    progress_queue.put({'type': 'info', 'data': info})


def handle_playlist_item_update(item):
    progress_queue.put({'type': 'playlist_item_update', 'item': item})


def handle_playlist_item_complete(item):
    progress_queue.put({'type': 'playlist_item_complete', 'item': item})

downloader = VeloDownloader(
    on_progress=handle_progress,
    on_success=handle_success,
    on_error=handle_error,
    on_info_fetched=handle_info,
    on_item_update=handle_playlist_item_update,
    on_item_complete=handle_playlist_item_complete,
)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/meta', methods=['GET'])
def api_meta():
    import shutil
    return jsonify({
        "name": "Velo",
        "version": APP_VERSION,
        "status": "ready",
        "features": [
            "low_bandwidth_modes",
            "batch_queue",
            "clip_maker",
            "history_stats",
            "multilingual_ui",
            "multilingual_subtitles",
            "reports",
            "persistent_queue",
            "download_recovery",
            "browser_cookies",
            "diagnostics",
        ],
        "ffmpeg_available": shutil.which("ffmpeg") is not None,
        "ffprobe_available": shutil.which("ffprobe") is not None,
    })

@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    if request.method == 'POST':
        settings = validate_settings(request.get_json(silent=True) or {})
        folder = Path(settings['download_folder'])
        if not folder.exists() or not folder.is_dir():
            return jsonify({"error": "Download folder must be an existing directory"}), 400
        if not save_settings(settings):
            return jsonify({"error": "Unable to save settings"}), 500
        return jsonify({"status": "success"})
    settings = load_settings()
    if 'download_folder' not in settings:
        settings['download_folder'] = str(Path.home() / "Downloads")
    return jsonify(settings)

@app.route('/api/select_folder', methods=['POST'])
def api_select_folder():
    def get_folder():
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        folder = filedialog.askdirectory(title="Select Download Folder")
        root.destroy()
        return folder
        
    folder = get_folder()
    if folder:
        settings = load_settings()
        settings['download_folder'] = folder
        save_settings(settings)
        return jsonify({"folder": folder})
    return jsonify({"error": "No folder selected"}), 400

@app.route('/api/history', methods=['GET', 'DELETE'])
def api_history():
    if request.method == 'DELETE':
        if clear_history():
            return jsonify({"status": "cleared"})
        return jsonify({"error": "Unable to clear history"}), 500
    return jsonify(load_history())

@app.route('/api/stats', methods=['GET'])
def api_stats():
    return jsonify(get_history_stats())

@app.route('/api/report', methods=['GET'])
def api_report():
    fmt = request.args.get("format", "json").lower()
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "app_version": APP_VERSION,
        "stats": get_history_stats(),
        "history": load_history(),
        "batch": get_batch_state(),
    }
    if fmt == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=["title", "channel", "url", "filepath", "timestamp"])
        writer.writeheader()
        for item in payload["history"]:
            writer.writerow({
                "title": item.get("title", ""),
                "channel": item.get("channel", ""),
                "url": item.get("url", ""),
                "filepath": item.get("filepath", ""),
                "timestamp": item.get("timestamp", ""),
            })
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=velo-history-report.csv"},
        )
    return jsonify(payload)

@app.route('/api/estimate', methods=['POST'])
def api_estimate():
    data = request.json or {}
    url = data.get('url')
    if not validate_media_url(url):
        return jsonify({"error": "A valid public HTTP(S) URL is required"}), 400

    result_queue = queue.Queue()

    def done(info):
        formats = info.get("formats", []) if isinstance(info, dict) else []
        candidates = []
        for item in formats:
            size = item.get("filesize") or item.get("filesize_approx")
            if not size:
                continue
            candidates.append({
                "format_id": item.get("format_id"),
                "ext": item.get("ext"),
                "height": item.get("height"),
                "resolution": item.get("resolution"),
                "filesize": size,
                "format_note": item.get("format_note"),
                "vcodec": item.get("vcodec"),
                "acodec": item.get("acodec"),
                "fps": item.get("fps"),
                "tbr": item.get("tbr"),
                "dynamic_range": item.get("dynamic_range"),
                "protocol": item.get("protocol"),
            })
        candidates = sorted(candidates, key=lambda row: row.get("filesize", 0))
        result_queue.put({
            "title": info.get("title", ""),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail", ""),
            "smallest": candidates[:5],
            "largest": candidates[-5:],
            "known_formats": len(candidates),
        })

    def fail(message):
        result_queue.put({"error": message})

    temp = VeloDownloader(on_info_fetched=done, on_error=fail)
    config = download_config_from_request(data)
    temp.fetch_info(
        url,
        single_video=True,
        browser_cookie_source=config['browser_cookie_source'],
        browser_profile=config['browser_profile'],
    )

    try:
        result = result_queue.get(timeout=30)
    except queue.Empty:
        return jsonify({"error": "Unable to estimate size before timeout"}), 504

    status = 400 if "error" in result else 200
    return jsonify(result), status

@app.route('/api/fetch', methods=['POST'])
def api_fetch():
    data = request.get_json(silent=True) or {}
    url = data.get('url')
    single_video = data.get('single_video', True)
    if 'list' in parse_qs(urlparse(url or '').query):
        single_video = False
    
    if not validate_media_url(url):
        return jsonify({"error": "A valid public HTTP(S) URL is required"}), 400
    config = download_config_from_request(data)
        
    threading.Thread(target=downloader.fetch_info, args=(url, single_video), kwargs={
        'browser_cookie_source': config['browser_cookie_source'],
        'browser_profile': config['browser_profile'],
    }, daemon=True).start()
    return jsonify({"status": "fetching"})

@app.route('/api/download', methods=['POST'])
def api_download():
    data = request.get_json(silent=True) or {}
    url = data.get('url')
    if not validate_media_url(url):
        return jsonify({"error": "A valid public HTTP(S) URL is required"}), 400
    config = download_config_from_request(data)
    config.pop('night_mode', None)
        
    threading.Thread(target=downloader.download, args=(
        url, config.pop('folder'), config.pop('format'), config.pop('quality')),
        kwargs=config, daemon=True).start()
    return jsonify({"status": "downloading"})

@app.route('/api/batch', methods=['POST'])
def api_batch():
    global is_batch_running
    data = request.get_json(silent=True) or {}
    urls = data.get('urls', [])
    config = download_config_from_request(data.get('config', {}))
    
    if not urls:
        return jsonify({"error": "No URLs provided"}), 400
    invalid_urls = [url for url in urls if not validate_media_url(url)]
    if invalid_urls:
        return jsonify({"error": "Every batch item must be a valid public HTTP(S) URL", "invalid": invalid_urls[:5]}), 400

    batch_id = uuid.uuid4().hex
    reset_batch_state(len(urls), batch_id)
        
    for i, url in enumerate(urls):
        job = job_store.create(url, config, batch_id=batch_id)
        job.update({
            'index': i + 1,
            'total': len(urls)
        })
        batch_queue.put(job)
        
    if not is_batch_running:
        is_batch_running = True
        threading.Thread(target=batch_worker, daemon=True).start()
        
    return jsonify({"status": "batch queued", "count": len(urls)})

@app.route('/api/batch/state', methods=['GET'])
def api_batch_state():
    return jsonify(get_batch_state())

@app.route('/api/batch/control', methods=['POST'])
def api_batch_control():
    global is_batch_running, active_batch_downloader
    data = request.json or {}
    action = data.get("action")

    with batch_lock:
        if action == "pause":
            batch_control["paused"] = True
        elif action == "resume":
            batch_control["paused"] = False
        elif action == "stop":
            batch_control["stop_requested"] = True
            batch_control["paused"] = False
            job_store.skip_queued()
        elif action == "retry_failed":
            failed_jobs = list(batch_control["failed_jobs"])
            batch_control["failed_jobs"] = []
            batch_control["failed"] = 0
            batch_control["stop_requested"] = False
            batch_control["paused"] = False
        else:
            return jsonify({"error": "Unknown batch action"}), 400

    if action == "retry_failed":
        failed_jobs = job_store.retry_failed(current_batch_id)
        if not failed_jobs:
            return jsonify({"status": "no failed jobs"})
        total = len(failed_jobs)
        for i, job in enumerate(failed_jobs):
            job["index"] = i + 1
            job["total"] = total
            batch_queue.put(job)
        with batch_lock:
            batch_control["total"] = total
            batch_control["completed"] = 0
            batch_control["current_index"] = 0
            batch_control["current_url"] = ""
        if not is_batch_running:
            is_batch_running = True
            threading.Thread(target=batch_worker, daemon=True).start()

    if action == "stop" and active_batch_downloader:
        active_batch_downloader.cancel()

    return jsonify({"status": action, "batch": get_batch_state()})

@app.route('/api/clip', methods=['POST'])
def api_clip():
    data = request.get_json(silent=True) or {}
    url = data.get('url')
    if not validate_media_url(url):
        return jsonify({"error": "A valid public HTTP(S) URL is required"}), 400
    try:
        start_time = int(data.get('start_time', 0))
        end_time = int(data.get('end_time', 0))
    except ValueError:
        return jsonify({"error": "Start and End times must be numbers"}), 400
        
    top_text = data.get('top_text', '')
    bottom_text = data.get('bottom_text', '')
    format_type = data.get('format_type', 'Short (9:16 MP4)')
    
    if not url or start_time is None or end_time is None:
        return jsonify({"error": "Missing parameters"}), 400
        
    def clip_task():
        progress_queue.put({'type': 'clip_status', 'message': 'Downloading segment...'})
        
        def c_prog(d):
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 1)
                dl = d.get('downloaded_bytes', 0)
                if total:
                    percent = (dl / total) * 100
                    progress_queue.put({'type': 'clip_progress', 'percent': f"{percent:.1f}%"})
                
        def c_succ(filepath, info):
            progress_queue.put({'type': 'clip_status', 'message': 'Processing via FFmpeg...'})
            is_short = format_type == "Short (9:16 MP4)"
            is_gif = format_type == "Meme GIF"
            
            output_file = str(Path(filepath).with_name(f"clip_{Path(filepath).name}"))
            
            success, msg_or_path = process_clip(
                filepath, output_file, 
                start_time=None, end_time=None, 
                top_text=top_text, bottom_text=bottom_text, 
                is_short=is_short, is_gif=is_gif
            )
            
            if success:
                progress_queue.put({'type': 'clip_success', 'filepath': msg_or_path})
            else:
                progress_queue.put({'type': 'clip_error', 'message': msg_or_path})
                
        def c_err(msg):
            progress_queue.put({'type': 'clip_error', 'message': msg})
            
        clip_dl = VeloDownloader(on_progress=c_prog, on_success=c_succ, on_error=c_err)
        settings = load_settings()
        folder = settings.get("download_folder", str(Path.home() / "Downloads"))
        
        clip_dl.download(
            url, folder, format_type='video', quality='best', single_video=True,
            clip_start=start_time, clip_end=end_time,
            browser_cookie_source=settings['browser_cookie_source'],
            browser_profile=settings['browser_profile'],
        )

    threading.Thread(target=clip_task, daemon=True).start()
    return jsonify({"status": "clipping started"})

@app.route('/api/cancel', methods=['POST'])
def api_cancel():
    downloader.cancel()
    return jsonify({"status": "cancelled"})

@app.route('/api/open', methods=['POST'])
def api_open():
    data = request.get_json(silent=True) or {}
    path = data.get('path')
    is_folder = data.get('is_folder', False)
    if path:
        settings = load_settings()
        history = load_history()
        if not is_allowed_open_path(path, settings['download_folder'], history):
            return jsonify({"error": "Path is outside Velo's managed downloads"}), 403
        opened = open_folder(path) if is_folder else open_file(path)
        if opened:
            return jsonify({"status": "opened"})
        return jsonify({"error": "Path does not exist or could not be opened"}), 404
    return jsonify({"error": "No path"}), 400


def command_version(command):
    executable = shutil.which(command)
    if not executable:
        return {"available": False, "version": "Not installed"}
    try:
        completed = subprocess.run(
            [executable, "-version"], capture_output=True, text=True, timeout=5,
        )
        first_line = (completed.stdout or completed.stderr).splitlines()[0]
        return {"available": completed.returncode == 0, "version": first_line}
    except (OSError, subprocess.SubprocessError, IndexError):
        return {"available": False, "version": "Unable to inspect"}


@app.route('/api/diagnostics', methods=['GET'])
def api_diagnostics():
    from yt_dlp.version import __version__ as yt_dlp_version

    settings = load_settings()
    folder = Path(settings['download_folder'])
    try:
        usage = shutil.disk_usage(folder)
        disk = {"total": usage.total, "used": usage.used, "free": usage.free}
        writable = os.access(folder, os.W_OK)
    except OSError:
        disk = {"total": 0, "used": 0, "free": 0}
        writable = False
    return jsonify({
        "velo_version": APP_VERSION,
        "yt_dlp_version": yt_dlp_version,
        "ffmpeg": command_version("ffmpeg"),
        "ffprobe": command_version("ffprobe"),
        "download_folder": str(folder),
        "folder_exists": folder.is_dir(),
        "folder_writable": writable,
        "disk": disk,
        "incomplete_count": len(find_incomplete_downloads(folder)),
        "queue": job_store.state(limit=20, batch_id=current_batch_id),
    })


@app.route('/api/logs', methods=['GET'])
def api_logs():
    log_path = Path(__file__).with_name("velo.log")
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lines = []
    requested = request.args.get("lines", "200")
    count = max(1, min(int(requested) if requested.isdigit() else 200, 1000))
    return jsonify({"lines": lines[-count:]})


@app.route('/api/verify', methods=['POST'])
def api_verify():
    data = request.get_json(silent=True) or {}
    path = data.get('path', '')
    settings = load_settings()
    if not is_allowed_open_path(path, settings['download_folder'], load_history()):
        return jsonify({"error": "Path is outside Velo's managed downloads"}), 403
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return jsonify({"error": "ffprobe is not installed"}), 503
    try:
        completed = subprocess.run([
            ffprobe, "-v", "error", "-show_entries",
            "format=duration,size,format_name:stream=index,codec_type,codec_name,width,height:stream_tags=language",
            "-of", "json", str(Path(path)),
        ], capture_output=True, text=True, timeout=20)
        if completed.returncode != 0:
            return jsonify({"error": completed.stderr.strip() or "Media verification failed"}), 422
        return jsonify({"status": "valid", "probe": json.loads(completed.stdout)})
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        return jsonify({"error": str(error)}), 500


@app.route('/api/recovery', methods=['GET', 'DELETE'])
def api_recovery():
    settings = load_settings()
    if request.method == 'GET':
        return jsonify(find_incomplete_downloads(settings['download_folder']))
    data = request.get_json(silent=True) or {}
    path = data.get('path', '')
    if not path.endswith('.part') or not is_allowed_open_path(
            path, settings['download_folder'], load_history()):
        return jsonify({"error": "Invalid partial-download path"}), 403
    partial = Path(path)
    try:
        partial.unlink()
        logger.info("Removed incomplete download: %s", partial)
        return jsonify({"status": "removed"})
    except FileNotFoundError:
        return jsonify({"error": "Partial file no longer exists"}), 404
    except OSError as error:
        return jsonify({"error": str(error)}), 500

@app.route('/stream')
def stream():
    def event_stream():
        while True:
            try:
                item = progress_queue.get(timeout=1.0)
                yield f"data: {json.dumps(item)}\n\n"
            except queue.Empty:
                yield ": ping\n\n"
    return Response(event_stream(), mimetype="text/event-stream")

if __name__ == '__main__':
    initialize_background_jobs()
    app.run(port=5000, debug=False)
