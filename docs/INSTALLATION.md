# Installation Guide — F.R.I.D.A.Y.

This guide covers installing FRIDAY on a Windows machine from scratch.

---

## Table of Contents

- [System Requirements](#system-requirements)
- [Step 1 — Python Setup](#step-1--python-setup)
- [Step 2 — Clone the Repository](#step-2--clone-the-repository)
- [Step 3 — Create a Virtual Environment](#step-3--create-a-virtual-environment)
- [Step 4 — Install Python Dependencies](#step-4--install-python-dependencies)
- [Step 5 — Install Playwright Browser](#step-5--install-playwright-browser)
- [Step 6 — Configure Environment Variables](#step-6--configure-environment-variables)
- [Step 7 — Verify the Installation](#step-7--verify-the-installation)
- [Step 8 — Run FRIDAY](#step-8--run-friday)
- [Optional: Autostart on Login](#optional-autostart-on-login)
- [Troubleshooting](#troubleshooting)

---

## System Requirements

| Component | Minimum | Recommended |
|---|---|---|
| OS | Windows 10 64-bit | Windows 11 64-bit |
| Python | 3.10 | 3.11 or 3.12 |
| RAM | 4 GB | 8 GB |
| Disk | 2 GB free | 4 GB free |
| Microphone | Optional | Required for voice |
| Internet | Required (for AI API calls) | — |

> **Note:** The PyQt6 overlay, `pycaw` (volume control), and `pywin32` (Windows APIs) are Windows-only. FRIDAY does not support macOS or Linux.

---

## Step 1 — Python Setup

1. Download **Python 3.11** from [python.org](https://www.python.org/downloads/).
2. During installation, check **"Add Python to PATH"**.
3. Verify:

```powershell
python --version
# Python 3.11.x
```

---

## Step 2 — Clone the Repository

```powershell
git clone https://github.com/josi1219/F.R.I.D.A.Y.git
cd friday
```

Or download and extract the ZIP from GitHub.

---

## Step 3 — Create a Virtual Environment

Using a virtual environment prevents dependency conflicts with other Python projects.

```powershell
python -m venv venv
venv\Scripts\activate
```

Your prompt will change to `(venv)`. Always activate this environment before running FRIDAY.

---

## Step 4 — Install Python Dependencies

```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

This installs all required packages including Flask, edge-tts, faster-whisper, PyQt6, google-genai, and ~30 other libraries. It may take several minutes.

### PyAudio on Windows

If `PyAudio` fails to install, use the pre-built wheel:

```powershell
pip install pipwin
pipwin install pyaudio
```

### faster-whisper models

The first time FRIDAY starts, `faster-whisper` will automatically download the configured Whisper model (default: `tiny.en`, ~75 MB) to `~/.cache/huggingface/`.

Available model sizes:

| Model | Size | Speed | Accuracy |
|---|---|---|---|
| `tiny.en` | 75 MB | Fastest | Good for commands |
| `base.en` | 145 MB | Fast | Better accuracy |
| `small.en` | 465 MB | Medium | High accuracy |
| `medium.en` | 1.5 GB | Slow | Very high accuracy |

Configure via `WHISPER_MODEL` in `.env`.

### OpenWakeWord (optional, for wake word)

OpenWakeWord is included in `requirements.txt`. On first run, it downloads the `hey_jarvis` model (~5 MB) automatically.

---

## Step 5 — Install Playwright Browser

FRIDAY uses Playwright for browser automation. Install the Chromium browser:

```powershell
playwright install chromium
```

This downloads a standalone Chromium binary (~150 MB) managed by Playwright.

---

## Step 6 — Configure Environment Variables

```powershell
copy .env.example .env
```

Open `.env` in a text editor and fill in at minimum:

```dotenv
GEMINI_API_KEY=your_key_here
SECRET_KEY=some_random_string_here
```

Get a free Gemini API key at [aistudio.google.com](https://aistudio.google.com/app/apikey).

See [CONFIGURATION.md](CONFIGURATION.md) for all available options.

---

## Step 7 — Verify the Installation

Run a quick sanity check:

```powershell
python -c "import flask, edge_tts, PyQt6, google.genai; print('All core imports OK')"
```

Check that FRIDAY's config loads:

```powershell
python -c "import config; print('AI provider:', config.AI_PROVIDER)"
```

---

## Step 8 — Run FRIDAY

### Recommended: Full experience

```powershell
python run_overlay.py
```

Open `http://localhost:5000` in your browser. The overlay widget will appear bottom-right on your desktop.

### Web UI only (no voice/overlay)

```powershell
python app.py
```

### Desktop window (pywebview)

```powershell
python run_desktop.py
```

### 24/7 production mode

```powershell
python watchdog.py
```

---

## Optional: Autostart on Login

Run the provided setup script to register FRIDAY as a Windows startup item:

```powershell
setup_autostart.bat
```

This creates a shortcut in `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup` pointing to `watchdog.py`.

To remove autostart, delete the shortcut from the Startup folder.

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'PyAudio'`

See the [PyAudio on Windows](#pyaudio-on-windows) section above.

### `KeyError: GEMINI_API_KEY` / AI not responding

Ensure `.env` exists and contains a valid `GEMINI_API_KEY`. The `.env.example` file is a template — it does not take effect until renamed/copied to `.env`.

### Overlay doesn't appear

Check that PyQt6 is installed correctly:
```powershell
python -c "from PyQt6.QtWidgets import QApplication"
```

On some machines, Microsoft Visual C++ Redistributable is required. Download from [Microsoft](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist).

### Voice input not working

1. Check your microphone is set as the default recording device in Windows Sound settings.
2. Ensure `sounddevice` and `faster-whisper` are installed.
3. Run `python -c "import sounddevice; print(sounddevice.query_devices())"` to list devices.

### `playwright` errors on browser automation

```powershell
playwright install chromium
playwright install-deps
```

### Port 5000 already in use

Change the port in `run_overlay.py` and `app.py` by setting `PORT = 5001` (or any free port) at the top of both files.

### Slow Whisper transcription

Switch to a smaller model in `.env`:
```dotenv
WHISPER_MODEL=tiny.en
WHISPER_DEVICE=cpu
```

### Import errors for `pycaw` or `pywin32`

These are Windows-only packages. Ensure you are running on Windows:
```powershell
pip install pywin32 pycaw comtypes
python Scripts/pywin32_postinstall.py -install
```
