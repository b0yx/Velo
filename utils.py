import json
import os
import platform
import subprocess
import logging
import ipaddress
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from io import BytesIO
from collections import Counter
from urllib.parse import urlparse
try:
    import requests
    from PIL import Image
except ImportError:
    pass  # Will be handled by missing dependencies check

SETTINGS_FILE = "settings.json"
HISTORY_FILE = "history.json"
LOG_FILE = "velo.log"
DATABASE_FILE = "velo_jobs.sqlite3"

SETTINGS_DEFAULTS = {
    "download_folder": str(Path.home() / "Downloads"),
    "default_quality": "best",
    "default_format": "video",
    "network_mode": "stable",
    "sponsorblock": False,
    "embed_metadata": False,
    "download_archive": False,
    "download_subtitles": False,
    "subtitle_languages": ["en"],
    "subtitle_source": "prefer_manual",
    "subtitle_format": "vtt",
    "embed_subtitles": True,
    "burn_subtitles": False,
    "browser_cookie_source": "none",
    "browser_profile": "",
    "organize_playlists": True,
    "include_video_id": True,
}


def get_logger():
    """Return Velo's bounded, UTF-8 application logger."""
    logger = logging.getLogger("velo")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    try:
        handler = RotatingFileHandler(
            get_app_dir() / LOG_FILE,
            maxBytes=1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
    except OSError:
        # A packaged read-only installation should still remain usable.
        logger.addHandler(logging.NullHandler())
    return logger

def get_app_dir():
    """Return the absolute path of the directory where main.py is located."""
    return Path(__file__).parent.absolute()

def get_settings_path():
    return get_app_dir() / SETTINGS_FILE

def get_history_path():
    return get_app_dir() / HISTORY_FILE


def get_database_path():
    return get_app_dir() / DATABASE_FILE


def validate_settings(settings):
    """Whitelist and normalize settings accepted from either UI."""
    settings = settings if isinstance(settings, dict) else {}
    result = dict(SETTINGS_DEFAULTS)

    folder_value = str(settings.get("download_folder", result["download_folder"]))
    folder = Path(folder_value).expanduser()
    if folder.is_absolute() or re.match(r"^[A-Za-z]:[\\/]", folder_value):
        result["download_folder"] = folder_value

    choices = {
        "default_format": {"video", "audio"},
        "network_mode": {"stable", "balanced", "turbo", "data_saver"},
        "subtitle_source": {"prefer_manual", "manual", "auto"},
        "subtitle_format": {"vtt", "srt", "best"},
        "browser_cookie_source": {"none", "firefox", "chrome", "chromium", "brave", "edge"},
    }
    for key, allowed in choices.items():
        value = settings.get(key)
        if value in allowed:
            result[key] = value

    quality = str(settings.get("default_quality", "best"))
    if quality == "best" or re.fullmatch(r"[1-9][0-9]{2,3}p", quality):
        result["default_quality"] = quality

    for key in (
        "sponsorblock", "embed_metadata", "download_archive",
        "download_subtitles", "embed_subtitles", "organize_playlists",
        "include_video_id", "burn_subtitles",
    ):
        if key in settings:
            result[key] = bool(settings[key])

    languages = settings.get("subtitle_languages", result["subtitle_languages"])
    if isinstance(languages, list):
        result["subtitle_languages"] = [
            str(code) for code in languages[:20]
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,34}", str(code))
        ] or ["en"]

    profile = str(settings.get("browser_profile", "")).strip()
    if re.fullmatch(r"[A-Za-z0-9._ -]{0,100}", profile):
        result["browser_profile"] = profile
    return result


def validate_media_url(url):
    """Accept remote HTTP(S) media URLs while blocking local-file/SSRF targets."""
    if not isinstance(url, str) or not 1 <= len(url) <= 4096:
        return False
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        hostname = parsed.hostname.lower().rstrip(".")
        if (hostname in {"localhost", "localhost.localdomain"}
                or hostname.endswith((".local", ".internal", ".lan", ".home", ".test"))):
            return False
        try:
            address = ipaddress.ip_address(hostname)
            if not address.is_global:
                return False
        except ValueError:
            if "." not in hostname:
                return False
        return True
    except ValueError:
        return False


def is_allowed_open_path(candidate, download_folder, history):
    """Limit open-file requests to the output root or exact history paths."""
    try:
        candidate = Path(candidate).expanduser().resolve()
        output_root = Path(download_folder).expanduser().resolve()
        if candidate == output_root or output_root in candidate.parents:
            return True
        for item in history:
            saved = item.get("filepath")
            if not saved:
                continue
            saved_path = Path(saved).expanduser().resolve()
            if candidate in {saved_path, saved_path.parent}:
                return True
    except (OSError, RuntimeError, TypeError, ValueError):
        return False
    return False


