# 🛡️ Anonymous Signal

**A privacy-first AI-powered anonymous reporting and early-warning intelligence platform.**

Citizens report corruption, crime, infrastructure failures, health risks, and public safety threats — completely anonymously. The platform uses AI to classify, cluster, score, and surface intelligence to analysts in real time.

---

## 🎯 What It Does

| Feature                   | Details                                                               |
| ------------------------- | --------------------------------------------------------------------- |
| **Anonymous Submission**  | Text, audio recording, image — no account, no IP, no tracking         |
| **AI Classification**     | Zero-shot classification into 8 categories (facebook/bart-large-mnli) |
| **Audio Transcription**   | Whisper-based local transcription — no external API                   |
| **Severity Scoring**      | 0–100 score with explainable reasoning                                |
| **Pattern Clustering**    | Semantic embeddings detect related and emerging incidents             |
| **Intelligence Alerts**   | Automatic surge alerts at 5/15/30 reports per cluster                 |
| **Intelligence Summary**  | AI-generated briefings: "15 sanitation reports in 24h"                |
| **Analyst Dashboard**     | Charts, clusters, alerts, AI chatbot — RBAC-protected                 |
| **Anonymous Tracking**    | One-time KE-XXXX-XXXX codes — reporters track status without identity |
| **Analyst–Reporter Chat** | Encrypted messaging channel via tracking code only                    |
| **Spam Detection**        | Automated credibility checks: spam filter + duplicate detection       |
| **Spam Box**              | Flagged reports quarantined, auto-deleted after 30 days               |
| **Mobile App**            | Flutter (iOS + Android) with audio recording and image upload         |

---

## 🔒 Privacy Guarantees

The system is designed around **privacy-by-default**:

- ❌ **No IP address** stored or logged — stripped at Nginx level
- ❌ **No User-Agent** forwarded to the backend
- ❌ **No accounts** required for report submission
- ❌ **No GPS coordinates** — only optional text area hints
- ❌ **No plaintext tracking codes** stored — bcrypt-hashed only
- ✅ **EXIF metadata** stripped from all images before storage
- ✅ **Audio metadata** (ID3 tags) stripped before storage
- ✅ **AES-256 encryption** (Fernet) for all report content at rest
- ✅ **Anonymous file refs** — original filenames never stored
- ✅ **JWT-protected analyst surface** — completely separate from reporter surface

---

## 🏗️ Architecture

```
Mobile App (Flutter)  ──▶  Nginx (HTTPS + strips headers)  ──▶  FastAPI Backend
                                                                       │
                                                             ┌─────────────────┐
                                                             │  AI Microservice │
                                                             │  (internal only) │
                                                             │  ┌────────────┐  │
                                                             │  │ Whisper    │  │
                                                             │  │ BART       │  │
                                                             │  │ MiniLM     │  │
                                                             │  └────────────┘  │
                                                             └─────────────────┘
                                                                       │
                                                                   PostgreSQL
                                                                       │
                                                           Next.js Analyst Dashboard
```

---

## 🚀 Quick Start

### Prerequisites

- Docker + Docker Compose
- Python 3.11+ (for key generation)
- OpenSSL (comes with Git for Windows)

### 1. Configure environment

```bash
cp .env.example .env

# Generate encryption key (CRITICAL — back this up securely!)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Paste output as ENCRYPTION_KEY in .env

# Generate JWT secret
openssl rand -hex 32
# Paste output as JWT_SECRET in .env

# Set strong passwords for POSTGRES_PASSWORD and REDIS_PASSWORD in .env
```

### 2. Generate SSL certificate (HTTPS)

```powershell
# Windows
.\generate_ssl.ps1

# Linux / macOS
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/ssl/selfsigned.key \
  -out nginx/ssl/selfsigned.crt \
  -subj "/C=KE/ST=Nairobi/L=Nairobi/O=AnonymousSignal/CN=localhost"
```

### 3. Start services

```bash
docker-compose up --build
```

### 4. Access

| Service             | URL                                          |
| ------------------- | -------------------------------------------- |
| Dashboard           | http://localhost (HTTP → redirects to HTTPS) |
| Dashboard (HTTPS)   | https://localhost                            |
| API                 | https://localhost/api/v1                     |
| API Docs (dev only) | https://localhost/api/v1/docs                |

> **Note:** The API and dashboard are served through Nginx on ports 80/443.  
> Direct access to backend (:8000) and dashboard (:3000) is internal only.

### 5. First login

Default admin credentials — **change immediately after first login:**

- **Username:** `admin`
- **Password:** `AdminPassword123!`

### 6. Run security audit

```bash
python backend/security/audit.py
```

All checks must pass before production deployment.

---

## 📱 Mobile App

```bash
cd mobile-app
flutter pub get
flutter run
```

**Requirements:** Flutter 3.x, Dart 3.x

**API base URL** (set in `lib/services/report_service.dart`):  
Change `http://192.168.100.78/api/v1` to your server's IP for physical device testing.

---

