# API Reference — F.R.I.D.A.Y.

The Flask web server exposes a JSON REST API consumed by the browser frontend and available for programmatic use. The server runs on `http://127.0.0.1:5000` by default.

---

## Table of Contents

- [Authentication](#authentication)
- [Endpoints](#endpoints)
  - [GET /](#get-)
  - [GET /status](#get-status)
  - [POST /chat](#post-chat)
  - [POST /chat/stream](#post-chatstream)
  - [POST /chat/reset](#post-chatreset)
  - [POST /tts](#post-tts)
  - [POST /listen](#post-listen)
- [Error Format](#error-format)
- [SSE Streaming Protocol](#sse-streaming-protocol)
- [Example: Full Chat Interaction](#example-full-chat-interaction)

---

## Authentication

No authentication is required. The server binds to `127.0.0.1` (loopback only) so it is not reachable from the network by default.

> **Warning:** Do not expose this server on `0.0.0.0` without adding authentication middleware. The API can control your computer.

---

## Endpoints

### GET /

Serves the web HUD frontend (`templates/index.html`).

**Response:** `text/html`

---

### GET /status

Returns the current AI provider status.

**Response:** `application/json`

```json
{
  "status": "online",
  "gemini": true,
  "model": "gemini-2.0-flash"
}
```

| Field | Type | Description |
|---|---|---|
| `status` | string | Always `"online"` if server is running |
| `gemini` | boolean | Whether the AI backend is enabled and has a valid key |
| `model` | string \| null | Active model name, or `null` if AI is disabled |

---

### POST /chat

Send a message and receive a complete response in one round-trip.

**Request body:** `application/json`

```json
{
  "message": "What time is it?"
}
```

| Field | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `message` | string | Yes | Max 1200 chars | User's message |

**Response:** `application/json` `200 OK`

```json
{
  "response": "It's 3:47 PM, Sir.",
  "user": "What time is it?"
}
```

| Field | Type | Description |
|---|---|---|
| `response` | string | FRIDAY's text response |
| `user` | string | Echo of the sanitised input message |

**Error response:** `400 Bad Request`

```json
{ "error": "No message provided" }
```

---

### POST /chat/stream

Send a message and receive the response as a **Server-Sent Events (SSE)** stream. Tokens are pushed as they are generated, enabling real-time streaming UI.

**Request body:** `application/json`

```json
{
  "message": "Explain quantum entanglement briefly."
}
```

| Field | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `message` | string | Yes | Max 1200 chars | User's message |

**Response:** `text/event-stream` `200 OK`

Each event is a JSON-encoded object on a `data:` line:

```
data: {"text": "Quantum entanglement is", "done": false}

data: {"text": " a phenomenon where two particles", "done": false}

data: {"done": true}
```

See [SSE Streaming Protocol](#sse-streaming-protocol) for details.

**Error response:** `400 Bad Request`

```json
{ "error": "No message provided" }
```

---

### POST /chat/reset

Clears FRIDAY's in-memory conversation history, starting a fresh session.

**Request body:** none required

**Response:** `application/json` `200 OK`

```json
{ "status": "ok" }
```

---

### POST /tts

Synthesize speech for arbitrary text. Returns an MP3 audio file.

**Request body:** `application/json`

```json
{
  "text": "All systems are nominal, Sir.",
  "tone": "auto"
}
```

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `text` | string | Yes | — | Text to synthesize. Max 700 chars |
| `tone` | string | No | `"auto"` | Prosody mode: `auto`, `normal`, `excited`, `urgent`, `calm`, `apologetic`, `warm` |

When `tone` is `"auto"`, the service detects the appropriate tone from the text content.

**Response:** `audio/mpeg` `200 OK`

Binary MP3 audio data.

**Error responses:**

| Code | Body | Reason |
|---|---|---|
| `400` | `{"error": "No text provided"}` | Empty or missing `text` field |
| `500` | `{"error": "TTS generation failed"}` | edge-tts service failure |

---

### POST /listen

Capture a single spoken phrase via the system microphone and return the transcript.

> **Note:** This route uses the browser-side `speech_recognition` library (Google Speech API). The always-on voice pipeline in `run_overlay.py` uses `faster-whisper` instead.

**Request body:** none required

**Response:** `application/json` `200 OK`

```json
{ "text": "open calculator" }
```

**Error responses:**

```json
{ "error": "timeout", "text": "" }
{ "error": "unclear", "text": "" }
{ "error": "microphone error", "text": "" }
{ "error": "speech_recognition not installed", "text": "" }
```

---

## Error Format

All error responses use a consistent JSON envelope:

```json
{
  "error": "Human-readable error message"
}
```

HTTP status codes used:

| Code | Meaning |
|---|---|
| `200` | Success |
| `400` | Bad request — missing or invalid input |
| `500` | Server error — unexpected failure |

---

## SSE Streaming Protocol

`POST /chat/stream` uses the [Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events) protocol.

### Event format

Each chunk is a `data:` line followed by two newlines:

```
data: <json-object>\n\n
```

### Chunk types

**Text chunk** — partial response text:
```json
{"text": "partial text here", "done": false}
```

**Final chunk** — signals end of stream:
```json
{"done": true}
```

### Consuming in JavaScript

```javascript
const response = await fetch('/chat/stream', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ message: userInput }),
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;

  const lines = decoder.decode(value).split('\n');
  for (const line of lines) {
    if (!line.startsWith('data: ')) continue;
    const data = JSON.parse(line.slice(6));
    if (data.done) break;
    appendText(data.text);  // stream to UI
  }
}
```

---

## Example: Full Chat Interaction

### Non-streaming

```bash
curl -X POST http://127.0.0.1:5000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is my battery level?"}'
```

```json
{
  "response": "Battery is at 87%, Sir. Currently charging.",
  "user": "What is my battery level?"
}
```

### Streaming

```bash
curl -N -X POST http://127.0.0.1:5000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Tell me a joke"}'
```

```
data: {"text": "Why don't scientists trust atoms?", "done": false}

data: {"text": " Because they make up everything.", "done": false}

data: {"done": true}
```

### TTS

```bash
curl -X POST http://127.0.0.1:5000/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Good morning, Sir.", "tone": "warm"}' \
  --output greeting.mp3
```

### Status check

```bash
curl http://127.0.0.1:5000/status
```

```json
{"status": "online", "gemini": true, "model": "gemini-2.0-flash"}
```
