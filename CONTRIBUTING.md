# Contributing to F.R.I.D.A.Y.

Thank you for your interest in contributing. This document covers the development workflow, coding standards, and submission process.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Coding Standards](#coding-standards)
- [Making Changes](#making-changes)
- [Adding a New Tool](#adding-a-new-tool)
- [Adding a New AI Provider](#adding-a-new-ai-provider)
- [Testing](#testing)
- [Submitting a Pull Request](#submitting-a-pull-request)
- [Reporting Bugs](#reporting-bugs)
- [Requesting Features](#requesting-features)

---

## Code of Conduct

Be respectful. Focus on constructive, technical discussion. Harassment or personal attacks will result in removal.

---

## Getting Started

1. Fork the repository on GitHub.
2. Clone your fork locally.
3. Set up the development environment (see below).
4. Create a branch for your change.
5. Make your changes.
6. Submit a pull request.

---

## Development Setup

```powershell
git clone https://github.com/your-fork/F.R.I.D.A.Y.git
cd friday
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
copy .env.example .env
# Edit .env and add GEMINI_API_KEY
```

For development, set `FLASK_DEBUG=1` in `.env` to enable Flask's auto-reloader (web UI only — does not apply to the overlay/engine).

---

## Project Structure

```
Friday/
├── app.py           # Flask web layer — add routes here
├── config.py        # Add new config constants here
├── engine.py        # Voice pipeline — modify the state machine here
├── services/
│   ├── ai.py        # AI provider logic — modify for new providers
│   ├── tools.py     # AI-callable tools — add new tools here
│   └── tts.py       # TTS logic
├── voice/           # Microphone input and audio playback
├── overlay/         # PyQt6 overlay UI
├── vision/          # Screen capture and analysis
├── automation/      # Browser and input automation
├── storage/         # SQLite persistence
└── docs/            # Documentation
```

---

## Coding Standards

### Style

- Follow **PEP 8**.
- Maximum line length: **100 characters**.
- Use **4-space indentation** (no tabs).
- Use `f-strings` for string formatting.
- Type-annotate all function signatures.

### Imports

Group imports in this order (one blank line between groups):
1. Standard library
2. Third-party packages
3. Local modules

```python
import os
import threading

import flask

import config
from services.ai import FridayAI
```

### Docstrings

Use one-line docstrings for simple functions. For complex functions, use multi-line:

```python
def synthesize(text: str, tone: str = "auto") -> io.BytesIO:
    """
    Generate TTS audio for the given text.

    Args:
        text: The text to synthesize. Max 700 characters.
        tone: Prosody mode. 'auto' detects from content.

    Returns:
        BytesIO buffer of MP3 audio data, seeked to position 0.
    """
```

### Error handling

- Use specific exception types, not bare `except:`.
- Log errors with `logger.error("msg: %s", exc)` — do not use f-strings in log calls.
- Handle missing optional dependencies with `try/except ImportError` at module level and set `HAS_X = False` flags.

### Logging

Every module should use its own named logger:

```python
import logging
logger = logging.getLogger(__name__)
```

Use appropriate levels: `DEBUG` for verbose trace, `INFO` for normal events, `WARNING` for degraded functionality, `ERROR` for failures.

---

## Making Changes

### Branch naming

| Type | Format | Example |
|---|---|---|
| Feature | `feat/short-description` | `feat/add-spotify-tool` |
| Bug fix | `fix/short-description` | `fix/whisper-timeout` |
| Documentation | `docs/short-description` | `docs/update-api-ref` |
| Refactor | `refactor/short-description` | `refactor/ai-provider` |

### Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(tools): add spotify playback control
fix(tts): handle empty text input gracefully
docs(api): add streaming example to API reference
refactor(ai): extract key rotation into helper method
```

---

## Adding a New Tool

Tools are functions in `services/tools.py` that the AI can call via function calling.

### Requirements

1. **Type-annotated parameters** — the SDK uses these to generate the JSON schema.
2. **Docstring** — becomes the tool's description shown to the model. Be precise.
3. **Returns a string** — the result fed back to the model.
4. **No module-level side effects** — use lazy imports inside the function.
5. **Handle failures gracefully** — return an error string, don't raise exceptions.

### Example

```python
def get_clipboard_text() -> str:
    """Return the current text content of the system clipboard."""
    try:
        import pyperclip
        text = pyperclip.paste()
        return f"Clipboard contains: {text!r}" if text else "Clipboard is empty."
    except Exception as exc:
        return f"Could not read clipboard: {exc}"
```

### Register the tool

Add the function to the tools list in `services/ai.py` where tools are collected:

```python
from services.tools import get_clipboard_text
# It is collected automatically if you follow the module-level function convention.
```

The SDK auto-discovers all callables passed to `tools=`. No separate registration file needed.

### Update documentation

Add the new tool to the [Tool categories](MODULES.md#servicestoolspy) table in `docs/MODULES.md`.

---

## Adding a New AI Provider

1. Add configuration constants to `config.py`:
   ```python
   NEW_API_KEY = os.getenv("NEW_API_KEY", "")
   NEW_MODEL   = os.getenv("NEW_MODEL", "default-model")
   ```

2. Add the provider case to `FridayAI.__init__()` in `services/ai.py`:
   ```python
   elif config.AI_PROVIDER == "new":
       self._init_new_provider()
   ```

3. Implement `_chat_new()` and `_chat_stream_new()` methods following the same interface as the Gemini/Groq implementations.

4. Add to `CONFIGURATION.md`.

---

## Testing

There is no automated test suite yet. Before submitting a PR, manually verify:

- [ ] `python -c "import app"` runs without errors.
- [ ] `python app.py` starts Flask and the `/status` endpoint returns 200.
- [ ] Chat responses work via `/chat` and `/chat/stream`.
- [ ] TTS endpoint returns audio.
- [ ] If you modified tools, test the specific tools via the chat interface.
- [ ] If you modified the voice pipeline, run `python run_overlay.py` and test the hotkey.

---

## Submitting a Pull Request

1. Push your branch to your fork.
2. Open a PR against `main` on [josi1219/F.R.I.D.A.Y](https://github.com/josi1219/F.R.I.D.A.Y).
3. Fill in the PR template:
   - What does this change do?
   - How was it tested?
   - Any breaking changes?
4. Link any related issues.
5. A maintainer will review within a few days.

### PR checklist

- [ ] Code follows the style guidelines
- [ ] All new functions have docstrings and type annotations
- [ ] New configuration options are documented in `CONFIGURATION.md`
- [ ] New tools are documented in `MODULES.md`
- [ ] No API keys or secrets in committed files

---

## Reporting Bugs

Open a GitHub Issue with:

- **OS version** and **Python version**
- **Steps to reproduce** — exact commands run
- **Expected behaviour**
- **Actual behaviour**
- **Relevant log output** (from console or `friday_watchdog.log`)

Redact any API keys before pasting logs.

---

## Requesting Features

Open a GitHub Issue labelled `enhancement` with:

- What you want FRIDAY to be able to do
- Why it would be useful
- Any implementation ideas you have
