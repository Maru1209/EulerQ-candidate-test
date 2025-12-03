from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import sqlite3
from datetime import datetime

app = FastAPI(title="EulerQ Candidate Test")
templates = Jinja2Templates(directory="templates")

DB = "submissions.db"

def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_name TEXT NOT NULL,
        part TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)
    conn.commit()
    conn.close()

init_db()

def save_submission(candidate_name: str, part: str, content: str):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO submissions(candidate_name, part, content, created_at) VALUES (?, ?, ?, ?)",
        (candidate_name.strip(), part, content, datetime.now().isoformat(timespec="seconds"))
    )
    conn.commit()
    conn.close()

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/start")
def start(candidate_name: str = Form(...)):
    resp = RedirectResponse(url="/test", status_code=303)
    # simple cookie-based candidate selection (not secure; ok for interview room)
    resp.set_cookie("candidate_name", candidate_name.strip(), httponly=False)
    return resp

@app.get("/test", response_class=HTMLResponse)
def test_landing(request: Request):
    cand = request.cookies.get("candidate_name", "").strip()
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "candidate_name": cand, "started": True}
    )

@app.get("/part/{part_id}", response_class=HTMLResponse)
def render_part(part_id: str, request: Request):
    cand = request.cookies.get("candidate_name", "").strip()
    if not cand:
        return RedirectResponse(url="/", status_code=303)

    mapping = {
        "a": "part_a.html",
        "b": "part_b.html",
        "c": "part_c.html",
        "d": "part_d.html",
    }
    tpl = mapping.get(part_id.lower())
    if not tpl:
        return RedirectResponse(url="/test", status_code=303)

    return templates.TemplateResponse(tpl, {"request": request, "candidate_name": cand})

@app.post("/submit/{part_id}", response_class=HTMLResponse)
def submit_part(part_id: str, request: Request, content: str = Form(...)):
    cand = request.cookies.get("candidate_name", "").strip()
    if not cand:
        return RedirectResponse(url="/", status_code=303)

    part_id = part_id.lower()
    if part_id not in ["a", "b", "c", "d"]:
        return RedirectResponse(url="/test", status_code=303)

    save_submission(cand, part_id.upper(), content)
    return templates.TemplateResponse(
        "submitted.html",
        {"request": request, "candidate_name": cand, "part": part_id.upper()}
    )
