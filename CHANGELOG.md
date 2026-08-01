# Changelog

## 1.1.0-pro

- Added a selectable playlist checklist with per-video progress, completion states, and locally preserved status.
- Added persistent SQLite batch jobs with restart recovery and per-job progress.
- Added browser-profile authentication for supported local browsers.
- Expanded subtitles with manual/automatic source preference and VTT/SRT output.
- Added organized, collision-safe playlist filenames and exact final-path tracking.
- Added runtime diagnostics, rotating logs, disk checks, and incomplete-download cleanup.
- Added richer codec, frame-rate, protocol, and HDR format information.
- Hardened local APIs with URL validation, managed-path checks, settings validation, and security headers.
- Redesigned the web interface as a compact desktop workspace with a contextual inspector and keyboard command palette.
- Added continuous integration and corrected standalone packaging for bundled web and font assets.

## 1.0.0-pro

- Added low-bandwidth network modes and a Low Bandwidth preset.
- Added batch queue controls: pause, resume, stop, retry failed, dedupe, and queue from history.
- Added download size estimates when source formats expose sizes.
- Added statistics dashboard for history, storage, local file availability, channels, formats, and daily activity.
- Added report export as JSON and CSV.
- Added multilingual UI foundation with English and Arabic.
- Added app metadata endpoint and visible version.
- Added launcher script for Windows.
- Added focused tests for settings, history, and statistics helpers.
