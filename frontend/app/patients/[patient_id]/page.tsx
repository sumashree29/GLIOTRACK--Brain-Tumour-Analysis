"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { format, parseISO } from "date-fns";
import {
  UserCircle2,
  Upload,
  TrendingUp,
  FileText,
  Clock,
  CalendarDays,
  BarChart3,
} from "lucide-react";

import AuthGuard          from "@/components/layout/AuthGuard";
import DashboardLayout    from "@/components/layout/DashboardLayout";
import ScanHistoryList    from "@/components/patients/ScanHistoryList";
import { SkeletonCard, SkeletonTable } from "@/components/ui/SkeletonLoader";
import ErrorMessage       from "@/components/ui/ErrorMessage";

import { getPatient, getPatientScans, deleteScan } from "@/lib/api";
import type { PatientRecord, ScanRecord } from "@/types";

// ── Info card ─────────────────────────────────────────────────────────────────
function InfoCard({
  label,
  value,
  icon,
}: {
  label: string;
  value: string | number;
  icon:  React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-[#21262d] bg-[#161b22] p-4">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-[#484f58]">{icon}</span>
        <p className="text-[10px] font-semibold text-[#8b949e] uppercase tracking-wider">
          {label}
        </p>
      </div>
      <p className="text-[15px] font-bold text-[#e6edf3] font-mono truncate">
        {value}
      </p>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function PatientDetailPage() {
  const params     = useParams();
  const patient_id = params.patient_id as string;

  const [patient, setPatient] = useState<PatientRecord | null>(null);
  const [scans,   setScans  ] = useState<ScanRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError  ] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [p, s] = await Promise.all([
        getPatient(patient_id),
        getPatientScans(patient_id),
      ]);
      setPatient(p);
      setScans(s);
    } catch {
      setError("Failed to load patient data.");
    } finally {
      setLoading(false);
    }
  }, [patient_id]);

  useEffect(() => { load(); }, [load]);
// Delete failed scan
  const handleDeleteScan = useCallback(async (scan_id: string) => {
    if (!confirm("Delete this scan? This cannot be undone.")) return;
    try {
      await deleteScan(scan_id);
      setScans((prev) => prev.filter((s) => s.scan_id !== scan_id));
    } catch {
      alert("Cannot delete this scan. Only failed scans can be deleted from the backend.");
    }
  }, []);


  // Derived stats
  const completedScans = scans.filter((s) => s.status === "REPORT_READY").length;
  const pendingScans   = scans.filter(
    (s) =>
      s.status !== "REPORT_READY" &&
      s.status !== "FAILED" &&
      s.status !== "failed_timeout"
  ).length;
  const lastScanDate   = scans.length
    ? [...scans].sort(
        (a, b) =>
          new Date(b.scan_date).getTime() - new Date(a.scan_date).getTime()
      )[0].scan_date
    : null;

  return (
    <AuthGuard>
      <DashboardLayout>
        <div className="max-w-[900px] mx-auto space-y-5">

          {/* ── Header ──────────────────────────────────────── */}
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="
                flex h-11 w-11 items-center justify-center rounded-full
                bg-[#21262d] border border-[#30363d]
                text-[#8b949e] shrink-0
              ">
                <UserCircle2 size={22} />
              </div>
              <div>
                <h2 className="text-[18px] font-bold text-[#e6edf3] font-mono">
                  {patient_id}
                </h2>
                <p className="text-[12px] text-[#8b949e] mt-0.5">
                  {loading
                    ? "Loading…"
                    : patient
                    ? `Registered ${format(parseISO(patient.created_at), "d MMMM yyyy")}`
                    : "Patient"}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              {/* Longitudinal link — only if ≥2 completed scans */}
              {completedScans >= 2 && (
                <Link
                  href={`/longitudinal/${patient_id}`}
                  className="
                    inline-flex items-center gap-2 px-3 py-2 rounded-lg
                    border border-[#30363d] bg-[#161b22]
                    text-[12px] font-medium text-[#8b949e]
                    hover:text-[#e6edf3] hover:border-[#484f58]
                    transition-colors duration-150
                  "
                >
                  <BarChart3 size={13} />
                  Longitudinal
                </Link>
              )}

              <Link
                href={`/upload/${patient_id}`}
                className="
                  inline-flex items-center gap-2 px-4 py-2 rounded-lg
                  bg-gradient-to-r from-[#2f81f7] to-[#1557b0]
                  text-white text-[13px] font-semibold
                  hover:from-[#388bfd] hover:to-[#1d6fe8]
                  shadow-[0_0_14px_rgba(47,129,247,0.25)]
                  transition-all duration-150
                "
              >
                <Upload size={13} />
                Upload scan
              </Link>
            </div>
          </div>

          {/* ── Info cards ──────────────────────────────────── */}
          {loading ? (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <SkeletonCard key={i} />
              ))}
            </div>
          ) : error ? (
            <ErrorMessage
              title="Failed to load patient"
              message={error}
              onRetry={load}
            />
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <InfoCard
                label="Total scans"
                value={scans.length}
                icon={<CalendarDays size={13} />}
              />
              <InfoCard
                label="Reports ready"
                value={completedScans}
                icon={<FileText size={13} />}
              />
              <InfoCard
                label="In progress"
                value={pendingScans}
                icon={<Clock size={13} />}
              />
              <InfoCard
                label="Last scan"
                value={
                  lastScanDate
                    ? format(parseISO(lastScanDate), "dd MMM yy")
                    : "—"
                }
                icon={<TrendingUp size={13} />}
              />
            </div>
          )}

          {/* ── Scan history ─────────────────────────────────── */}
          <div>
            <p className="text-[11px] font-semibold text-[#8b949e] uppercase tracking-wider mb-3">
              Scan history
            </p>

            {loading ? (
              <div className="rounded-xl border border-[#21262d] bg-[#161b22] overflow-hidden">
                <SkeletonTable rows={5} cols={4} />
              </div>
            ) : (
              <ScanHistoryList scans={scans} onDeleteScan={handleDeleteScan} />
            )}
          </div>
        </div>
      </DashboardLayout>
    </AuthGuard>
  );
}
