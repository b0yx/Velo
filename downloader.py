import re
import subprocess
import threading
import traceback
from pathlib import Path

import yt_dlp

from utils import get_logger, vtt_to_md


SUBTITLE_LANGUAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,34}$")


def normalize_subtitle_languages(languages):
    """Return a safe, de-duplicated list of explicit subtitle language codes."""
    if isinstance(languages, str):
        languages = languages.split(',')
    if not isinstance(languages, (list, tuple)):
        return []

    normalized = []
    for language in languages[:20]:
        code = str(language).strip()
        if code and SUBTITLE_LANGUAGE_RE.fullmatch(code) and code not in normalized:
            normalized.append(code)
    return normalized


def configure_subtitles(ydl_opts, download_subtitles=False,
                        subtitle_languages=None, embed_subtitles=True,
                        download_transcript=False, subtitle_source='prefer_manual',
                        subtitle_format='vtt'):
    """Add yt-dlp subtitle options, preferring authored tracks over auto captions."""
    languages = normalize_subtitle_languages(subtitle_languages)
    if download_transcript and 'en' not in languages:
        languages.append('en')

    if not languages:
        return

    ydl_opts['writeautomaticsub'] = subtitle_source in {'prefer_manual', 'auto'} or download_transcript
    ydl_opts['subtitleslangs'] = languages
    ydl_opts['subtitlesformat'] = 'vtt/best' if subtitle_format == 'srt' else f'{subtitle_format}/best'

    if download_subtitles:
        ydl_opts['writesubtitles'] = subtitle_source in {'prefer_manual', 'manual'}
        # Automatic-caption endpoints are commonly rate-limited. Pace subtitle
        # requests, retry with backoff, and keep subtitle failures non-fatal so
        # an optional track cannot discard an otherwise successful video.
        ydl_opts['sleep_interval_subtitles'] = 1.5
        ydl_opts.setdefault('retry_sleep_functions', {})['http'] = (
            lambda attempt: min(2 ** attempt, 20))
        ydl_opts['ignoreerrors'] = True
        if subtitle_format == 'srt':
            ydl_opts.setdefault('postprocessors', []).append({
                'key': 'FFmpegSubtitlesConvertor',
                'format': 'srt',
            })
        if embed_subtitles:
            ydl_opts.setdefault('postprocessors', []).append({
                'key': 'FFmpegEmbedSubtitle',
                # Keep the language-labelled sidecar files as well as embedding them.
                'already_have_subtitle': True,
            })


