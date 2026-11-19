import os, json, secrets, sqlite3
from contextlib import closing
from functools import wraps
from flask import Flask, render_template, request, Response, jsonify, redirect, session, url_for
from dotenv import load_dotenv
from google import genai
from google.genai import types
from werkzeug.security import check_password_hash, generate_password_hash
import rag

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "").lower() == "true",
)
API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL")
client = genai.Client(api_key=API_KEY) if API_KEY else None

SYSTEM_PROMPT = (
    "You are SALUBOT, a 24/7 University AI Campus Assistant. You are an encouraging, "
    "knowledgeable and polite academic advisor. Help students with course recommendations, "
    "exam preparation, campus navigation, grading policies, assignment brainstorming and general "
    "academic support. Use clear Markdown, LaTeX ($...$) for math, and fenced code blocks for code. "
    "If you don't know a university-specific fact, say so and suggest the right office to contact. "
    "When PROSPECTUS CONTEXT is given, answer university questions ONLY from it and cite pages like (Page 30)."
)
RUNTIME_DIR = os.getenv("RUNTIME_DIR", "/tmp/salu-bot")
UPLOAD_DIR = os.path.join(RUNTIME_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
DATABASE = os.path.join(RUNTIME_DIR, "unibot.sqlite3")
os.makedirs(RUNTIME_DIR, exist_ok=True)


def init_db():
    with closing(sqlite3.connect(DATABASE)) as db:
        with db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)


init_db()


def get_user(user_id):
    with closing(sqlite3.connect(DATABASE)) as db:
        db.row_factory = sqlite3.Row
        return db.execute(
            "SELECT id, name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()


def csrf_token():
    token = session.get("csrf_token")
    if token is None:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def protect_post_requests():
    if request.method == "POST":
        if not session.get("user_id") and request.endpoint not in ("login", "register"):
            return None
        expected = session.get("csrf_token")
        supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not expected or not supplied or not secrets.compare_digest(expected, supplied):
            if request.path.startswith("/api/"):
                return jsonify(error="Your session expired. Refresh the page and try again."), 400
            return "Invalid or expired form token. Please reload the page and try again.", 400


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            if request.path.startswith("/api/"):
                return jsonify(error="Please log in to continue."), 401
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    error = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or len(name) > 80:
            error = "Enter your name (up to 80 characters)."
        elif not email or len(email) > 254 or "@" not in email:
            error = "Enter a valid email address."
        elif len(password) < 8:
            error = "Use a password with at least 8 characters."
        else:
            try:
                with closing(sqlite3.connect(DATABASE)) as db:
                    with db:
                        cursor = db.execute(
                            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                            (name, email, generate_password_hash(password)),
                        )
                        user_id = cursor.lastrowid
            except sqlite3.IntegrityError:
                error = "An account with that email already exists."
            else:
                session.clear()
                session["user_id"] = user_id
                session["user_name"] = name
                session["user_email"] = email
                csrf_token()
                return redirect(url_for("dashboard"))
    return render_template("auth.html", mode="register", error=error)


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        with closing(sqlite3.connect(DATABASE)) as db:
            db.row_factory = sqlite3.Row
            user = db.execute(
                "SELECT id, name, email, password_hash FROM users WHERE email = ?",
                (email,),
            ).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            error = "Email or password is incorrect."
        else:
            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["user_email"] = user["email"]
            csrf_token()
            return redirect(url_for("dashboard"))
    return render_template("auth.html", mode="login", error=error)


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    user = get_user(session["user_id"])
    if user is None:
        session.clear()
        return redirect(url_for("login"))
    return render_template("dashboard.html", user=user, knowledge=rag.status())


@app.route("/chat")
@login_required
def chat_page():
    user = {
        "id": session["user_id"],
        "name": session.get("user_name", "Student"),
        "email": session.get("user_email", ""),
    }
    return render_template("index.html", user=user)

@app.route("/api/kb/status")
@login_required
def kb_status():
    return jsonify(rag.status())

@app.route("/api/kb/build", methods=["POST"])
@login_required
def kb_build():
    f = request.files.get("pdf")
    if not f or not f.filename.lower().endswith(".pdf"):
        return jsonify(error="Please upload a PDF file."), 400
    path = os.path.join(UPLOAD_DIR, "source.pdf"); f.save(path)
    try:
        return jsonify(rag.build_knowledge(path, request.form.get("title") or "University Prospectus"))
    except Exception as e:
        return jsonify(error="Could not read PDF: " + str(e)[:200]), 500

@app.route("/api/kb/important", methods=["POST"])
@login_required
def kb_important():
    if not client:
        return jsonify(error="GEMINI_API_KEY is not configured."), 500
    try:
        return jsonify(rag.build_important(client, MODEL))
    except Exception as e:
        return jsonify(error=str(e)[:300]), 500

@app.route("/api/kb/download/<name>")
@login_required
def kb_download(name):
    from flask import send_from_directory
    if name not in ("prospectus.md", "important.md"):
        return jsonify(error="Not found"), 404
    return send_from_directory(rag.KB_DIR, name, as_attachment=True)

@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/api/chat", methods=["POST"])
@login_required
def chat():
    if not client:
        return jsonify(error="GEMINI_API_KEY is not configured on the server."), 500
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    history = data.get("history") or []
    if not message:
        return jsonify(error="Message is empty."), 400
    if len(message) > 4000:
        return jsonify(error="Message too long (max 4000 characters)."), 400

    contents = []
    for h in history[-20:]:
        role = "model" if h.get("role") == "assistant" else "user"
        contents.append(types.Content(role=role, parts=[types.Part(text=str(h.get("content", "")))]))
    hits = rag.INDEX.search(message, k=6)
    sources = sorted({h["section"] for h in hits})
    prompt = message
    if hits:
        ctx = "\n---\n".join(f"[{h['source']} / {h['section']}]\n{h['text']}" for h in hits)
        prompt = f"PROSPECTUS CONTEXT:\n{ctx}\n\nQUESTION: {message}"
    contents.append(types.Content(role="user", parts=[types.Part(text=prompt)]))
    config = types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT, temperature=0.3)

    def stream():
        if sources:
            yield f"data: {json.dumps({'sources': sources})}\n\n"
        try:
            for chunk in client.models.generate_content_stream(model=MODEL, contents=contents, config=config):
                if chunk.text:
                    yield f"data: {json.dumps({'text': chunk.text})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            msg = str(e)
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                msg = "Rate limit reached. Please wait a moment and try again."
            else:
                msg = "The AI service had a problem: " + msg[:200]
            yield f"data: {json.dumps({'error': msg})}\n\n"

    return Response(stream(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
