# Anonymous Signal — Architecture & Developer Guide

## System Overview

Anonymous Signal is a privacy-first national early-warning intelligence platform. Citizens submit reports anonymously (text, audio, image). The system classifies, clusters, and scores them using AI, then surfaces intelligence insights to analysts via a secure dashboard.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        PUBLIC INTERNET                          │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS only
                    ┌────────▼─────────┐
                    │   Nginx Proxy    │
                    │  (rate limit,    │
                    │  strip headers,  │
                    │  no access logs) │
                    └────┬────────┬───┘
                         │        │
              ┌──────────▼──┐  ┌──▼──────────────┐
              │  FastAPI    │  │  Next.js         │
              │  Backend    │  │  Dashboard       │
              │  :8000      │  │  :3000           │
              └──────┬──────┘  └─────────────────┘
                     │ INTERNAL ONLY
          ┌──────────┼─────────────┐
          │          │             │
    ┌─────▼──┐  ┌────▼──────┐  ┌──▼──────┐
    │Postgres│  │  Redis    │  │AI Svc   │
    │  :5432 │  │  :6379    │  │  :8001  │
    │(expose)│  │(expose)   │  │(expose) │
    └────────┘  └───────────┘  └─────────┘
```

**Key**: All internal services use Docker `expose` (not `ports`) — they are NOT reachable from outside the Docker network.

---

## Privacy Architecture

### The Anonymity Guarantee

```
Report Submitter
      │
      │ HTTPS (TLS 1.3)
      ▼
Nginx (strips X-Forwarded-For, User-Agent, Referer)
      │
      ▼
PrivacyMiddleware (sets scope["client"] = None)
      │
      ▼
RateLimitMiddleware (time-bucket based, NOT IP-based)
      │
      ▼
Route Handler (no access to IP, UA, or any identifier)
      │
      ▼
FileEncryptionService (EXIF stripped, then AES-256 encrypted)
      │
      ▼
Database (stores only: encrypted_content, has_audio, has_image, status)
```

**What is NEVER stored:**
- IP address
- User-agent / browser fingerprint
- Device ID
- GPS coordinates
- Account or session ID
- Original filename
- Timestamp with timezone that could identify region

---

## Services

### 1. FastAPI Backend (`backend/`)

**Purpose:** Accept anonymous reports, authenticate analysts, serve dashboard data.

**Key modules:**
- `app/main.py` — App factory, middleware stack, lifecycle events
- `app/api/v1/endpoints/reports.py` — Report submission + analyst reads
- `app/api/v1/endpoints/analytics.py` — Dashboard stats, alerts, chatbot
- `app/api/v1/auth.py` — JWT auth, RBAC (analyst/senior_analyst/admin)
- `app/security/encryption.py` — Fernet encryption + EXIF stripping
- `app/core/privacy_middleware.py` — **Critical** — strips all identity headers
- `app/services/intelligence_scheduler.py` — Background surge detection

**Ports:** 8000 (public via Nginx)

### 2. AI Service (`ai-service/`)

**Purpose:** Process reports through the full ML pipeline.

**Pipeline steps:**
1. Decrypt report content
2. Transcribe audio (Whisper)
3. Combine text sources
4. Classify (facebook/bart-large-mnli zero-shot)
5. Score severity (0–100) and urgency
6. Generate embedding (all-MiniLM-L6-v2)
7. Assign to cluster (cosine similarity)
8. Generate AI summary
9. Save analysis to DB
10. Update report status to "analyzed"
11. Check surge thresholds → create alerts

**Ports:** 8001 (internal only — never exposed)

### 3. Intelligence Scheduler (runs inside Backend)

**Purpose:** Background asyncio task for proactive intelligence.

**Runs every 5 minutes:**
- Scans for category surges (5/15/30 threshold)
- Updates cluster escalation flags
- Resets stuck "processing" reports
- Creates intelligence alerts

### 4. Next.js Dashboard (`dashboard/`)

**Purpose:** Analyst interface for reviewing reports and intelligence.

**Tabs:**
- Overview — stat cards, trend chart, category breakdown, urgency pie
- Alerts — acknowledge alerts (senior_analyst+), filter by severity
- Clusters — view emerging patterns, escalation flags
- Reports — link to API, status overview
- Intelligence — AI-generated summaries (senior_analyst+)
- AI Chat — RAG chatbot over live report data

**Auth:** JWT bearer token, role-based tab restrictions

### 5. Flutter Mobile App (`mobile-app/`)

**Purpose:** Anonymous report submission from Android/iOS.

**Screens:**
- PrivacyNotice → Home → SubmitReport → Confirmation

**Features:**
- Text description
- Audio recording (WAV, Whisper-compatible)
- Image attach (camera or gallery)
- Category selection
- Location hint (text only, no GPS)

**Privacy:**
- Generic filenames (`audio.wav`, `image.jpeg`) — no device filename
- No device ID headers sent
- No app version tracking header

---

## Database Schema

```sql
reports               — Anonymous submissions (no PII columns)
  id                  UUID PK
  encrypted_content   TEXT (Fernet encrypted JSON)
  has_audio           BOOLEAN
  has_image           BOOLEAN
  audio_ref           TEXT (anonymous hash)
  image_ref           TEXT (anonymous hash)
  user_category       VARCHAR(64)
  status              ENUM(pending, processing, analyzed, flagged, archived)
  submitted_at        TIMESTAMP
  processed_at        TIMESTAMP

