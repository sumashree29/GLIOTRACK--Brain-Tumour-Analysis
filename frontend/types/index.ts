// ─────────────────────────────────────────────────────────────────────────────
// GLIOTRACK — Central type definitions
// Single source of truth for all data shapes across the app
// ─────────────────────────────────────────────────────────────────────────────

// ── Scan pipeline status ──────────────────────────────────────────────────────
export type ScanStatus =
  | "PENDING"
  | "SEGMENTATION_RUNNING"
  | "SEGMENTATION_COMPLETE"
  | "RANO_RUNNING"
  | "RANO_COMPLETE"
  | "LONGITUDINAL_RUNNING"
  | "LONGITUDINAL_COMPLETE"
  | "RAG_RUNNING"
  | "RAG_COMPLETE"
  | "REPORT_RUNNING"
  | "REPORT_READY"
  | "FAILED"
  | "failed_timeout";

// ── RANO treatment response classification ────────────────────────────────────
export type RANOClass =
  | "CR_provisional"
  | "CR_confirmed"
  | "PR"
  | "SD"
  | "PD";

// ── Auth ──────────────────────────────────────────────────────────────────────
export interface User {
  email: string;
  role: "doctor" | "admin";
  access_token: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  role: "doctor" | "admin";
  email: string;
}

// ── Patients ──────────────────────────────────────────────────────────────────
export interface PatientRecord {
  patient_id: string;
  assigned_doctor: string;
  created_at: string;
}

// ── Scans ─────────────────────────────────────────────────────────────────────
export interface ScanRecord {
  scan_id: string;
  patient_id: string;
  scan_date: string;
  status: ScanStatus;
  doctor_email: string;
  created_at: string;
  updated_at: string | null;
  failed_stage: string | null;
  error: string | null;
}

export interface ScanStatusResponse {
  scan_id: string;
  status: ScanStatus;
  failed_stage: string | null;
  error: string | null;
}

export interface FileUploadResponse {
  r2_key: string;
  sequence: string;
  size_bytes: number;
}

// ── Agent outputs ─────────────────────────────────────────────────────────────
export interface Agent1Output {
  scan_id: string;
  scan_date: string;
  et_volume_ml: number;
  tc_volume_ml: number;
  wt_volume_ml: number;
  rc_volume_ml: number;
  et_diameter1_mm: number;
  et_diameter2_mm: number;
  bidimensional_product_mm2: number;
  dice_et: number;
  dice_tc: number;
  dice_wt: number;
  low_confidence_flag: boolean;
  low_confidence_reason: string | null;
  mean_softmax_prob?: number;
}

export interface Agent2Output {
  rano_class: RANOClass;
  pct_change_from_baseline: number | null;
  new_lesion_detected: boolean;
  steroid_increase: boolean;
  clinical_deterioration: boolean;
  low_confidence_flag: boolean;
  reasoning: string | null;
  pseudoprogression_flag: boolean;
  baseline_date: string | null;
  baseline_type: "post_op" | "nadir" | "unconfirmed" | null;
}

export interface Agent3Output {
  scan_dates: string[];
  nadir_bp_mm2: number;
  nadir_scan_date: string;
  change_from_nadir_pct: number;
  overall_trend: string | null;
  inflection_points: string[];
  dissociation_flag: boolean;
  dissociation_detail: string | null;
  low_confidence_flag: boolean;
}

export interface RAGPassage {
  source_document: string;
  guideline_version: string;
  publication_year: number;
  passage_text: string;
  relevance_score: number;
  bullets?: string[];
}

export interface Agent4Output {
  rag_available: boolean;
  passages: RAGPassage[];
}

// ── Reports ───────────────────────────────────────────────────────────────────
export interface ReportResponse {
  scan_id: string;
  r2_key: string;
  download_url: string;
  generation_ts: string;
}

export interface FullReportData {
  scan_id: string;
  patient_id: string;
  scan_date: string;
  r2_key: string;
  download_url: string;
  generation_ts: string;
  agent1: Agent1Output | null;
  agent2: Agent2Output | null;
  agent3: Agent3Output | null;
  agent4: Agent4Output | null;
}

// ── Longitudinal ──────────────────────────────────────────────────────────────
export interface LongitudinalPoint {
  scan_id: string;
  scan_date: string;
  et_volume_ml: number;
  bidimensional_product_mm2: number;
  rano_class: RANOClass | null;
  change_from_nadir_pct: number | null;
  is_nadir: boolean;
}

// ── Dashboard ─────────────────────────────────────────────────────────────────
export interface DashboardStats {
  total_patients: number;
  scans_this_week: number;
  completed_reports: number;
  pending_scans: number;
  recent_scans: ScanRecord[];
}

// ── System health ─────────────────────────────────────────────────────────────
export interface HealthResponse {
  status: string;
  version?: string;
  db?: string;
  storage?: string;
  vector_db?: string;
  uptime_seconds?: number;
}
