# Security Policy — F.R.I.D.A.Y.

---

## Supported Versions

| Version | Supported |
|---|---|
| 2.x (current) | Yes |
| 1.x | No — upgrade to 2.x |

---

## Reporting a Vulnerability

**Do not open a public GitHub Issue for security vulnerabilities.**

Report security issues privately via GitHub's security advisory feature at:
https://github.com/josi1219/F.R.I.D.A.Y/security/advisories/new

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if you have one)

You will receive an acknowledgement within 48 hours and a resolution timeline within 7 days.

---

## Security Model

FRIDAY runs entirely on the **local machine**. It is designed as a personal tool, not a multi-user or internet-facing service.

### Network exposure

- The Flask server binds to `127.0.0.1:5000` by default — **loopback only**.
- It is not accessible from the local network or internet.
- **Do not change the bind address to `0.0.0.0`** without adding authentication. The API can execute shell commands and control the computer.

### API keys

- All API keys are stored in `.env` at the project root.
- `.env` is listed in `.gitignore` and must never be committed to source control.
- Keys are loaded at startup and stored in memory for the lifetime of the process.
- Never log or print API keys. The codebase uses `os.getenv()` only in `config.py`.

### Sensitive tool operations

The following tools require explicit user confirmation before execution, enforced at the AI system prompt level:

| Tool | Risk |
|---|---|
| `delete_file` | Permanent file deletion |
| `restart_computer` | Interrupts all running processes |
| `shutdown_computer` | Interrupts all running processes |
| `kill_process` | May kill unsaved work |

These confirmations are enforced via the system prompt in `services/ai.py`. They are not enforced at the code level — do not rely on them as a security boundary in adversarial contexts.

### Input validation

- User messages are truncated to 1200 characters in all Flask routes.
- TTS text is truncated to 700 characters.
- SQL queries in `storage/db.py` use parameterised statements — no string interpolation.

### Prompt injection

FRIDAY processes arbitrary user input and web/file content and sends it to the AI. A malicious document or webpage could attempt to inject instructions into the AI prompt. Mitigations:

- Tool functions that read external content (`read_file_contents`, `web_search`) return raw text without executing it.
- The system prompt explicitly defines FRIDAY's persona and constraints.
- High-risk operations require explicit confirmation phrases.

Be cautious when asking FRIDAY to read files or pages from untrusted sources.

### Local data

- Conversation history is stored **in memory only** and lost on restart.
- Reminders, tasks, notes, and memories are stored in `friday.db` (SQLite) with no encryption.
- If you store sensitive information via the `add_note` or `add_memory` tools, be aware this is plaintext on disk.

---

## Dependency Security

FRIDAY uses a number of third-party packages. Keep dependencies up to date:

```powershell
pip install --upgrade -r requirements.txt
```

Periodically audit for known vulnerabilities:

```powershell
pip install pip-audit
pip-audit
```

---

## Known Limitations

1. **No authentication on the local HTTP API.** Any process running on the same machine can send requests to `localhost:5000`.
2. **AI function calling is only partially sandboxed.** A sufficiently crafted prompt could instruct the AI to perform destructive operations. The confirmation requirements in the system prompt are a defence-in-depth measure, not a hard security boundary.
3. **Clipboard access is unrestricted.** The `read_clipboard` tool reads the clipboard on demand — avoid copying sensitive secrets while FRIDAY is running.