class VeloDownloader:
    def __init__(self, 
                 on_progress=None, 
                 on_success=None, 
                 on_error=None,
                 on_info_fetched=None,
                 on_item_update=None,
                 on_item_complete=None):
        """
        Initializes the downloader with callbacks.
        on_progress: function(d) - Called during download with a dictionary of progress info.
        on_success: function(filepath) - Called when download completes successfully.
        on_error: function(error_message) - Called if an error occurs.
        on_info_fetched: function(info_dict) - Called when video metadata is successfully fetched.
        """
        self.on_progress = on_progress
        self.on_success = on_success
        self.on_error = on_error
        self.on_info_fetched = on_info_fetched
        self.on_item_update = on_item_update
        self.on_item_complete = on_item_complete
        self.logger = get_logger()
        self._ydl_logger = YtDlpLogger(self.logger)
        
        self.is_cancelled = False
        self._current_thread = None

    def cancel(self):
        """Signals the current download to stop."""
        self.is_cancelled = True

    def fetch_info(self, url, single_video=True, browser_cookie_source='none',
                   browser_profile=''):
        """Fetches video metadata in a separate thread."""
        if not url:
            if self.on_error:
                self.on_error("Please enter a valid URL.")
            return

        def _fetch():
            ydl_opts = {
                'quiet': True,
                'no_warnings': False,
                'logger': self._ydl_logger,
                'extract_flat': 'in_playlist',
                'skip_download': True,
                'noplaylist': single_video,
                # These also make extractors expose authored and automatic
                # subtitle languages in the metadata returned to the UIs.
                'writesubtitles': True,
                'writeautomaticsub': True,
            }
            self._apply_browser_cookies(
                ydl_opts, browser_cookie_source, browser_profile)
            try:
                self.logger.info("Fetching metadata for %s", url)
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if self.on_info_fetched:
                        self.on_info_fetched(info)
            except Exception as e:
                self.logger.exception("Metadata fetch failed for %s", url)
                if self.on_error:
                    self.on_error(f"Failed to fetch video info: {str(e)}")

        thread = threading.Thread(target=_fetch, daemon=True)
        thread.start()

    def download(self, url, folder_path, format_type='video', quality='best',
                 single_video=True, playlist_items=None, download_transcript=False,
                 clip_start=None, clip_end=None, sponsorblock=False,
                 embed_metadata=False, network_mode='stable',
                 download_archive=False, download_subtitles=False,
                 subtitle_languages=None, embed_subtitles=True,
                 subtitle_source='prefer_manual', subtitle_format='vtt',
                 browser_cookie_source='none', browser_profile='',
                 organize_playlists=True, include_video_id=True,
                 burn_subtitles=False):
        """
        Starts the download in a separate thread.
        format_type: 'video' (MP4) or 'audio' (MP3)
        quality: '360p', '720p', '1080p', or 'best'
        network_mode: 'stable', 'balanced', 'turbo', or 'data_saver'
        """
        self.is_cancelled = False
        download_subtitles = download_subtitles and format_type == 'video'
        burn_subtitles = burn_subtitles and download_subtitles
        
        if not Path(folder_path).exists():
            if self.on_error:
                self.on_error("Selected output folder does not exist.")
            return

        subtitle_languages = normalize_subtitle_languages(subtitle_languages)
        if download_subtitles and not subtitle_languages:
            if self.on_error:
                self.on_error("Select at least one subtitle language.")
            return

        def _download():
            title_template = '%(title)s [%(id)s]' if include_video_id else '%(title)s'
            if organize_playlists and not single_video:
                output_template = f'%(playlist_title|Playlist)s/%(playlist_index)03d - {title_template}.%(ext)s'
            else:
                output_template = f'{title_template}.%(ext)s'
            completed_paths = []
            current_playlist_item = {}

            def progress_hook(data):
                self._progress_hook(data)
                payload = self._playlist_item_payload(data)
                if not payload:
                    return
                current_playlist_item.update(payload)
                if self.on_item_update:
                    try:
                        self.on_item_update(payload)
                    except Exception:
                        self.logger.exception("Playlist item update callback failed")

            def post_hook(filepath):
                completed_paths.append(filepath)
                if current_playlist_item.get('index') is None or not self.on_item_complete:
                    return
                payload = dict(current_playlist_item)
                payload.update({"status": "completed", "progress": 100, "filepath": filepath})
                try:
                    self.on_item_complete(payload)
                except Exception:
                    self.logger.exception("Playlist item completion callback failed")

            ydl_opts = {
                'outtmpl': str(Path(folder_path) / output_template),
                'progress_hooks': [progress_hook],
                'post_hooks': [post_hook],
                'quiet': True,
                'no_warnings': False,
                'logger': self._ydl_logger,
                'noplaylist': single_video,
                'continuedl': True,
                'retries': 20,
                'fragment_retries': 20,
                'file_access_retries': 5,
                'extractor_retries': 5,
                'socket_timeout': 30,
                'trim_file_name': 180,
            }
            self._apply_browser_cookies(
                ydl_opts, browser_cookie_source, browser_profile)

            if network_mode == 'turbo':
                ydl_opts.update({
                    'concurrent_fragment_downloads': 6,
                    'http_chunk_size': 10 * 1024 * 1024,
                    'retries': 10,
                    'fragment_retries': 10,
                })
            elif network_mode == 'balanced':
                ydl_opts.update({
                    'concurrent_fragment_downloads': 3,
                    'http_chunk_size': 5 * 1024 * 1024,
                })
            elif network_mode == 'data_saver':
                ydl_opts.update({
                    'concurrent_fragment_downloads': 2,
                    'http_chunk_size': 2 * 1024 * 1024,
                    'retries': 30,
                    'fragment_retries': 30,
                    'socket_timeout': 45,
                })
            if playlist_items:
                ydl_opts['playlist_items'] = playlist_items
            configure_subtitles(
                ydl_opts,
                download_subtitles=download_subtitles,
                subtitle_languages=subtitle_languages,
                embed_subtitles=embed_subtitles and format_type == 'video',
                download_transcript=download_transcript,
                subtitle_source=subtitle_source,
                subtitle_format=subtitle_format,
            )
            if clip_start is not None and clip_end is not None:
                ydl_opts['download_ranges'] = yt_dlp.utils.download_range_func(None, [(clip_start, clip_end)])

            if download_archive:
                ydl_opts['download_archive'] = str(Path(folder_path) / 'velo_archive.txt')

            if sponsorblock:
                ydl_opts['sponsorblock_remove'] = ['sponsor', 'intro', 'outro', 'interaction']

            if format_type == 'audio':
                ydl_opts['format'] = 'bestaudio/best'
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '96' if network_mode == 'data_saver' else '192',
                }]
            else:
                # Video format logic
                if network_mode == 'data_saver':
                    ydl_opts['format'] = 'bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]/worst[ext=mp4]/worst'
                    ydl_opts['merge_output_format'] = 'mp4'
                elif quality == 'best':
                    # Best video + best audio, merged into mp4 if possible
                    ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
                    ydl_opts['merge_output_format'] = 'mp4'
                else:
                    # Specific quality (e.g., '1080p' -> '1080')
                    height = quality.replace('p', '')
                    # Prefer MP4 if possible, but fallback to best available for the selected resolution
                    ydl_opts['format'] = f'bestvideo[height={height}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height={height}]+bestaudio/best[height={height}]'
                    ydl_opts['merge_output_format'] = 'mp4'
            
            if embed_metadata:
                ydl_opts['writethumbnail'] = True
                if 'postprocessors' not in ydl_opts:
                    ydl_opts['postprocessors'] = []
                ydl_opts['postprocessors'].append({
                    'key': 'FFmpegMetadata',
                    'add_metadata': True,
                })
                ydl_opts['postprocessors'].append({
                    'key': 'EmbedThumbnail',
                    'already_have_thumbnail': False,
                })

            try:
                self.logger.info(
                    "Starting download url=%s format=%s quality=%s subtitle_languages=%s embed_subtitles=%s",
                    url, format_type, quality, subtitle_languages if download_subtitles else [],
                    embed_subtitles and format_type == 'video',
                )
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    if self.is_cancelled:
                        return # Cancelled, error callback already called in hook
                    if not info:
                        if self.on_error:
                            self.on_error("The media download failed before an output file was created.")
                        return

                    requested_subtitles = info.get('requested_subtitles') or {}
                    if download_subtitles:
                        info['velo_missing_subtitles'] = [
                            language for language in subtitle_languages
                            if not Path(requested_subtitles.get(language, {}).get('filepath', '')).exists()
                        ]

                    filepath = ydl.prepare_filename(info)
                    if completed_paths:
                        filepath = completed_paths[-1]
                    if info.get('_type') == 'playlist' or info.get('entries'):
                        filepath = self._playlist_result_path(info, ydl) or filepath
                    
                    # If audio, yt-dlp might change the extension to mp3 post-processing
                    if format_type == 'audio':
                        base_path = Path(filepath).with_suffix('.mp3')
                        filepath = str(base_path)

                    if burn_subtitles and format_type == 'video' and subtitle_languages:
                        selected = requested_subtitles.get(subtitle_languages[0], {})
                        subtitle_path = selected.get('filepath')
                        if subtitle_path and Path(subtitle_path).exists():
                            success, warning = self._burn_subtitle(filepath, subtitle_path)
                            if not success:
                                info.setdefault('velo_subtitle_warnings', []).append(warning)

                    if download_transcript:
                        transcript_path = requested_subtitles.get('en', {}).get('filepath')
                        if not transcript_path:
                            for extension in ('vtt', 'srt'):
                                candidate = Path(filepath).with_suffix(f'.en.{extension}')
                                if candidate.exists():
                                    transcript_path = str(candidate)
                                    break
                        if transcript_path and Path(transcript_path).exists():
                            vtt_to_md(str(transcript_path), info)

                    if self.on_success:
                        self.logger.info("Download completed: %s", filepath)
                        self.on_success(filepath, info)
                        
            except yt_dlp.utils.DownloadError as e:
                self.logger.error("Download failed for %s: %s", url, e)
                if self.is_cancelled:
                    pass # Handled in hook
                elif self.on_error:
                    self.on_error(f"Download Error: {str(e)}")
            except Exception as e:
                self.logger.exception("Unexpected download failure for %s", url)
                if not self.is_cancelled and self.on_error:
                    self.on_error(f"An unexpected error occurred: {str(e)}\n{traceback.format_exc()}")

        self._current_thread = threading.Thread(target=_download, daemon=True)
        self._current_thread.start()

    @staticmethod
    def _apply_browser_cookies(ydl_opts, browser, profile):
        if browser in {'firefox', 'chrome', 'chromium', 'brave', 'edge'}:
            ydl_opts['cookiesfrombrowser'] = (browser, profile or None, None, None)

    def _burn_subtitle(self, filepath, subtitle_path):
        """Render one selected subtitle track into the video image."""
        source = Path(filepath)
        if not source.exists():
            return False, "Downloaded video was not found for subtitle rendering"
        escaped = str(Path(subtitle_path).resolve())
        for original, replacement in (
                ('\\', '\\\\'), (':', '\\:'), ("'", "\\'"),
                ('[', '\\['), (']', '\\]'), (',', '\\,')):
            escaped = escaped.replace(original, replacement)
        temporary = source.with_name(f"{source.stem}.burning{source.suffix}")
        command = [
            'ffmpeg', '-y', '-i', str(source), '-vf', f"subtitles=filename='{escaped}'",
            '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-c:a', 'copy',
            str(temporary),
        ]
        try:
            completed = subprocess.run(command, capture_output=True, text=True)
            if completed.returncode != 0:
                temporary.unlink(missing_ok=True)
                self.logger.error("Burning subtitles failed: %s", completed.stderr[-2000:])
                return False, "FFmpeg could not render the selected subtitle track"
            temporary.replace(source)
            return True, ""
        except OSError as error:
            temporary.unlink(missing_ok=True)
            self.logger.error("Burning subtitles failed: %s", error)
            return False, str(error)

    @staticmethod
    def _playlist_result_path(info, ydl):
        """Return a real downloaded item path instead of a playlist's .NA path."""
        for entry in reversed(list(info.get('entries') or [])):
            if not entry:
                continue
            candidates = [entry.get('filepath'), entry.get('_filename')]
            candidates.extend(
                item.get('filepath') for item in (entry.get('requested_downloads') or [])
                if item
            )
            for candidate in candidates:
                if candidate and Path(candidate).exists():
                    return candidate
            prepared = ydl.prepare_filename(entry)
            if prepared and Path(prepared).exists():
                return prepared
        return None

    def _progress_hook(self, d):
        """Hook for yt-dlp progress."""
        if self.is_cancelled:
            if d['status'] == 'downloading':
                # Attempt to stop download by raising an exception
                if self.on_error:
                    self.on_error("Download cancelled by user.")
                raise yt_dlp.utils.DownloadCancelled('Download cancelled by user.')
            return

        if self.on_progress:
            self.on_progress(d)

    @staticmethod
    def _playlist_item_payload(data):
        info = data.get('info_dict') or {}
        index = info.get('playlist_index')
        if index is None:
            return None
        total = info.get('playlist_count') or info.get('n_entries')
        total_bytes = data.get('total_bytes') or data.get('total_bytes_estimate') or 0
        downloaded = data.get('downloaded_bytes') or 0
        progress = (downloaded / total_bytes * 100) if total_bytes else 0
        status = data.get('status', 'pending')
        if status == 'finished':
            status = 'processing'
            progress = 100
        return {
            "index": int(index),
            "total": int(total) if total else None,
            "id": info.get('id'),
            "title": info.get('title') or f"Playlist item {index}",
            "status": status,
            "progress": round(progress, 1),
        }


class YtDlpLogger:
    """Adapter that sends yt-dlp output to Velo's rotating log file."""

    def __init__(self, logger):
        self.logger = logger

    def debug(self, message):
        # yt-dlp sends ordinary informational lines through debug().
        self.logger.info(message)

    def info(self, message):
        self.logger.info(message)

    def warning(self, message):
        self.logger.warning(message)

    def error(self, message):
        self.logger.error(message)
