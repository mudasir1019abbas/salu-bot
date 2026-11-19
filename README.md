# SALUBOT — University AI Campus Assistant (Flask + Gemini)

## Setup
```bash
python -m venv venv
# Windows: venv\Scripts\activate    macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # Windows: copy .env.example .env
# put your key from https://aistudio.google.com/apikey into .env
python app.py
```
Open http://127.0.0.1:5000

Create an account from the sign-in page to access your dashboard and campus assistant. Accounts and password hashes are stored in `instance/unibot.sqlite3`; chat history stays in the browser and is separated by account. Set `FLASK_SECRET_KEY` to a long random value before deploying. When serving over HTTPS, set `SESSION_COOKIE_SECURE=true`.


## Prospectus answers (RAG)
SALUBOT answers university questions from the prospectus.
- `knowledge/prospectus.md` is already built from the SALU Prospectus 2027 (206 pages).
- Click the 📖 book button in the top bar to upload a new PDF and rebuild it.
- Click **Create important.md** to make a short key-facts file (fees, admissions, dates). It is searched first, so replies are faster and cleaner.
- Each reply shows the pages it used. Search runs locally (BM25), so no extra API cost.
- Command line: `python -c "import rag; rag.build_knowledge('file.pdf')"`
