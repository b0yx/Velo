<div align="center">

# 🚀 Velo
**Your Local Media Workspace & Viral Content Engine**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/Flask-Backend-green.svg)](https://flask.palletsprojects.com/)
[![yt-dlp](https://img.shields.io/badge/yt--dlp-Downloader-red.svg)](https://github.com/yt-dlp/yt-dlp)

*Download videos, extract audio, create short clips, and manage batch queues locally.*

</div>

---

## 📖 Overview

**Velo** is a fully localized media workspace designed for efficiency and robustness. It offers a premium, modern web dashboard that runs entirely in your browser, powered locally by Flask and `yt-dlp`. 

Built specifically to handle real-world network conditions—including unstable and low-bandwidth connections—Velo provides the ultimate toolkit for media management and history tracking without relying on cloud services.

---

## ✨ Highlights

*   **🌗 Local Web Dashboard**: A sleek, Vercel-inspired interface with light/dark mode support.
*   **📶 Resilient Network Modes**: Choose from *Stable*, *Balanced*, *Turbo*, and *Data Saver* to adapt to your connection.
*   **🛠️ Versatile Workflows**: Support for single video downloads, audio extraction, batch queues, and precise clip making.
*   **💬 Multi-language Subtitles**: Select several authored or automatic subtitle languages, keep sidecar files, and optionally embed switchable tracks in MP4 videos.
*   **⏯️ Advanced Queue Controls**: Pause, resume, stop, retry failed items, deduplicate links, and requeue directly from history.
*   **💾 Restart Recovery**: Batch jobs persist in SQLite and queued work resumes after restarting Velo.
*   **✅ Playlist Checklist**: Analyze a playlist, select individual episodes, and track pending, downloading, processing, completed, or skipped videos like a to-do list.
*   **🩺 Health Center**: Inspect FFmpeg, ffprobe, yt-dlp, disk space, logs, and incomplete downloads from Settings.
*   **🔐 Browser Authentication**: Optionally use a local browser profile for content that requires an authenticated session.
*   **📊 Insights & Statistics**: Built-in dashboard tracking total downloads, storage usage, top channels, formats, and daily activity.
*   **📁 Seamless Management**: Search history, filter by channel, copy file paths, and open folders directly from the UI.
*   **🌍 Multilingual**: UI foundation with support for English and Arabic.
*   **📄 Exportable Reports**: Export your download history in JSON or CSV formats.

---

## ⚙️ Requirements

Before you begin, ensure you have the following installed:

- 🐍 **Python 3.11** or newer.
- 🎬 **FFmpeg** (Must be installed and available on your system's PATH).
- 🌐 **Internet Access** (For downloading media and initial CDN assets).

### Installing FFmpeg (Windows)
```powershell
winget install ffmpeg
```

---

## 🚀 Setup & Installation

Get Velo running locally in a few simple steps:

1. **Create and activate a virtual environment**:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. **Install dependencies**:
   ```powershell
   pip install -r requirements.txt
   ```

   Contributors can install the test and packaging tools with:
   ```powershell
   pip install -r requirements-dev.txt
   ```

3. **Start the application**:
   ```powershell
   python main.py
   ```
   *Alternatively, on Windows, simply double-click or run: `.\run_velo.bat`*

4. **Open the Dashboard**:  
   The application will automatically be available at: [http://127.0.0.1:5000](http://127.0.0.1:5000)

---

## 🌐 Recommended Network Settings

Optimize your experience based on your internet connection:

| Mode | Use Case |
| :--- | :--- |
| **📉 Low Bandwidth** | Best for downloading the smallest practical file sizes. |
| **🛡️ Data Saver** | Ideal when your connection disconnects frequently. |
| **⚓ Stable** | Perfect for when downloads fail midway and require multiple retries. |
| **⚖️ Balanced** | Recommended for connections that are slow but mostly steady. |
| **⚡ Turbo** | Use only when your connection is strong enough to handle parallel fragments. |

---

## 🔌 API Overview

Velo provides a comprehensive local API for developers:

*   `GET /api/meta` - App metadata and feature flags.
*   `GET /api/settings` & `POST /api/settings` - Read and save user configurations.
*   `GET /api/history` & `DELETE /api/history` - Retrieve or clear download history.
*   `GET /api/stats` - Access computed statistics from local history.
*   `GET /api/report?format=json|csv` - Export detailed reports.
*   `POST /api/estimate` - Estimate file sizes for known formats.
*   `POST /api/fetch` - Fetch video metadata and information.
*   `POST /api/download` - Initiate a single file download.
*   `POST /api/batch` - Queue a batch download job.
*   `GET /api/batch/state` - Inspect the current state of batch jobs.
*   `POST /api/batch/control` - Pause, resume, stop, or retry jobs.
*   `POST /api/clip` - Generate a specified media clip.
*   `GET /api/diagnostics` - Inspect dependencies, storage, and queue health.
*   `GET /api/logs` - Read the bounded local application log.
*   `GET` & `DELETE /api/recovery` - Inspect or remove incomplete `.part` downloads.
*   `POST /api/verify` - Validate a managed media file and inspect its streams with ffprobe.

Browser authentication reads cookies directly through yt-dlp. Velo never writes cookie values to its application log. Use this option only with a local browser profile you trust.

---

## 🧪 Testing

Install the development dependencies and run the complete test suite:

```powershell
pip install -r requirements-dev.txt
python -m pytest
```

---

## 📦 Packaging for Production

To create a standalone executable with the bundled templates, fonts, and static assets:

```powershell
pip install -r requirements-dev.txt
pyinstaller --clean Velo.spec
```

The packaged application is written to `dist/Velo`. FFmpeg must still be installed on the target system and available on `PATH`.

---

## 🖋️ Font Assets

The Arabic UI text utilizes locally bundled **Thmanyah Sans** `woff2` files. If you fork or distribute this application, please ensure you retain the original font license and verify that your use case complies with their terms.

---

## ⚖️ Responsible Use

> [!WARNING]  
> **Velo** does not bypass DRM or access private, restricted content. Please ensure you only download media that you have the right to save, reuse, or archive.