## 🧪 Testing

```bash
pip install pytest pytest-asyncio httpx
pytest tests/ -v --asyncio-mode=auto

# Run specific suites
pytest tests/ -v -k "Privacy"      # Privacy guarantee tests
pytest tests/ -v -k "API"          # API endpoint tests
pytest tests/ -v -k "AI"           # AI pipeline tests
pytest tests/ -v -k "E2E"          # End-to-end tests
pytest tests/ -v -k "Security"     # Security hardening tests
pytest tests/ -v -k "Scheduler"    # Intelligence scheduler tests
```

---

## 📊 Report Categories

| Category               | Description                                   |
| ---------------------- | --------------------------------------------- |
| 🔴 Terrorism           | Terrorist threats, extremist activity         |
| 💰 Corruption          | Bribery, embezzlement, official misconduct    |
| 🚨 Crime Signals       | Criminal activity, suspicious behavior        |
| ⚠️ Public Safety       | Accidents, violence, emergencies              |
| 🏥 Health / Sanitation | Disease, contamination, unsanitary conditions |
| 🌿 Environmental       | Pollution, illegal dumping, toxic waste       |
| 🏗️ Infrastructure      | Roads, bridges, utilities, structural damage  |
| 📋 Service Delivery    | Government service failures                   |

---

## 🤖 AI Models

All models run **locally** — zero data leaves the system. Models are pre-baked into the Docker image at build time and never downloaded at runtime.

| Model                      | Purpose                                   | Size         |
| -------------------------- | ----------------------------------------- | ------------ |
| `faster-whisper/base`      | Audio transcription                       | ~74M params  |
| `facebook/bart-large-mnli` | Zero-shot classification                  | ~400M params |
| `all-MiniLM-L6-v2`         | Semantic embeddings + duplicate detection | ~22M params  |

---

## 🚫 Spam & Credibility Detection

Every report passes a two-phase automated credibility check before AI classification:

**Phase 1 — Content Quality Filter**

- Minimum content length check (20 characters)
- Spam pattern detection (gibberish, test strings, keyboard mashing)
- Repetition ratio check
- Noise ratio check (non-alphabetic content)
- Vocabulary diversity check

**Phase 2 — Duplicate Detection**

- Cosine similarity against recent reports in same category (7-day window)
- Embedding-based similarity using MiniLM (when available)
- TF-IDF fallback if embeddings unavailable
- Reports above 92% similarity flagged as near-duplicates

Flagged reports are moved to the **Spam Box** in the analyst dashboard. Analysts can restore or permanently delete them. All spam reports are **auto-deleted after 30 days**.

---

## 👥 RBAC Roles

| Role             | Access                                                |
| ---------------- | ----------------------------------------------------- |
| `analyst`        | View stats, clusters, alerts, reports, use AI chatbot |
| `senior_analyst` | + Acknowledge alerts, intelligence summary            |
| `admin`          | Full access, resolve alerts, manage spam box          |

---

## 📁 Project Structure

```
anonymous-signal/
├── backend/                  FastAPI backend
│   ├── app/
│   │   ├── api/v1/           Endpoints (reports, analytics, auth)
│   │   ├── core/             Config, database, middleware
│   │   ├── models/           SQLAlchemy models
│   │   ├── schemas/          Pydantic schemas
│   │   ├── security/         Encryption service
│   │   └── services/         Intelligence scheduler (with spam auto-delete)
│   └── sql/                  Database init SQL
├── ai-service/               AI microservice
│   ├── classifier.py         Zero-shot classification (BART)
│   ├── clustering.py         Semantic embeddings + clustering (MiniLM)
│   ├── scoring.py            Severity scoring
│   ├── transcription.py      Whisper transcription
│   ├── false_report_detector.py  Spam + duplicate detection
│   └── inference.py          Pipeline orchestrator
├── dashboard/                Next.js analyst dashboard
│   └── src/pages/            Main dashboard UI
├── mobile-app/               Flutter mobile app
│   └── lib/
│       ├── screens/          App screens (submit, track, home, confirmation)
│       └── services/         API service layer
├── nginx/                    Nginx reverse proxy
│   ├── nginx.conf            HTTPS config with header stripping
│   └── ssl/                  SSL certificates (git-ignored)
├── docs/                     Architecture documentation
├── tests/                    Full test suite
├── .env.example              Environment variable template
├── generate_ssl.ps1          Self-signed cert generator (Windows)
└── docker-compose.yml        Service orchestration
```

---

## 🔐 Security Notes

- All secrets (`ENCRYPTION_KEY`, `JWT_SECRET`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD`) must be set via environment variables — never hardcoded
- The `.env` file must **never** be committed to git — add it to `.gitignore`
- For production: replace the self-signed certificate with a CA-signed cert via Let's Encrypt (`certbot`)
- The backend port 8000 is not exposed externally — all traffic goes through Nginx
- HSTS is enabled on HTTPS responses

---

## 📜 License

_Built for national security. Designed for trust. Guaranteed for privacy._
