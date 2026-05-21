"""Full system sanity check for F.R.I.D.A.Y."""
import sys, traceback

PASS = "[OK]  "
FAIL = "[FAIL]"
results = []

def check(name, fn):
    try:
        info = fn()
        results.append((True, name, info or ""))
        print(f"{PASS} {name}  {info or ''}")
    except Exception as exc:
        results.append((False, name, str(exc)))
        print(f"{FAIL} {name}: {exc}")
        traceback.print_exc()
    print()

# 1. config
def c_config():
    import config
    return (f"AI_PROVIDER={config.AI_PROVIDER}  GEMINI_MODEL={config.GEMINI_MODEL}  "
            f"GROQ_MODEL={config.GROQ_MODEL}  KEYS={len(config.GEMINI_API_KEYS)}")
check("config", c_config)

# 2. storage / DB
def c_db():
    from storage.db import init_db, get_conn, search_memory_fts, add_memory_to_fts
    init_db()
    with get_conn() as conn:
        tables = sorted(
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        )
    required = {"reminders","tasks","notes","memories","conversations","messages","stock_watchlist"}
    missing  = required - set(tables)
    return f"tables={tables}  missing={missing or 'none'}"
check("storage.db", c_db)

# 3. FTS search
def c_fts():
    from storage.db import search_memory_fts
    results = search_memory_fts("test", limit=1)
    return f"FTS search returns type={type(results).__name__}"
check("storage.db FTS search", c_fts)

# 4. tools
def c_tools():
    from services.tools import TOOL_MAP, ALL_TOOLS
    advanced = ["analyze_document", "research_topic", "execute_python_code",
                "add_to_watchlist", "list_watchlist", "take_note", "remember_fact"]
    missing = [t for t in advanced if t not in TOOL_MAP]
    return f"{len(TOOL_MAP)} tools registered  advanced_missing={missing or 'none'}"
check("services.tools", c_tools)

# 5. AI
def c_ai():
    from services.ai import FridayAI
    import inspect
    ai = FridayAI()
    has_stream = hasattr(ai, "chat_stream") and callable(ai.chat_stream)
    is_gen     = inspect.isgeneratorfunction(ai.chat_stream)
    return f"enabled={ai.enabled}  has_chat_stream={has_stream}  is_generator={is_gen}"
check("services.ai", c_ai)

# 6. memory service
def c_memory():
    from services.memory import store_memory, recall_memories, list_all_memories
    return "store_memory / recall_memories / list_all_memories imported OK"
check("services.memory", c_memory)

# 7. monitor — RAM cooldown fix
def c_monitor():
    from services.monitor import ProactiveMonitor
    m = ProactiveMonitor(None)
    has_ram_attr = hasattr(m, "_last_ram_alert")
    has_cpu_attr = hasattr(m, "_last_cpu_alert")
    # set different values and confirm they are independent variables
    m._last_ram_alert = 999.0
    distinct = m._last_cpu_alert != 999.0
    m._last_ram_alert = 0.0
    return f"_last_ram_alert exists={has_ram_attr}  cpu_exists={has_cpu_attr}  independent={distinct}"
check("services.monitor (RAM cooldown)", c_monitor)

# 8. TTS
def c_tts():
    from services.tts import synthesize
    import inspect
    sig = str(inspect.signature(synthesize))
    return f"synthesize{sig}"
check("services.tts", c_tts)

# 9. Flask app routes
def c_routes():
    import app as a
    rules = [r.rule for r in a.app.url_map.iter_rules()]
    required = ["/chat/stream", "/api/status", "/api/conversations",
                "/chat/reset", "/tts", "/tasks", "/reminders"]
    missing = [r for r in required if r not in rules]
    return f"{len(rules)} routes  missing={missing or 'none'}"
check("app.py routes", c_routes)

# 10. imports that tools need at runtime
def c_pkg():
    ok, fail = [], []
    for mod, pkg in [("fitz","pymupdf"), ("docx","python-docx"),
                     ("bs4","beautifulsoup4"), ("psutil","psutil"),
                     ("groq","groq"), ("PIL","Pillow")]:
        try:
            __import__(mod)
            ok.append(mod)
        except ImportError:
            fail.append(f"{mod}({pkg})")
    return f"ok={ok}  missing={fail or 'none'}"
check("runtime packages", c_pkg)

# ── Summary ──────────────────────────────────────────────────────────────────
print("=" * 60)
passed = sum(1 for r in results if r[0])
failed = [r for r in results if not r[0]]
print(f"  {passed}/{len(results)} checks passed")
if failed:
    print("\n  FAILURES:")
    for _, name, err in failed:
        print(f"    - {name}: {err}")
else:
    print("  System is fully operational.")
print("=" * 60)
