"use client";

import React, { useEffect, useState, useCallback } from "react";
import { Plus, Loader2, AlertCircle, X } from "lucide-react";
import AuthGuard       from "@/components/layout/AuthGuard";
import DashboardLayout from "@/components/layout/DashboardLayout";
import PatientTable    from "@/components/patients/PatientTable";
import { SkeletonTable } from "@/components/ui/SkeletonLoader";
import ErrorMessage    from "@/components/ui/ErrorMessage";
import { listPatients, getPatientScans, createPatient, archivePatient, restorePatient, listArchivedPatients } from "@/lib/api";
import type { PatientRecord, ScanRecord } from "@/types";

function CreatePatientModal({ onClose, onCreated }: {
  onClose: () => void; onCreated: (p: PatientRecord) => void;
}) {
  const [id,      setId     ] = useState("");
  const [loading, setLoading] = useState(false);
  const [error,   setError  ] = useState<string | null>(null);
  const valid = /^[a-zA-Z0-9_-]{1,64}$/.test(id.trim());

  async function handleCreate() {
    if (!valid) return;
    setLoading(true); setError(null);
    try {
      const p = await createPatient(id.trim());
      onCreated(p); onClose();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Failed to create patient.");
    } finally { setLoading(false); }
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") onClose(); }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 backdrop-blur-sm" style={{ backgroundColor: "color-mix(in srgb, var(--bg) 80%, transparent)" }} onClick={onClose} />
      <div className="relative z-10 w-full max-w-sm rounded-2xl border p-6 shadow-2xl" style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}>
        <div className="flex items-center justify-between mb-5">
          <div>
            <h3 className="text-[15px] font-bold" style={{ color: "var(--text)" }}>New Patient</h3>
            <p className="text-[11px] mt-0.5" style={{ color: "var(--muted)" }}>Alphanumeric, hyphens and underscores only</p>
          </div>
          <button onClick={onClose} className="transition-colors" style={{ color: "var(--muted)" }} aria-label="Close">
            <X size={16} />
          </button>
        </div>

        {error && (
          <div className="flex items-start gap-2 mb-4 px-3 py-2.5 rounded-lg border" style={{ backgroundColor: "var(--red-dim)", borderColor: "var(--red)" }}>
            <AlertCircle size={13} className="mt-0.5 shrink-0" style={{ color: "var(--red)" }} />
            <p className="text-[12px]" style={{ color: "var(--red)" }}>{error}</p>
          </div>
        )}

        <div className="space-y-4">
          <div>
            <label className="block text-[11px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: "var(--muted)" }}>Patient ID</label>
            <input
              autoFocus type="text" value={id} onChange={(e) => setId(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && valid) handleCreate(); }}
              placeholder="e.g. PT-00142 or SMITH_JOHN" maxLength={64}
              className="w-full px-3.5 py-2.5 rounded-lg text-sm font-mono border focus:outline-none transition-colors duration-150"
              style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)", color: "var(--text)" }}
            />
            <p className="mt-1 text-[10px]" style={{ color: "var(--muted)" }}>
              {id.length}/64 characters
              {id.length > 0 && !valid && <span className="ml-2" style={{ color: "var(--red)" }}>Invalid characters detected</span>}
            </p>
          </div>

          <div className="flex gap-2 pt-1">
            <button
              onClick={onClose}
              className="flex-1 py-2.5 px-4 rounded-lg text-[13px] font-medium border transition-colors duration-150"
              style={{ borderColor: "var(--border)", backgroundColor: "transparent", color: "var(--muted)" }}
            >
              Cancel
            </button>
            <button
              onClick={handleCreate} disabled={!valid || loading}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg text-[13px] font-semibold text-white disabled:opacity-40 disabled:cursor-not-allowed transition-all duration-150"
              style={{ background: "linear-gradient(to right, var(--blue), #1557b0)" }}
            >
              {loading ? <><Loader2 size={13} className="animate-spin" /> Creating…</> : "Create patient"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function PatientsPage() {
  const [patients,         setPatients        ] = useState<PatientRecord[]>([]);
  const [archivedPatients, setArchivedPatients] = useState<PatientRecord[]>([]);
  const [scanCounts,       setScanCounts      ] = useState<Record<string, number>>({});
  const [lastScans,        setLastScans       ] = useState<Record<string, string>>({});
  const [loading,          setLoading         ] = useState(true);
  const [error,            setError           ] = useState<string | null>(null);
  const [showModal,        setShowModal       ] = useState(false);
  const [showArchived,     setShowArchived    ] = useState(false);
  const [archiveLoading,   setArchiveLoading  ] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [ps, archived] = await Promise.all([listPatients(), listArchivedPatients()]);
      setPatients(ps); setArchivedPatients(archived);
      const scanResults = await Promise.allSettled(ps.map((p) => getPatientScans(p.patient_id)));
      const counts: Record<string, number> = {};
      const lasts:  Record<string, string>  = {};
      scanResults.forEach((result, i) => {
        const pid = ps[i].patient_id;
        if (result.status === "fulfilled") {
          const scans: ScanRecord[] = result.value;
          counts[pid] = scans.length;
          const sorted = [...scans].sort((a, b) => new Date(b.scan_date).getTime() - new Date(a.scan_date).getTime());
          if (sorted[0]) lasts[pid] = sorted[0].scan_date;
        } else { counts[pid] = 0; }
      });
      setScanCounts(counts); setLastScans(lasts);
    } catch { setError("Failed to load patients."); }
    finally { setLoading(false); }
  }, []);

  async function handleArchive(patient_id: string) {
    setArchiveLoading(patient_id);
    try { await archivePatient(patient_id); await load(); } catch {} finally { setArchiveLoading(null); }
  }

  async function handleRestore(patient_id: string) {
    setArchiveLoading(patient_id);
    try { await restorePatient(patient_id); await load(); } catch {} finally { setArchiveLoading(null); }
  }

  useEffect(() => { load(); }, [load]);

  function handlePatientCreated(p: PatientRecord) {
    setPatients((prev) => [p, ...prev]);
    setScanCounts((prev) => ({ ...prev, [p.patient_id]: 0 }));
  }

  return (
    <AuthGuard>
      <DashboardLayout>
        <div className="max-w-[900px] mx-auto space-y-5">

          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-[18px] font-bold" style={{ color: "var(--text)" }}>Patients</h2>
              <p className="text-[12px] mt-0.5" style={{ color: "var(--muted)" }}>
                {loading ? "Loading…" : `${patients.length} patient${patients.length !== 1 ? "s" : ""} registered`}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowArchived(!showArchived)}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border text-[13px] font-medium transition-all duration-150"
                style={{ borderColor: "var(--border)", backgroundColor: "transparent", color: "var(--muted)" }}
              >
                {showArchived ? "Hide archived" : `Show archived (${archivedPatients.length})`}
              </button>
              <button
                onClick={() => setShowModal(true)}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-white text-[13px] font-semibold transition-all duration-150"
                style={{ background: "linear-gradient(to right, var(--blue), #1557b0)" }}
              >
                <Plus size={14} />
                New patient
              </button>
            </div>
          </div>

          {loading ? (
            <div className="rounded-xl border overflow-hidden" style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}>
              <SkeletonTable rows={6} cols={5} />
            </div>
          ) : error ? (
            <ErrorMessage title="Failed to load patients" message={error} onRetry={load} />
          ) : (
            <>
              <PatientTable
                patients={patients} scanCounts={scanCounts} lastScans={lastScans}
                onArchive={handleArchive} archiveLoading={archiveLoading}
              />
              {showArchived && archivedPatients.length > 0 && (
                <div className="mt-6">
                  <h3 className="text-[13px] font-semibold uppercase tracking-wider mb-3" style={{ color: "var(--muted)" }}>Archived patients</h3>
                  <div className="rounded-xl border overflow-hidden" style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}>
                    {archivedPatients.map((p) => (
                      <div key={p.patient_id} className="flex items-center justify-between px-5 py-3 border-b last:border-0" style={{ borderColor: "var(--border)" }}>
                        <div>
                          <p className="text-[13px] font-mono" style={{ color: "var(--muted)" }}>{p.patient_id}</p>
                          {p.archived_at && <p className="text-[11px] mt-0.5" style={{ color: "var(--muted)", opacity: 0.6 }}>Archived {new Date(p.archived_at).toLocaleDateString()}</p>}
                        </div>
                        <button
                          onClick={() => handleRestore(p.patient_id)} disabled={archiveLoading === p.patient_id}
                          className="px-3 py-1.5 rounded-lg text-[12px] font-medium border transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed"
                          style={{ borderColor: "var(--green)", color: "var(--green)", backgroundColor: "transparent" }}
                        >
                          {archiveLoading === p.patient_id ? "Restoring…" : "Restore"}
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {showArchived && archivedPatients.length === 0 && (
                <p className="text-[12px] text-center py-4" style={{ color: "var(--muted)" }}>No archived patients.</p>
              )}
            </>
          )}
        </div>
        {showModal && <CreatePatientModal onClose={() => setShowModal(false)} onCreated={handlePatientCreated} />}
      </DashboardLayout>
    </AuthGuard>
  );
}