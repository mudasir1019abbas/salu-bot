"""Simple, fast RAG for SALUBOT.
1) build_knowledge(pdf) -> knowledge/prospectus.md  (clean Markdown, one section per page)
2) Optional: build_important(client) -> knowledge/important.md (AI-made key facts for fast replies)
3) search(query) -> best matching chunks (BM25, no vector DB needed)
"""
import os, re, json
from rank_bm25 import BM25Okapi

KB_DIR = os.path.join(os.path.dirname(__file__), "knowledge")
FULL_MD = os.path.join(KB_DIR, "prospectus.md")
IMPORTANT_MD = os.path.join(KB_DIR, "important.md")
os.makedirs(KB_DIR, exist_ok=True)

STOP = set("a an the of to in for and or is are was be on at by with from as it this that what which who how when where do does i me my you your can".split())

def tokenize(t):
    return [w for w in re.findall(r"[a-z0-9]+", t.lower()) if w not in STOP]

def _clean(text):
    lines = [re.sub(r"[ \t]{3,}", " | ", l.strip()) for l in text.splitlines()]
    out, blank = [], False
    for l in lines:
        if not l:
            if not blank: out.append("")
            blank = True
        else:
            out.append(l); blank = False
    return "\n".join(out).strip()

def build_knowledge(pdf_path, title="University Prospectus"):
    from pypdf import PdfReader
    reader = PdfReader(pdf_path)
    parts = [f"# {title}\n"]
    for i, page in enumerate(reader.pages, 1):
        txt = _clean(page.extract_text(extraction_mode="layout") or "")
        if len(txt) > 30:
            parts.append(f"\n## Page {i}\n\n{txt}\n")
    with open(FULL_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    INDEX.reload()
    return {"pages": len(reader.pages), "chunks": len(INDEX.chunks)}

def _chunks_from_md(path, source):
    if not os.path.exists(path): return []
    text = open(path, encoding="utf-8").read()
    chunks = []
    for sec in re.split(r"\n(?=## )", text):
        head = sec.split("\n", 1)[0].lstrip("# ").strip()
        body = sec.strip()
        # split long sections into ~1200 char windows with overlap
        step, size = 1000, 1200
        for s in range(0, max(len(body), 1), step):
            piece = body[s:s + size]
            if len(piece) > 40:
                chunks.append({"source": source, "section": head, "text": piece})
    return chunks

class Index:
    def __init__(self): self.reload()
    def reload(self):
        # important.md first: its short facts give the fastest, cleanest answers
        self.chunks = _chunks_from_md(IMPORTANT_MD, "important.md") + _chunks_from_md(FULL_MD, "prospectus.md")
        self.bm25 = BM25Okapi([tokenize(c["text"]) for c in self.chunks]) if self.chunks else None
    def search(self, query, k=6):
        if not self.bm25: return []
        q = tokenize(query)
        if not q: return []
        scores = self.bm25.get_scores(q)
        best = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        return [dict(self.chunks[i], score=float(scores[i])) for i in best if scores[i] > 0]

INDEX = Index()

TOPICS = ["admission procedure eligibility criteria", "fee structure tuition charges", "programs offered departments faculties",
          "merit list entry test", "hostel accommodation transport", "scholarships financial aid", "examination grading GPA rules",
          "important dates deadlines", "campuses contact address phone", "attendance discipline rules", "seats quota reserved",
          "documents required migration", "library facilities", "semester system credit hours"]

def build_important(client, model):
    """Ask Gemini to distil the most important facts into a short Markdown file."""
    if not os.path.exists(FULL_MD):
        raise RuntimeError("Build the knowledge file from the PDF first.")
    sections = []
    for t in TOPICS:
        ctx = "\n---\n".join(f"[{c['section']}]\n{c['text']}" for c in INDEX.search(t, k=5) if c["source"] == "prospectus.md")
        if not ctx: continue
        prompt = (f"Topic: {t}\n\nFrom the prospectus extracts below, write the important facts for this topic as a short "
                  "Markdown section: a '## ' heading, then concise bullet points with exact numbers, dates, fees and names. "
                  "Add the page reference like (Page 12). Only use facts in the text. If nothing relevant, reply SKIP.\n\n" + ctx)
        r = client.models.generate_content(model=model, contents=prompt)
        txt = (r.text or "").strip()
        if txt and "SKIP" not in txt[:10]:
            sections.append(txt)
    with open(IMPORTANT_MD, "w", encoding="utf-8") as f:
        f.write("# Important Facts (quick answers)\n\n" + "\n\n".join(sections))
    INDEX.reload()
    return {"sections": len(sections)}

def status():
    def info(p): return {"exists": os.path.exists(p), "size_kb": round(os.path.getsize(p)/1024, 1) if os.path.exists(p) else 0}
    return {"prospectus": info(FULL_MD), "important": info(IMPORTANT_MD), "chunks": len(INDEX.chunks)}
