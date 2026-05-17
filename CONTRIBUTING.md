# Contributing to Velo

First off, thank you for considering contributing to Velo! It's people like you that make Velo such a powerful and resilient local media tool.

This guide outlines our developer onboarding process, local environment setup, and submission guidelines.

---

## 🛠️ Local Development Setup

To get set up for local development and start contributing, please follow these steps:

### 1. Prerequisites

Ensure you have the following installed on your machine:

* 🐍 **Python 3.11** or newer.
* 🎬 **FFmpeg** (Crucial for audio extraction, clipping, and metadata embedding).

> [!TIP]
> **Installing FFmpeg:**
>
> * **Windows:** `winget install ffmpeg`
> * **macOS:** `brew install ffmpeg`
> * **Linux (Ubuntu/Debian):** `sudo apt install ffmpeg`

### 2. Environment Installation

1. **Clone the repository:**

    ```bash
    git clone https://github.com/your-username/Velo.git
    cd Velo
    ```

2. **Create and activate a virtual environment:**

    ```bash
    # Windows
    python -m venv .venv
    .\.venv\Scripts\activate

    # macOS / Linux
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3. **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

---

## 🚀 Running Velo

Velo is a dual-interface application. You can develop or run either client locally:

### A. Developing the Web Dashboard

Start the local Flask development server:

```bash
python main.py
```

Then open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser. Live templates are configured to auto-reload.

### B. Developing the CustomTkinter Desktop GUI

Launch the cross-platform GUI client:

```bash
python ui.py
```

---

## 🧪 Testing and Formatting

We value robust code testing. Please ensure all existing tests pass and write new tests for any added helper functionality.

* **Running the PyTest suite:**

    ```bash
    python -m pytest
    ```

* **Style Guide:**
  * We follow the **PEP 8** style guide for Python.
  * Please make sure your code uses relative paths for resources (such as assets/logos) so it remains portable across other platforms.

---

## 🤝 Submission Guidelines

1. **Search first**: Check existing issues and PRs to see if your bug or feature is already discussed.
2. **Create a branch**: Use descriptive branch names like `feature/smart-sync` or `bugfix/issue-102`.
3. **Keep it focused**: Keep pull requests focused on a single issue or improvement.
4. **Write comments**: Maintain code clarity by commenting on any complex custom logic, especially within `batch_worker` or `yt-dlp` integration blocks.

Thank you again for helping us make **Velo** the ultimate offline media engine! 🚀
