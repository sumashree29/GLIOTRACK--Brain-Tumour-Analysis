-- ============================================================
-- Brain Tumour Assessment — Production Database Schema
-- Run this in: Supabase Dashboard → SQL Editor → Run
--
-- Fix #15 — users table now has role + email_verified columns
-- Fix #19 — audit_logs table added
-- Fix #21 — email_verifications + password_resets tables added
-- Fix #9  — patients.assigned_doctor + scans.doctor_email added
-- ============================================================

-- ── Users ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    email            TEXT PRIMARY KEY,
    hashed_password  TEXT        NOT NULL,
    role             TEXT        NOT NULL DEFAULT 'doctor'
                                 CHECK (role IN ('doctor', 'admin')),
    -- FIX #15, #20
    email_verified   BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Email verification tokens (Fix #20, #21) ──────────────────────────────────
CREATE TABLE IF NOT EXISTS email_verifications (
    token      TEXT        PRIMARY KEY,
    email      TEXT        NOT NULL REFERENCES users(email) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Password reset tokens (Fix #21) ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS password_resets (
    token      TEXT        PRIMARY KEY,
    email      TEXT        NOT NULL REFERENCES users(email) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Patients ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS patients (
    patient_id       TEXT        NOT NULL,
    -- FIX #9 — each patient record is owned by a specific doctor
    assigned_doctor  TEXT        NOT NULL REFERENCES users(email) ON DELETE CASCADE,
    age_at_diagnosis INT,
    diagnosis        TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (patient_id, assigned_doctor)
);

CREATE INDEX IF NOT EXISTS idx_patients_doctor ON patients(assigned_doctor);

-- ── Scans ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scans (
    scan_id       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id    TEXT        NOT NULL,
    -- FIX #9 — doctor ownership stored on scans
    doctor_email  TEXT        NOT NULL REFERENCES users(email),
    scan_date     DATE        NOT NULL,
    status        TEXT        NOT NULL DEFAULT 'PENDING',
    failed_stage  TEXT,
    error         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_scans_patient ON scans(patient_id, scan_date);
CREATE INDEX IF NOT EXISTS idx_scans_doctor  ON scans(doctor_email);

-- ── Agent outputs ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent1_outputs (
    scan_id                   UUID PRIMARY KEY REFERENCES scans(scan_id) ON DELETE CASCADE,
    scan_date                 DATE,
    et_volume_ml              FLOAT,
    tc_volume_ml              FLOAT,
    wt_volume_ml              FLOAT,
    et_diameter1_mm           FLOAT,
    et_diameter2_mm           FLOAT,
    bidimensional_product_mm2 FLOAT,
    dice_et                   FLOAT,
    dice_tc                   FLOAT,
    dice_wt                   FLOAT,
    low_confidence_flag       BOOLEAN DEFAULT FALSE,
    low_confidence_reason     TEXT
);

CREATE TABLE IF NOT EXISTS agent2_outputs (
    scan_id                    UUID PRIMARY KEY REFERENCES scans(scan_id) ON DELETE CASCADE,
    rano_class                 TEXT,
    pct_change_from_baseline   FLOAT,
    new_lesion_detected        BOOLEAN DEFAULT FALSE,
    non_measurable_progression BOOLEAN DEFAULT FALSE,
    steroid_increase           BOOLEAN DEFAULT FALSE,
    clinical_deterioration     BOOLEAN DEFAULT FALSE,
    low_confidence_flag        BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS agent3_outputs (
    scan_id               UUID PRIMARY KEY REFERENCES scans(scan_id) ON DELETE CASCADE,
    scan_dates            JSONB,
    nadir_bp_mm2          FLOAT,
    nadir_scan_date       DATE,
    change_from_nadir_pct FLOAT,
    overall_trend         TEXT,
    inflection_points     JSONB,
    trajectory_intervals  JSONB,
    dissociation_flag     BOOLEAN DEFAULT FALSE,
    low_confidence_flag   BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS agent4_outputs (
    scan_id        UUID PRIMARY KEY REFERENCES scans(scan_id) ON DELETE CASCADE,
    rag_available  BOOLEAN,
    failure_reason TEXT,
    query_used     TEXT,
    passage_count  INT
);

-- ── Reports ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS reports (
    scan_id           UUID PRIMARY KEY REFERENCES scans(scan_id) ON DELETE CASCADE,
    r2_key            TEXT        NOT NULL,
    generation_ts     TIMESTAMPTZ,
    prompt_tokens     INT DEFAULT 0,
    completion_tokens INT DEFAULT 0
);

-- ── Audit Logs (Fix #19) ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_logs (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_email  TEXT        NOT NULL,
    action        TEXT        NOT NULL,
    resource_type TEXT        NOT NULL,
    resource_id   TEXT        NOT NULL,
    ip_address    TEXT,
    details       JSONB,
    timestamp     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_doctor    ON audit_logs(doctor_email);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_resource  ON audit_logs(resource_type, resource_id);

-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_scans_status   ON scans(status);

-- ── Row Level Security (Fix R17) ──────────────────────────────────────────────
-- Enable RLS on all PHI-touching tables.
-- The service role key bypasses these, but they provide defence-in-depth:
-- if the anon key is ever accidentally used, no data leaks.

ALTER TABLE patients     ENABLE ROW LEVEL SECURITY;
ALTER TABLE scans        ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent1_outputs ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent2_outputs ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent3_outputs ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent4_outputs ENABLE ROW LEVEL SECURITY;
ALTER TABLE reports      ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs   ENABLE ROW LEVEL SECURITY;

-- Doctors can only see their own patients
CREATE POLICY IF NOT EXISTS doctor_own_patients ON patients
    USING (assigned_doctor = auth.jwt() ->> 'sub');

-- Doctors can only see their own scans
CREATE POLICY IF NOT EXISTS doctor_own_scans ON scans
    USING (doctor_email = auth.jwt() ->> 'sub');

-- Agent outputs and reports are visible only through scans owned by the doctor
CREATE POLICY IF NOT EXISTS doctor_own_agent1 ON agent1_outputs
    USING (scan_id IN (SELECT scan_id FROM scans WHERE doctor_email = auth.jwt() ->> 'sub'));

CREATE POLICY IF NOT EXISTS doctor_own_agent2 ON agent2_outputs
    USING (scan_id IN (SELECT scan_id FROM scans WHERE doctor_email = auth.jwt() ->> 'sub'));

CREATE POLICY IF NOT EXISTS doctor_own_agent3 ON agent3_outputs
    USING (scan_id IN (SELECT scan_id FROM scans WHERE doctor_email = auth.jwt() ->> 'sub'));

CREATE POLICY IF NOT EXISTS doctor_own_agent4 ON agent4_outputs
    USING (scan_id IN (SELECT scan_id FROM scans WHERE doctor_email = auth.jwt() ->> 'sub'));

CREATE POLICY IF NOT EXISTS doctor_own_reports ON reports
    USING (scan_id IN (SELECT scan_id FROM scans WHERE doctor_email = auth.jwt() ->> 'sub'));

-- Doctors can only see their own audit log entries
CREATE POLICY IF NOT EXISTS doctor_own_audit ON audit_logs
    USING (doctor_email = auth.jwt() ->> 'sub');

-- ── scan_files table (Fix S3) ──────────────────────────────────────────────────
-- Replaces the in-memory _pending dict. Stores the R2 keys for each uploaded
-- file so they survive server restarts and multi-worker deployments.
CREATE TABLE IF NOT EXISTS scan_files (
    id         BIGSERIAL PRIMARY KEY,
    scan_id    UUID        NOT NULL REFERENCES scans(scan_id) ON DELETE CASCADE,
    r2_key     TEXT        NOT NULL,
    sequence   TEXT        NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_scan_files_scan_id ON scan_files(scan_id);

ALTER TABLE scan_files ENABLE ROW LEVEL SECURITY;
CREATE POLICY IF NOT EXISTS doctor_own_scan_files ON scan_files
    USING (scan_id IN (SELECT scan_id FROM scans WHERE doctor_email = auth.jwt() ->> 'sub'));
