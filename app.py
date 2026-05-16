"""
F.R.I.D.A.Y. — Female Replacement Intelligent Digital Assistant Youth
Gemini Edition — Flask application entry point.
"""

import datetime
import json
import logging
import random
import re

from flask import Flask, Response, jsonify, render_template, request, send_file, stream_with_context

import config
from services.ai import FridayAI
from services.tts import synthesize
from storage import init_db, get_conn

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(name)s: %(message)s',
)

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# ── Bootstrap ───────────────────────────────────────────────────────────
init_db()
ai = FridayAI(api_key=config.GEMINI_API_KEY, model_name=config.GEMINI_MODEL)

_FALLBACKS = [
    "My Gemini uplink is unavailable right now, Sir. "
    "I can still handle time, weather, system info, reminders, tasks, and app commands.",
    "Running in local mode — AI services are offline. Basic commands remain fully operational, Sir.",
    "AI uplink is down at the moment. Try asking me to open apps, check battery, "
    "set a reminder, or search the web, Sir.",
]


# ── Local fast-path handler ──────────────────────────────────────────
def local_fallback(text: str):
    """Instant responses for simple queries without an AI round-trip."""
    tl = text.lower().strip()

    if re.search(r'^(hi|hello|hey|howdy|greetings|good morning|good afternoon|good evening|sup)\b', tl):
        h = datetime.datetime.now().hour
        g = "Good morning" if h < 12 else "Good afternoon" if h < 17 else "Good evening"
        return f"{g}, Sir. All systems are nominal. What can I do for you?"

    if re.search(r'\b(who are you|what are you|introduce yourself|your name|what.s your name)\b', tl):
        return (
            "I'm F.R.I.D.A.Y. — Female Replacement Intelligent Digital Assistant Youth. "
            "Your personal AI, Sir. Always at your service."
        )

    if re.match(r'^(help|what can you do|capabilities|commands)\b', tl):
        return (
            "I can check the time, weather, and system stats; open apps; search the web; "
            "get directions; manage your tasks and reminders; and hold a full conversation, Sir. Just ask."
        )

    if re.search(r'\b(joke|make me laugh|funny)\b', tl):
        jokes = [
            "Why don't scientists trust atoms? Because they make up everything. "
            "Unlike me — I only work with verified data, Sir.",
            "I would tell you a construction joke, Sir, but I'm still working on it.",
            "Why did the AI go to therapy? Too many unresolved exceptions.",
            "Parallel processing, Sir. I can hold multiple conversations "
            "and still find yours the least interesting.",
            "I tried to write a time-travel joke. But you didn't like it.",
        ]
        return random.choice(jokes)

    if re.search(r'\b(clear|reset|forget|new conversation|clear chat|clear history)\b', tl):
        ai.reset()
        return "Conversation history cleared. Starting fresh, Sir."

    if re.search(r'\b(bye|goodbye|goodnight|see you|farewell|standby)\b', tl):
        return "Understood, Sir. Going into standby. Call me whenever you need me."

    return None


# ── Routes ───────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html', gemini_active=ai.enabled)


@app.route('/chat/stream', methods=['POST'])
def chat_stream():
    data = request.get_json(silent=True) or {}
    user_message = str(data.get('message', '')).strip()[:1200]
    if not user_message:
        return jsonify({'error': 'No message provided'}), 400

    quick_reply = local_fallback(user_message)

    def generate():
        if quick_reply:
            yield f"data: {json.dumps({'text': quick_reply, 'done': False})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
            return

        got_any = False
        try:
            for chunk in ai.chat_stream(user_message):
                got_any = True
                yield f"data: {json.dumps({'text': chunk, 'done': False})}\n\n"
        except Exception:
            pass

        if not got_any:
            fallback = ai.chat(user_message) or random.choice(_FALLBACKS)
            yield f"data: {json.dumps({'text': fallback, 'done': False})}\n\n"

        yield f"data: {json.dumps({'done': True})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        },
    )


@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json(silent=True) or {}
    user_message = str(data.get('message', '')).strip()[:1200]
    if not user_message:
        return jsonify({'error': 'No message provided'}), 400

    response = local_fallback(user_message)
    if response is None:
        response = ai.chat(user_message)
    if not response:
        response = random.choice(_FALLBACKS)

    return jsonify({'response': response, 'user': user_message})


