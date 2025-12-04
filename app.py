import os
import sqlite3
from datetime import datetime
from typing import Optional, Tuple

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

# -----------------------------
# Config
# -----------------------------
APP_TITLE = "EulerQ Candidate Test"
DB = os.getenv("DB_PATH", "submissions.db")
ADMIN_KEY = os.getenv("ADMIN_KEY", "EULERQ123")  # set in Railway Variables for security
COOKIE_NAME = "candidate_name"

templates = Jinja2Templates(directory="templates")
app = FastAPI(title=APP_TITLE)

# -----------------------------
# DB helpers
# -----------------------------
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

    cur.execute("""
    CREATE TABLE IF NOT EXISTS final_submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_name TEXT NOT NULL UNIQUE,
        finalized_at TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def get_candidate(request: Request) -> str:
    return (request.cookies.get(COOKIE_NAME) or "").strip()


def save_submission(candidate: str, part: str, content: str):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO submissions(candidate_name, part, content, created_at) VALUES (?, ?, ?, ?)",
        (candidate.strip(), part.strip(), content, now_iso()),
    )
    conn.commit()
    conn.close()


def get_latest_submission(candidate: str, part: str) -> Tuple[Optional[str], Optional[str]]:
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT content, created_at
        FROM submissions
        WHERE candidate_name=? AND part=?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (candidate.strip(), part.strip()),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None, None
    return row[0], row[1]


def has_submission(candidate: str, part: str) -> bool:
    content, _ = get_latest_submission(candidate, part)
    return bool(content and content.strip())


def is_finalized(candidate: str) -> bool:
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM final_submissions WHERE candidate_name=? LIMIT 1",
        (candidate.strip(),),
    )
    ok = cur.fetchone() is not None
    conn.close()
    return ok


def finalize_candidate(candidate: str):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO final_submissions(candidate_name, finalized_at) VALUES (?, ?)",
        (candidate.strip(), now_iso()),
    )
    conn.commit()
    conn.close()


# -----------------------------
# Startup
# -----------------------------
@app.on_event("startup")
def _startup():
    init_db()


# -----------------------------
# Candidate + Home
# -----------------------------
@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    return RedirectResponse(url="/test", status_code=303)


@app.get("/test", response_class=HTMLResponse)
def test_home(request: Request):
    candidate = get_candidate(request)
    if not candidate:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "candidate_name": "",
                "finalized": False,
            },
        )

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "candidate_name": candidate,
            "finalized": is_finalized(candidate),
        },
    )


@app.post("/set-candidate")
def set_candidate(candidate_name: str = Form(...)):
    candidate_name = (candidate_name or "").strip()
    if not candidate_name:
        return RedirectResponse(url="/test", status_code=303)

    resp = RedirectResponse(url="/test", status_code=303)
    resp.set_cookie(COOKIE_NAME, candidate_name, max_age=60 * 60 * 24 * 14)  # 14 days
    return resp


@app.get("/change-candidate")
def change_candidate():
    resp = RedirectResponse(url="/test", status_code=303)
    resp.delete_cookie(COOKIE_NAME)
    return resp


# -----------------------------
# Parts (A/B/C/D/E)
# -----------------------------
PART_MAP = {
    "a": ("A", "part_a.html"),
    "b": ("B", "part_b.html"),
    "c": ("C", "part_c.html"),
    "d": ("D", "part_d.html"),
    "e": ("E", "part_e.html"),
}


@app.get("/part/{part_id}", response_class=HTMLResponse)
def render_part(part_id: str, request: Request):
    candidate = get_candidate(request)
    if not candidate:
        return RedirectResponse(url="/test", status_code=303)

    part_id = part_id.lower().strip()
    if part_id not in PART_MAP:
        return RedirectResponse(url="/test", status_code=303)

    part_letter, template_name = PART_MAP[part_id]
    existing_content, existing_time = get_latest_submission(candidate, part_letter)
    finalized = is_finalized(candidate)

    return templates.TemplateResponse(
        template_name,
        {
            "request": request,
            "candidate_name": candidate,
            "part": part_letter,
            "existing_content": existing_content or "",
            "existing_time": existing_time,
            "finalized": finalized,
        },
    )


@app.post("/submit/{part_id}", response_class=HTMLResponse)
def submit_part(part_id: str, request: Request, content: str = Form("")):
    candidate = get_candidate(request)
    if not candidate:
        return RedirectResponse(url="/test", status_code=303)

    part_id = part_id.lower().strip()
    if part_id not in PART_MAP:
        return RedirectResponse(url="/test", status_code=303)

    # Block resubmission after finalize
    if is_finalized(candidate):
        return HTMLResponse("Test already finalized. Submissions are locked.", status_code=403)

    part_letter, _template = PART_MAP[part_id]
    save_submission(candidate, part_letter, content or "")

    # Redirect to next part after submit
    next_map = {
        "a": "b",
        "b": "c",
        "c": "d",
        "d": "e",
        "e": "finalize"
    }
    next_step = next_map.get(part_id, "finalize")

    if next_step == "finalize":
        return RedirectResponse(url="/finalize", status_code=303)

    return RedirectResponse(url=f"/part/{next_step}", status_code=303)



# -----------------------------
# Final Submit All
# -----------------------------
@app.get("/finalize", response_class=HTMLResponse)
def finalize_page(request: Request):
    candidate = get_candidate(request)
    if not candidate:
        return RedirectResponse(url="/test", status_code=303)

    status = {
        "A": has_submission(candidate, "A"),
        "B": has_submission(candidate, "B"),
        "C": has_submission(candidate, "C"),
        "D": has_submission(candidate, "D"),
    }
    all_done = all(status.values())
    finalized = is_finalized(candidate)

    return templates.TemplateResponse(
        "finalize.html",
        {
            "request": request,
            "candidate_name": candidate,
            "status": status,
            "all_done": all_done,
            "finalized": finalized,
        },
    )


@app.post("/finalize")
def finalize_submit(request: Request):
    candidate = get_candidate(request)
    if not candidate:
        return RedirectResponse(url="/test", status_code=303)

    if is_finalized(candidate):
        return RedirectResponse(url="/finalize", status_code=303)

    if not all(has_submission(candidate, p) for p in ["A", "B", "C", "D"]):
        return HTMLResponse("Please submit Parts A–D before finalizing.", status_code=400)

    finalize_candidate(candidate)
    return RedirectResponse(url="/finalize", status_code=303)


# -----------------------------
# Admin - view submissions
# -----------------------------
@app.get("/admin/submissions", response_class=HTMLResponse)
def admin_submissions(key: str):
    if key != ADMIN_KEY:
        return HTMLResponse("Unauthorized", status_code=401)

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
        SELECT candidate_name, part, created_at, content
        FROM submissions
        ORDER BY created_at DESC
        LIMIT 200
    """)
    rows = cur.fetchall()
    conn.close()

    html = ["<h2>Submissions</h2>", "<p>Latest 200</p>"]
    for cand, part, created_at, content in rows:
        html.append("<hr/>")
        html.append(f"<b>{cand}</b> — Part <b>{part}</b> — <small>{created_at}</small>")
        html.append(
            "<pre style='white-space:pre-wrap;background:#f3f4f6;padding:12px;border-radius:10px;'>"
            + (content or "")
            + "</pre>"
        )
    return HTMLResponse("".join(html))
