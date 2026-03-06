# 🛡️ Anonymous Signal

**A privacy-first AI-powered anonymous reporting and early-warning intelligence platform.**

Citizens report corruption, crime, infrastructure failures, health risks, and public safety threats — completely anonymously. The platform uses AI to classify, cluster, score, and surface intelligence to analysts.

---

## 🎯 What It Does

| Feature                  | Details                                                               |
| ------------------------ | --------------------------------------------------------------------- |
| **Anonymous Submission** | Text, audio recording, image — no account, no IP, no tracking         |
| **AI Classification**    | Zero-shot classification into 8 categories (facebook/bart-large-mnli) |
| **Audio Transcription**  | Whisper-based local transcription (no external API)                   |
| **Severity Scoring**     | 0–100 score with explainable reasoning                                |
| **Pattern Clustering**   | Semantic embeddings detect related/emerging incidents                 |
| **Intelligence Alerts**  | Automatic surge alerts at 5/15/30 reports per cluster                 |
| **Intelligence Summary** | AI-generated briefings: "15 sanitation reports in 24h"                |
| **Analyst Dashboard**    | Charts, clusters, alerts, AI chatbot — RBAC-protected                 |
| **Mobile App**           | Flutter (iOS + Android) with audio recording and image upload         |

---

## 🔒 Privacy Guarantees

The system is designed around **privacy-by-default**:

- ❌ **No IP address** stored or logged — even in Nginx
- ❌ **No User-Agent** forwarded to the backend
- ❌ **No accounts** required for report submission
- ❌ **No GPS coordinates** — only optional text area hints
- ✅ **EXIF metadata** stripped from all images before storage
- ✅ **Audio metadata** (ID3 tags) stripped before storage
- ✅ **AES-256 encryption** (Fernet) for all report content
- ✅ **Anonymous file refs** — original filenames never stored

---

## 🏗️ Architecture

```
Mobile App (Flutter)  ──▶  Nginx (strips headers)  ──▶  FastAPI Backend
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
                                                    Next.js Dashboard
```

---

## Quick Start

### Prerequisites

- Docker + Docker Compose
- Python 3.11+ (for key generation)

### 1. Configure environment

```bash
cp .env.example .env

# Generate encryption key (CRITICAL — back this up!)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Paste output as ENCRYPTION_KEY in .env

# Generate JWT secret
openssl rand -hex 32
# Paste output as JWT_SECRET in .env

# Set strong passwords for POSTGRES_PASSWORD and REDIS_PASSWORD
```

### 2. Start services

```bash
docker-compose up --build
```

### 3. Access

| Service             | URL                        |
| ------------------- | -------------------------- |
| API                 | http://localhost:8000      |
| API Docs (dev only) | http://localhost:8000/docs |
| Dashboard           | http://localhost:3000      |

### 4. First login

Default admin credentials (change immediately!):

- Username: `admin`
- Password: `AdminPassword123!`

### 5. Run security audit

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

Requires: Flutter 3.x, Dart 3.x

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

| Category             | Description                                   |
| -------------------- | --------------------------------------------- |
| 🔴 Terrorism         | Terrorist threats, extremist activity         |
| 💰 Corruption        | Bribery, embezzlement, official misconduct    |
| 🚨 Crime Signals     | Criminal activity, suspicious behavior        |
| ⚠️ Public Safety     | Accidents, violence, emergencies              |
| 🏥 Health/Sanitation | Disease, contamination, unsanitary conditions |
| 🌿 Environmental     | Pollution, illegal dumping, toxic waste       |
| 🏗️ Infrastructure    | Roads, bridges, utilities, structural damage  |
| 📋 Service Delivery  | Government service failures                   |

---

## 🤖 AI Models

All models run **locally** — zero data leaves the system:

| Model                      | Purpose                  | Size         |
| -------------------------- | ------------------------ | ------------ |
| `faster-whisper/base`      | Audio transcription      | ~74M params  |
| `facebook/bart-large-mnli` | Zero-shot classification | ~400M params |
| `all-MiniLM-L6-v2`         | Semantic embeddings      | ~22M params  |

---

## 👥 RBAC Roles

| Role             | Access                                     |
| ---------------- | ------------------------------------------ |
| `analyst`        | View stats, clusters, alerts, use chatbot  |
| `senior_analyst` | + Acknowledge alerts, intelligence summary |
| `admin`          | Full access, resolve alerts                |

---

## 📁 Project Structure

```
anonymous-signal/
├── backend/              FastAPI backend
│   ├── app/
│   │   ├── api/v1/       Endpoints (reports, analytics, auth)
│   │   ├── core/         Config, database, middleware
│   │   ├── models/       SQLAlchemy models
│   │   ├── schemas/      Pydantic schemas
│   │   ├── security/     Encryption service
│   │   └── services/     Intelligence scheduler
│   └── sql/              Database init SQL
├── ai-service/           AI microservice
│   ├── classifier.py     Zero-shot classification
│   ├── clustering.py     Embeddings + clustering
│   ├── scoring.py        Severity scoring
│   ├── transcription.py  Whisper transcription
│   └── inference.py      Pipeline orchestrator
├── dashboard/            Next.js analyst dashboard
│   └── src/pages/        Main dashboard UI
├── mobile-app/           Flutter mobile app
│   └── lib/
│       ├── screens/      App screens
│       └── services/     API service
├── nginx/                Nginx config
├── docs/                 Architecture documentation
├── tests/                Full test suite
└── docker-compose.yml    Service orchestration
```

---

## 📜 License

_Built for national security. Designed for trust. Guaranteed for privacy._
