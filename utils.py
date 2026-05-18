import json
import os
import platform
import subprocess
from pathlib import Path
from io import BytesIO
from collections import Counter
try:
    import requests
    from PIL import Image
except ImportError:
    pass  # Will be handled by missing dependencies check

SETTINGS_FILE = "settings.json"
HISTORY_FILE = "history.json"

def get_app_dir():
    """Return the absolute path of the directory where main.py is located."""
    return Path(__file__).parent.absolute()

def get_settings_path():
    return get_app_dir() / SETTINGS_FILE

def get_history_path():
    return get_app_dir() / HISTORY_FILE

def load_settings():
    """Load settings from JSON. Returns default settings if file doesn't exist."""
    default_settings = {
        "download_folder": str(Path.home() / "Downloads"),
        "default_quality": "best",
        "default_format": "video",
        "network_mode": "stable",
        "sponsorblock": False,
        "embed_metadata": False,
        "download_archive": False
    }
    
    settings_path = get_settings_path()
    if settings_path.exists():
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                # Merge with defaults to ensure all keys exist
                for k, v in default_settings.items():
                    if k not in settings:
                        settings[k] = v
                return settings
        except Exception:
            return default_settings
    return default_settings

def save_settings(settings):
    """Save settings to JSON file."""
    try:
        with open(get_settings_path(), 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=4)
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
            if not line or line.startswith('WEBVTT') or line.startswith('Kind:') or line.startswith('Language:') or '-->' in line:
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

def get_playlists_path():
    return get_app_dir() / "playlists.json"

def load_playlists():
    """Load the list of installed/subscribed playlists."""
    playlists_path = get_playlists_path()
    if playlists_path.exists():
        try:
            with open(playlists_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_playlists(playlists):
    """Save the list of installed/subscribed playlists."""
    try:
        with open(get_playlists_path(), 'w', encoding='utf-8') as f:
            json.dump(playlists, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving playlists: {e}")
        return False

