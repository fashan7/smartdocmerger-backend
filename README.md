# SmartDocMerger — Backend

> AI-powered document deduplication and synthesis API.  
> Built with FastAPI + PostgreSQL + Claude API.

---

## What it does

SmartDocMerger takes scattered AI-generated documents, extracts every distinct idea, detects duplicates across all docs using TF-IDF + Claude, and helps you merge everything into one clean master document.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI |
| Database | PostgreSQL (Railway) / SQLite (local dev) |
| ORM | SQLAlchemy async |
| Migrations | Alembic |
| AI | Anthropic Claude API |
| Similarity | scikit-learn TF-IDF + cosine |
| File parsing | pdfplumber, python-docx |
| Auth | JWT (python-jose + passlib bcrypt) |
| Deployment | Railway |

---

## Project Structure

```
app/
├── main.py                  # FastAPI app entry point
├── config.py                # Settings (pydantic-settings)
├── database.py              # Async SQLAlchemy engine + session
├── core/
│   ├── deps.py              # get_current_user, require_admin
│   └── security.py          # JWT + password hashing
├── models/
│   ├── user.py
│   ├── document.py
│   ├── idea.py
│   ├── idea_pair.py
│   ├── master_doc.py
│   ├── notification.py
│   └── workspace_settings.py
├── routers/
│   ├── auth.py              # Register, login, me, change password
│   ├── documents.py         # Upload, paste, list, SSE stream
│   ├── ideas.py             # List, get, update, delete
│   ├── diff.py              # Side-by-side idea comparison
│   ├── merge_queue.py       # Merge, keep-both, discard, flag
│   ├── master_doc.py        # Sections, ideas, export .md
│   ├── notifications.py     # List, mark read
│   ├── settings.py          # Workspace settings, API key validation
│   └── admin.py             # User management (admin only)
└── services/
    ├── ai_service.py        # Claude API: extract, verify, merge
    ├── chunker.py           # Split documents into sections
    ├── similarity.py        # TF-IDF cosine similarity
    ├── file_parser.py       # PDF, DOCX, MD, TXT parsing
    └── processor.py         # Full processing pipeline + SSE
tests/
├── conftest.py
├── test_auth.py
├── test_documents.py
├── test_services.py
└── test_admin.py
```

---

## API Endpoints

| Method | Route | Description |
|---|---|---|
| POST | `/auth/register` | Register (dev only) |
| POST | `/auth/login` | Login → JWT token |
| GET | `/auth/me` | Current user |
| POST | `/documents/upload` | Upload file (.pdf .docx .md .txt) |
| POST | `/documents/paste` | Paste raw text |
| GET | `/documents` | List all documents |
| GET | `/documents/:id` | Get doc + extracted ideas |
| DELETE | `/documents/:id` | Delete document |
| POST | `/documents/:id/reprocess` | Re-run AI extraction |
| GET | `/documents/:id/stream` | SSE progress stream |
| GET | `/ideas` | List ideas (filterable) |
| PATCH | `/ideas/:id` | Update idea |
| GET | `/diff/:pair_id` | Get duplicate pair for comparison |
| GET | `/merge-queue` | List pending duplicate pairs |
| POST | `/merge-queue/:id/merge` | Merge two ideas |
| POST | `/merge-queue/:id/keep-both` | Keep both ideas |
| POST | `/merge-queue/:id/discard` | Discard duplicate |
| GET | `/master-doc` | Get master document |
| POST | `/master-doc/sections` | Create section |
| POST | `/master-doc/sections/:id/ideas` | Add idea to section |
| GET | `/master-doc/export/md` | Export as markdown |
| GET | `/notifications` | List notifications |
| GET | `/settings` | Get workspace settings |
| PATCH | `/settings` | Update settings + API key |
| POST | `/settings/validate-key` | Validate Anthropic API key |
| GET | `/admin/users` | List all users (admin only) |
| POST | `/admin/users` | Create user / invite teammate |
| POST | `/admin/users/:id/reset-password` | Reset user password |
| POST | `/admin/users/:id/generate-token` | Generate 24hr login token |
| POST | `/admin/users/:id/deactivate` | Deactivate user |
| DELETE | `/admin/users/:id` | Delete user |

Full interactive docs at `/docs` when running locally.

---

## Document Processing Pipeline

```
Upload / Paste
     ↓
Parse file (pdfplumber / python-docx / plain text)
     ↓
Chunk into sections (markdown-aware)
     ↓
Extract ideas via Claude API
     ↓
TF-IDF cosine similarity across ALL user ideas
     ↓
Claude verifies candidate pairs (wording + concept match)
     ↓
Save IdeaPair records + notify
     ↓
SSE streams progress to frontend in real time
```

---

## Local Setup

```bash
# 1. Clone and install
git clone https://github.com/fashan7/smartdocmerger-backend
cd smartdocmerger-backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env:
# ANTHROPIC_API_KEY=sk-ant-...
# SECRET_KEY=your-32-char-secret
# ADMIN_EMAIL=your@email.com

# 3. Run
uvicorn app.main:app --reload --port 8000

# 4. API docs
open http://localhost:8000/docs
```

---

## Running Tests

```bash
pytest
# 51 tests — auth, documents, ideas, services, admin
```

---

## Deployment (Railway)

```bash
# 1. Push to GitHub
# 2. New project on Railway → Deploy from GitHub repo
# 3. Add PostgreSQL plugin (auto-sets DATABASE_URL)
# 4. Set environment variables:
#    SECRET_KEY=...
#    ANTHROPIC_API_KEY=sk-ant-...
#    ADMIN_EMAIL=your@email.com
#    ENVIRONMENT=production
# Railway reads railway.toml for start command:
# alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

---

## Admin Setup (First Time)

1. Temporarily set `ENVIRONMENT=development`
2. Register your account via `/auth/register`
3. Set `ENVIRONMENT=production` (blocks all public signups)
4. Set `ADMIN_EMAIL=your@email.com`
5. Log in → Settings → Team → invite teammates

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `SECRET_KEY` | Yes | JWT signing key (min 32 chars) |
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `ADMIN_EMAIL` | Yes | Email with admin privileges |
| `ENVIRONMENT` | Yes | `development` or `production` |
| `ALGORITHM` | No | JWT algorithm (default: HS256) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | Token TTL (default: 10080 = 7 days) |
| `SIMILARITY_THRESHOLD` | No | Duplicate threshold (default: 0.75) |

---

## Frontend

→ [smartdocmerger-frontend](https://github.com/yourusername/smartdocmerger-frontend)
