# EulerQ Candidate Test (Click-to-Answer Web App)

## What this does
- Home page with buttons for Part A/B/C/D
- Each part opens its own page with questions + a large answer box
- Autosaves drafts in the browser (localStorage)
- On Submit, stores responses on the server in SQLite (`submissions.db`)

## Run locally
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

Open: http://127.0.0.1:8000

## Review submissions
A SQLite DB file `submissions.db` will appear in the project folder.

### Quick query
```sql
SELECT candidate_name, part, created_at, length(content)
FROM submissions
ORDER BY created_at DESC;
```

(Use DB Browser for SQLite or sqlite3 CLI)