report_ai_analysis    — AI results (multiple per report)
  id                  UUID PK
  report_id           UUID FK → reports
  category            VARCHAR(64)
  confidence_score    FLOAT
  severity_score      INTEGER (0–100)
  urgency_level       ENUM(low, medium, high, critical)
  embedding           FLOAT[]
  cluster_id          UUID FK → clusters
  transcription       TEXT
  ai_summary          TEXT

clusters              — Report groupings
  id                  UUID PK
  category            VARCHAR(64)
  label               TEXT
  centroid_embedding  FLOAT[]
  report_count        INTEGER
  escalation_flag     BOOLEAN

alerts                — Intelligence alerts
  id                  UUID PK
  alert_type          VARCHAR(64)
  severity_level      VARCHAR(16)
  acknowledged        BOOLEAN
  resolved            BOOLEAN

analyst_users         — Dashboard accounts (NOT linked to submitters)
  id                  UUID PK
  username            VARCHAR(64)
  password_hash       TEXT (bcrypt)
  role                ENUM(analyst, senior_analyst, admin)
```

---

## RBAC Roles

| Action | analyst | senior_analyst | admin |
|--------|---------|----------------|-------|
| Submit report | ✅ (no auth) | ✅ | ✅ |
| View stats/clusters/alerts | ✅ | ✅ | ✅ |
| Use AI chatbot | ✅ | ✅ | ✅ |
| Acknowledge alerts | ❌ | ✅ | ✅ |
| View intelligence summary | ❌ | ✅ | ✅ |
| Resolve alerts | ❌ | ❌ | ✅ |
| Manage users | ❌ | ❌ | ✅ |

---

## Local Development

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env: set ENCRYPTION_KEY, JWT_SECRET, passwords

# 2. Generate encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 3. Start all services
docker-compose up --build

# 4. Access
#   API:       http://localhost:8000
#   Dashboard: http://localhost:3000
#   API Docs:  http://localhost:8000/docs  (development mode only)

# 5. Default admin login
#   Username: admin
#   Password: AdminPassword123!  ← CHANGE IMMEDIATELY

# 6. Run tests
pip install pytest pytest-asyncio
pytest tests/ -v --asyncio-mode=auto

# 7. Security audit
python backend/security/audit.py
```

---

## API Reference

### Public Endpoints (No Auth)

```
POST /api/v1/reports/submit     Submit anonymous report (multipart/form-data)
  Fields: text_content, user_category, location_hint
  Files:  audio_file, image_file

GET  /health                    Health check
```

### Analyst Endpoints (JWT Bearer)

```
POST /api/v1/auth/login         Login → returns JWT token

GET  /api/v1/reports/           List reports (paginated)
GET  /api/v1/reports/{id}       Get report detail (+ ?include_content=true)

GET  /api/v1/analytics/stats    Dashboard stats
GET  /api/v1/analytics/clusters Active report clusters
GET  /api/v1/analytics/alerts   Intelligence alerts
POST /api/v1/analytics/chatbot  AI chatbot query
```

### Senior Analyst / Admin

```
POST /api/v1/analytics/alerts/{id}/acknowledge    Acknowledge alert
GET  /api/v1/analytics/intelligence-summary       AI intelligence brief
```

---

## Deployment (Production)

1. Update `nginx.conf`: replace `api.anonymous-signal.gov` with your domain
2. Configure SSL certificates (Let's Encrypt or your provider)
3. Set all `.env` values — especially `ENCRYPTION_KEY` and `JWT_SECRET`
4. Change default admin password immediately after first login
5. Run `python backend/security/audit.py` — all checks must pass
6. Deploy: `docker-compose up -d`

---

## AI Models Used

| Model | Purpose | Size |
|-------|---------|------|
| `openai/whisper-base` (via faster-whisper) | Audio transcription | ~74M |
| `facebook/bart-large-mnli` | Zero-shot text classification | ~400M |
| `sentence-transformers/all-MiniLM-L6-v2` | Semantic embeddings | ~22M |

All models run **locally** — no data is sent to external AI APIs.
