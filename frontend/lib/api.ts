// ─────────────────────────────────────────────────────────────────────────────
// GLIOTRACK — API layer
//
// All requests go directly to process.env.NEXT_PUBLIC_API_BASE.
// No Next.js API route proxy — the Render backend handles CORS.
// Bearer token is attached automatically by the request interceptor.
// 401 responses clear the session and redirect to /login.
// ─────────────────────────────────────────────────────────────────────────────

import axios, { type AxiosInstance, type AxiosProgressEvent } from "axios";
import { getToken, clearSession } from "@/lib/auth";
import type {
  LoginResponse,
  PatientRecord,
  ScanRecord,
  ScanStatusResponse,
  FileUploadResponse,
  ReportResponse,
  FullReportData,
  HealthResponse,
  DashboardStats,
} from "@/types";

// ── Axios instance ────────────────────────────────────────────────────────────
const api: AxiosInstance = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_BASE,
  timeout: 30_000,
});

// Attach JWT on every outgoing request
api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// On 401 → clear session + redirect (client side only)
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (
      typeof window !== "undefined" &&
      err.response?.status === 401 &&
      !window.location.pathname.startsWith("/login")
    ) {
      clearSession();
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

// ── Auth ──────────────────────────────────────────────────────────────────────
export async function loginRequest(
  email: string,
  password: string
): Promise<LoginResponse> {
  const res = await api.post<LoginResponse>("/auth/login", { email, password });
  return res.data;
}

export async function registerRequest(
  email: string,
  password: string
): Promise<{ message: string }> {
  const res = await api.post<{ message: string }>("/auth/register", {
    email,
    password,
  });
  return res.data;
}

// ── Patients ──────────────────────────────────────────────────────────────────
export async function createPatient(patient_id: string): Promise<PatientRecord> {
  const res = await api.post<PatientRecord>("/patients/", { patient_id });
  return res.data;
}

export async function getPatient(patient_id: string): Promise<PatientRecord> {
  const res = await api.get<PatientRecord>(`/patients/${patient_id}`);
  return res.data;
}

export async function listPatients(): Promise<PatientRecord[]> {
  const res = await api.get<PatientRecord[]>("/patients/");
  return res.data;
}
export async function archivePatient(
  patient_id: string
): Promise<{ message: string }> {
  const res = await api.post<{ message: string }>(
    `/patients/${patient_id}/archive`
  );
  return res.data;
}

export async function restorePatient(
  patient_id: string
): Promise<{ message: string }> {
  const res = await api.post<{ message: string }>(
    `/patients/${patient_id}/restore`
  );
  return res.data;
}

export async function listArchivedPatients(): Promise<PatientRecord[]> {
  const res = await api.get<PatientRecord[]>("/patients/archived");
  return res.data;
}

export async function getPatientScans(patient_id: string): Promise<ScanRecord[]> {
  const res = await api.get<ScanRecord[]>(`/patients/${patient_id}/scans`);
  return res.data;
}

// ── Scans ─────────────────────────────────────────────────────────────────────
export async function createScan(
  patient_id: string,
  scan_date: string
): Promise<ScanRecord> {
  const res = await api.post<ScanRecord>("/scans", { patient_id, scan_date });
  return res.data;
}

export async function uploadSequenceFile(
  scan_id: string,
  sequence: string,
  file: File,
  onProgress?: (pct: number) => void
): Promise<FileUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("sequence", sequence);

  const res = await api.post<FileUploadResponse>(
    `/scans/${scan_id}/files`,
    form,
    {
      headers: { "Content-Type": "multipart/form-data" },
      // No timeout for file uploads — they can be large
      timeout: 0,
      onUploadProgress: (evt: AxiosProgressEvent) => {
        if (evt.total && onProgress) {
          onProgress(Math.round((evt.loaded / evt.total) * 100));
        }
      },
    }
  );
  return res.data;
}

export interface ClinicalMetadata {
  steroid_dose_current_mg:   number | null;
  steroid_dose_baseline_mg:  number | null;
  new_lesion_detected:       boolean;
  weeks_since_rt_completion: number | null;
  clinical_deterioration:    boolean;
  mgmt_status?:          string | null;
  idh_status?:           string | null;
  days_since_diagnosis?: number | null;
}

export async function runScanPipeline(
  scan_id: string,
  meta?: ClinicalMetadata
): Promise<{ message: string; scan_id: string }> {
  const form = new FormData();
  if (meta) {
    if (meta.steroid_dose_current_mg  != null) form.append("steroid_dose_current_mg",  String(meta.steroid_dose_current_mg));
    if (meta.steroid_dose_baseline_mg != null) form.append("steroid_dose_baseline_mg", String(meta.steroid_dose_baseline_mg));
    if (meta.weeks_since_rt_completion != null) form.append("weeks_since_rt_completion", String(meta.weeks_since_rt_completion));
    form.append("new_lesion_detected",    String(meta.new_lesion_detected));
    form.append("clinical_deterioration", String(meta.clinical_deterioration));
  }
  const res = await api.post<{ message: string; scan_id: string }>(
    `/scans/${scan_id}/run`,
    form,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
  return res.data;
}
export async function deleteScan(scan_id: string): Promise<void> {
  await api.delete(`/scans/${scan_id}`);
}

export async function getScanStatus(scan_id: string): Promise<ScanStatusResponse> {
  const res = await api.get<ScanStatusResponse>(`/scans/${scan_id}/status`);
  return res.data;
}

// ── Reports ───────────────────────────────────────────────────────────────────
export async function getScanReport(scan_id: string): Promise<FullReportData> {
  const res = await api.get<FullReportData>(`/scans/${scan_id}/full`);
  return res.data;
}

// ── Health ────────────────────────────────────────────────────────────────────
export async function getHealth(): Promise<HealthResponse> {
  const res = await api.get<HealthResponse>("/admin/health");
  return res.data;
}

// ── Dashboard stats (derived from available endpoints) ────────────────────────
export async function getDashboardStats(): Promise<DashboardStats> {
  // Fetch patients first, then scans for each in parallel
  const patients = await listPatients();

  const scanArrays = await Promise.allSettled(
    patients.map((p) => getPatientScans(p.patient_id))
  );

  const allScans: ScanRecord[] = scanArrays
    .filter((r): r is PromiseFulfilledResult<ScanRecord[]> => r.status === "fulfilled")
    .flatMap((r) => r.value);

  const now     = new Date();
  const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);

  const scans_this_week = allScans.filter(
    (s) => new Date(s.created_at) >= weekAgo
  ).length;

  const completed_reports = allScans.filter(
    (s) => s.status === "REPORT_READY"
  ).length;

  const pending_scans = allScans.filter(
    (s) =>
      s.status !== "REPORT_READY" &&
      s.status !== "FAILED" &&
      s.status !== "failed_timeout"
  ).length;

  const recent_scans = [...allScans]
    .sort(
      (a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    )
    .slice(0, 8);

  return {
    total_patients: patients.length,
    scans_this_week,
    completed_reports,
    pending_scans,
    recent_scans,
  };
}

export default api;