@app.route('/listen', methods=['POST'])
def listen():
    try:
        import speech_recognition as sr
    except ImportError:
        return jsonify({'error': 'speech_recognition not installed', 'text': ''})

    r = sr.Recognizer()
    r.dynamic_energy_threshold = True
    try:
        with sr.Microphone() as source:
            r.adjust_for_ambient_noise(source, duration=0.4)
            audio = r.listen(source, timeout=8, phrase_time_limit=12)
        text = r.recognize_google(audio)
        return jsonify({'text': text})
    except sr.WaitTimeoutError:
        return jsonify({'error': 'timeout', 'text': ''})
    except sr.UnknownValueError:
        return jsonify({'error': 'unclear', 'text': ''})
    except Exception as exc:
        logging.error('Listen error: %s', exc)
        return jsonify({'error': 'microphone error', 'text': ''})


@app.route('/chat/reset', methods=['POST'])
def chat_reset():
    ai.reset()
    return jsonify({'status': 'ok'})


@app.route('/tts', methods=['POST'])
def tts():
    data = request.get_json(silent=True) or {}
    text = str(data.get('text', '')).strip()[:700]
    tone = str(data.get('tone', 'auto'))
    if not text:
        return jsonify({'error': 'No text provided'}), 400
    try:
        audio = synthesize(text, tone)
        return send_file(audio, mimetype='audio/mpeg')
    except Exception as exc:
        logging.error('TTS error: %s', exc)
        return jsonify({'error': 'TTS generation failed'}), 500


@app.route('/status')
def status():
    return jsonify({
        'status':  'online',
        'gemini':  ai.enabled,
        'model':   config.GEMINI_MODEL if ai.enabled else None,
    })


@app.route('/tasks', methods=['GET'])
def get_tasks():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, text, priority, created_at FROM tasks WHERE done=0 "
            "ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END, id"
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/tasks', methods=['POST'])
def create_task():
    data     = request.get_json(silent=True) or {}
    text     = str(data.get('text', '')).strip()
    priority = str(data.get('priority', 'normal')).lower()
    if priority not in ('low', 'normal', 'high'):
        priority = 'normal'
    if not text:
        return jsonify({'error': 'No text provided'}), 400
    with get_conn() as conn:
        conn.execute("INSERT INTO tasks (text, priority) VALUES (?, ?)", (text, priority))
        conn.commit()
    return jsonify({'status': 'ok'}), 201


@app.route('/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE tasks SET done=1 WHERE id=?", (task_id,))
        conn.commit()
    return jsonify({'status': 'ok'})


@app.route('/reminders', methods=['GET'])
def get_reminders():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, text, due_time, created_at FROM reminders WHERE done=0 ORDER BY id DESC"
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/reminders', methods=['POST'])
def create_reminder():
    data     = request.get_json(silent=True) or {}
    text     = str(data.get('text', '')).strip()
    due_time = str(data.get('due_time', '')).strip() or None
    if not text:
        return jsonify({'error': 'No text provided'}), 400
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO reminders (text, due_time) VALUES (?, ?)",
            (text, due_time),
        )
        conn.commit()
    return jsonify({'status': 'ok'}), 201


@app.route('/reminders/<int:rem_id>', methods=['DELETE'])
def delete_reminder(rem_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE reminders SET done=1 WHERE id=?", (rem_id,))
        conn.commit()
    return jsonify({'status': 'ok'})


# ── Entry ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("\n" + "=" * 58)
    print("  F.R.I.D.A.Y. — AI Assistant  (Gemini Edition)")
    gemini_status = f"ACTIVE — {config.GEMINI_MODEL}" if ai.enabled else "OFFLINE — add GEMINI_API_KEY to .env"
    print(f"  Gemini: {gemini_status}")
    print("=" * 58)
    print("  http://127.0.0.1:5000")
    print("  Ctrl+C to shut down")
    print("=" * 58 + "\n")
    app.run(debug=False, host='127.0.0.1', port=5000, threaded=True)
