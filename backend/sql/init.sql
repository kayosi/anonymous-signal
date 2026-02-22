-- Anonymous Signal - Database Schema
-- Privacy-by-design: No PII columns anywhere in this schema.
-- All report content is stored encrypted at the application layer.

-- ─── Enable Extensions ────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─── Reports Table ────────────────────────────────────────────────────────
-- Core anonymous report submission.
-- PRIVACY GUARANTEE: No IP, no user agent, no account, no device ID.
CREATE TABLE IF NOT EXISTS reports (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Encrypted payload (Fernet symmetric encryption, AES-128-CBC)
    -- Contains: {text_content, transcription, location_hint}
    encrypted_content TEXT NOT NULL,

    -- Media references (encrypted filenames only, not plaintext)
    has_audio       BOOLEAN DEFAULT FALSE,
    has_image       BOOLEAN DEFAULT FALSE,
    audio_ref       TEXT,   -- Encrypted filename reference
    image_ref       TEXT,   -- Encrypted filename reference

    -- Pre-classification category (user-selected on mobile)
    user_category   VARCHAR(64),

    -- Processing status
    status          VARCHAR(32) DEFAULT 'pending'
                    CHECK (status IN ('pending', 'processing', 'analyzed', 'flagged', 'archived')),

    -- Timestamps (UTC only — no timezone that could identify region)
    submitted_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at    TIMESTAMP WITH TIME ZONE,

    -- Soft delete — never hard delete reports
    is_archived     BOOLEAN DEFAULT FALSE,

    -- EXPLICITLY NULL columns to prevent accidental data collection:
    -- ip_address: NOT STORED (guaranteed by application layer)
    -- user_agent: NOT STORED
    -- device_id:  NOT STORED
    -- session_id: NOT STORED
    CONSTRAINT no_pii_check CHECK (TRUE) -- Placeholder for audit tooling
);

-- ─── AI Analysis Table ────────────────────────────────────────────────────
-- One report can have multiple analyses (e.g., v1 model → v2 model upgrade)
CREATE TABLE IF NOT EXISTS report_ai_analysis (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_id           UUID NOT NULL REFERENCES reports(id) ON DELETE CASCADE,

    -- Classification output
    category            VARCHAR(64) NOT NULL,
    subcategory         VARCHAR(128),
    confidence_score    FLOAT CHECK (confidence_score BETWEEN 0 AND 1),

    -- Severity scoring (0–100)
    severity_score      INTEGER CHECK (severity_score BETWEEN 0 AND 100),
    urgency_level       VARCHAR(16) CHECK (urgency_level IN ('low', 'medium', 'high', 'critical')),

    -- Explainability fields
    classification_reasoning TEXT,
    severity_reasoning       TEXT,

    -- Embedding for clustering (stored as float array)
    embedding           FLOAT[],

    -- Cluster assignment
    cluster_id          UUID REFERENCES clusters(id) ON DELETE SET NULL,

    -- AI model metadata
    model_version       VARCHAR(64),
    analyzed_at         TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Transcription result (for audio reports)
    transcription       TEXT,
    transcription_confidence FLOAT,

    -- AI-generated summary of this report
    ai_summary          TEXT
);

-- ─── Clusters Table ───────────────────────────────────────────────────────
-- Groups of similar/related reports detected by clustering algorithm
CREATE TABLE IF NOT EXISTS clusters (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    category            VARCHAR(64),
    label               TEXT,           -- Human-readable cluster description
    centroid_embedding  FLOAT[],        -- Cluster centroid in embedding space
    report_count        INTEGER DEFAULT 0,
    first_seen          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_updated        TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active           BOOLEAN DEFAULT TRUE,
    -- Urgency escalated when cluster grows rapidly
    escalation_flag     BOOLEAN DEFAULT FALSE,
    notes               TEXT
);

-- ─── Alerts Table ─────────────────────────────────────────────────────────
-- System-generated alerts when patterns are detected
CREATE TABLE IF NOT EXISTS alerts (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    alert_type          VARCHAR(64) NOT NULL,
    -- Types: 'surge', 'high_severity', 'new_cluster', 'repeat_pattern', 'critical'
    category            VARCHAR(64),
    cluster_id          UUID REFERENCES clusters(id),
    title               TEXT NOT NULL,
    description         TEXT NOT NULL,
    severity_level      VARCHAR(16) DEFAULT 'medium',
    report_count        INTEGER,
    time_window_hours   INTEGER,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    acknowledged        BOOLEAN DEFAULT FALSE,
    acknowledged_at     TIMESTAMP WITH TIME ZONE,
    resolved            BOOLEAN DEFAULT FALSE,
    resolved_at         TIMESTAMP WITH TIME ZONE
);

-- ─── Dashboard Users (Analysts Only) ─────────────────────────────────────
-- These are analyst accounts — NOT linked to report submitters
CREATE TABLE IF NOT EXISTS analyst_users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username        VARCHAR(64) UNIQUE NOT NULL,
    -- bcrypt hashed password
    password_hash   TEXT NOT NULL,
    role            VARCHAR(32) DEFAULT 'analyst'
                    CHECK (role IN ('analyst', 'senior_analyst', 'admin')),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_login      TIMESTAMP WITH TIME ZONE
);

-- ─── Indexes ──────────────────────────────────────────────────────────────
CREATE INDEX idx_reports_status ON reports(status);
CREATE INDEX idx_reports_submitted_at ON reports(submitted_at DESC);
CREATE INDEX idx_reports_category ON reports(user_category);
CREATE INDEX idx_analysis_report_id ON report_ai_analysis(report_id);
CREATE INDEX idx_analysis_category ON report_ai_analysis(category);
CREATE INDEX idx_analysis_urgency ON report_ai_analysis(urgency_level);
CREATE INDEX idx_analysis_severity ON report_ai_analysis(severity_score DESC);
CREATE INDEX idx_clusters_category ON clusters(category);
CREATE INDEX idx_alerts_created_at ON alerts(created_at DESC);
CREATE INDEX idx_alerts_acknowledged ON alerts(acknowledged);

-- ─── Seed default admin ───────────────────────────────────────────────────
-- Password: 'AdminPassword123!' — MUST be changed after first login
INSERT INTO analyst_users (username, password_hash, role)
VALUES (
    'admin',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/HS.iRpa',
    'admin'
) ON CONFLICT DO NOTHING;