def find_incomplete_downloads(folder, limit=100):
    """Return resumable yt-dlp partial files inside the configured output root."""
    root = Path(folder).expanduser()
    if not root.exists() or not root.is_dir():
        return []
    results = []
    try:
        candidates = root.rglob("*.part")
        for path in candidates:
            try:
                stat = path.stat()
                results.append({
                    "path": str(path),
                    "name": path.name,
                    "size": stat.st_size,
                    "modified": __import__("datetime").datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                })
            except OSError:
                continue
            if len(results) >= limit:
                break
    except OSError:
        return []
    return sorted(results, key=lambda item: item["modified"], reverse=True)

def load_settings():
    """Load settings from JSON. Returns default settings if file doesn't exist."""
    default_settings = dict(SETTINGS_DEFAULTS)
    
    settings_path = get_settings_path()
    if settings_path.exists():
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                return validate_settings(settings)
        except Exception:
            return default_settings
    return default_settings

def save_settings(settings):
    """Save settings to JSON file."""
    try:
        with open(get_settings_path(), 'w', encoding='utf-8') as f:
            json.dump(validate_settings(settings), f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving settings: {e}")
        return False

def load_history():
    """Load download history from JSON."""
    history_path = get_history_path()
    if history_path.exists():
        try:
            with open(history_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []
    return []

def add_to_history(video_info, filepath):
    """Add a successful download to history."""
    history = load_history()
    entry = {
        "title": video_info.get("title", "Unknown Title"),
        "url": video_info.get("webpage_url", ""),
        "channel": video_info.get("uploader", "Unknown Channel"),
        "filepath": filepath,
        "timestamp": __import__("datetime").datetime.now().isoformat()
    }
    history.insert(0, entry)  # Add to beginning
    
    # Keep only last 50 entries
    if len(history) > 50:
        history = history[:50]
        
    try:
        with open(get_history_path(), 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=4)
    except Exception as e:
        print(f"Error saving history: {e}")

def clear_history():
    """Remove all saved history entries."""
    try:
        with open(get_history_path(), 'w', encoding='utf-8') as f:
            json.dump([], f, indent=4)
        return True
    except Exception as e:
        print(f"Error clearing history: {e}")
        return False

def get_history_stats():
    """Build lightweight analytics from saved history and local files."""
    history = load_history()
    channels = Counter()
    extensions = Counter()
    days = Counter()
    total_bytes = 0
    existing_files = 0
    missing_files = 0

    for item in history:
        channel = item.get("channel") or "Unknown Channel"
        channels[channel] += 1

        timestamp = item.get("timestamp", "")
        if timestamp:
            days[timestamp[:10]] += 1

        filepath = item.get("filepath") or ""
        suffix = Path(filepath).suffix.lower().lstrip(".") or "unknown"
        extensions[suffix] += 1

        path = Path(filepath)
        if path.exists() and path.is_file():
            existing_files += 1
            try:
                total_bytes += path.stat().st_size
            except OSError:
                pass
        elif filepath:
            missing_files += 1

    return {
        "total_items": len(history),
        "existing_files": existing_files,
        "missing_files": missing_files,
        "total_bytes": total_bytes,
        "channels": channels.most_common(8),
        "formats": extensions.most_common(),
        "daily": sorted(days.items(), reverse=True)[:14],
    }

def fetch_thumbnail(url):
    """Fetch an image from URL and return a PIL Image object."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        img_data = response.content
        img = Image.open(BytesIO(img_data))
        return img
    except Exception as e:
        print(f"Error fetching thumbnail: {e}")
        return None

def open_folder(path):
    """Cross-platform function to open a folder in the file manager."""
    path = Path(path)
    if not path.exists():
        return False
        
    if path.is_file():
        path = path.parent
        
    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception as e:
        print(f"Error opening folder: {e}")
        return False

def open_file(filepath):
    """Cross-platform function to open a file with its default application."""
    path = Path(filepath)
    if not path.exists() or not path.is_file():
        return False
        
    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception as e:
        print(f"Error opening file: {e}")
        return False

def vtt_to_md(vtt_filepath, video_info=None):
    """Parses a VTT file and creates a clean Markdown file."""
    vtt_path = Path(vtt_filepath)
    if not vtt_path.exists():
        return False
        
    md_path = vtt_path.with_suffix('.md')
    try:
        with open(vtt_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        clean_lines = []
        for line in lines:
            line = line.strip()
            # Skip VTT headers, empty lines, and timestamp lines
            if (not line or line.isdigit() or line.startswith('WEBVTT')
                    or line.startswith('Kind:') or line.startswith('Language:')
                    or '-->' in line):
                continue
            # Basic deduplication for auto-subs which repeat lines
            if clean_lines and clean_lines[-1] == line:
                continue
            clean_lines.append(line)
            
        with open(md_path, 'w', encoding='utf-8') as f:
            if video_info:
                f.write(f"# {video_info.get('title', 'Transcript')}\n\n")
                f.write(f"**Channel:** {video_info.get('uploader', 'Unknown')}\n")
                f.write(f"**URL:** {video_info.get('webpage_url', '')}\n\n")
                f.write("---\n\n")
            
            f.write(" ".join(clean_lines))
            
        return str(md_path)
    except Exception as e:
        print(f"Error converting VTT to MD: {e}")
        return False
