"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { format, parseISO, isAfter, subDays } from "date-fns";
import {
  Users, ScanLine, FileText, Clock,
  Plus, Upload, ArrowRight, RefreshCw, TrendingUp,
} from "lucide-react";

import AuthGuard       from "@/components/layout/AuthGuard";
import DashboardLayout from "@/components/layout/DashboardLayout";
import StatusBadge     from "@/components/ui/StatusBadge";
import { SkeletonCard, SkeletonTable } from "@/components/ui/SkeletonLoader";
import ErrorMessage    from "@/components/ui/ErrorMessage";
import ClinicalFlag    from "@/components/ui/ClinicalFlag";

import { getDashboardStats } from "@/lib/api";
import { getUser }           from "@/lib/auth";
import { FLAG_MESSAGES }     from "@/lib/constants";
import type { DashboardStats, ScanRecord } from "@/types";

// ── Stat card ─────────────────────────────────────────────────────────────────
function StatCard({ label, value, icon, accent, sub }: {
  label: string; value: number | string; icon: React.ReactNode; accent: string; sub?: string;
}) {
  return (
    <div
      className="relative rounded-xl border p-5 overflow-hidden transition-colors duration-200"
      style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}
    >
      <div
        className="absolute -top-6 -right-6 w-20 h-20 rounded-full opacity-10 blur-2xl pointer-events-none"
        style={{ backgroundColor: accent }}
      />
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-wider mb-2" style={{ color: "var(--muted)" }}>
            {label}
          </p>
          <p className="text-3xl font-bold font-mono leading-none" style={{ color: "var(--text)" }}>
            {value}
          </p>
          {sub && (
            <p className="mt-1.5 text-[11px] flex items-center gap-1" style={{ color: "var(--muted)" }}>
              <TrendingUp size={10} style={{ color: accent }} />
              {sub}
            </p>
          )}
        </div>
        <div
          className="shrink-0 flex h-9 w-9 items-center justify-center rounded-lg"
          style={{ backgroundColor: accent + "22", color: accent }}
        >
          {icon}
        </div>
      </div>
    </div>
  );
}

// ── Quick action ──────────────────────────────────────────────────────────────
function QuickAction({ href, icon, label, sub }: {
  href: string; icon: React.ReactNode; label: string; sub: string;
}) {
  return (
    <Link
      href={href}
      className="group flex items-center gap-4 px-5 py-4 rounded-xl border transition-all duration-200"
      style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}
    >
      <div
        className="flex h-9 w-9 items-center justify-center rounded-lg shrink-0 transition-colors duration-200"
        style={{ backgroundColor: "var(--surface-2)", color: "var(--muted)" }}
      >
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-semibold transition-colors" style={{ color: "var(--text)" }}>{label}</p>
        <p className="text-[11px] mt-0.5" style={{ color: "var(--muted)" }}>{sub}</p>
      </div>
      <ArrowRight size={14} style={{ color: "var(--muted)" }} />
    </Link>
  );
}

// ── Recent scan row ───────────────────────────────────────────────────────────
function ScanRow({ scan }: { scan: ScanRecord }) {
  const router = useRouter();
  return (
    <tr
      className="border-b last:border-0 cursor-pointer transition-colors duration-150"
      style={{ borderColor: "var(--border)" }}
      onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "var(--surface-2)")}
      onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
      onClick={() =>
        scan.status === "REPORT_READY"
          ? router.push(`/scans/${scan.scan_id}/report`)
          : router.push(`/status/${scan.scan_id}`)
      }
    >
      <td className="px-4 py-3">
        <span className="text-[12px] font-mono" style={{ color: "var(--muted)" }}>{scan.patient_id}</span>
      </td>
      <td className="px-4 py-3">
        <span className="text-[12px]" style={{ color: "var(--text)" }}>
          {format(parseISO(scan.scan_date), "dd MMM yyyy")}
        </span>
      </td>
      <td className="px-4 py-3">
        <StatusBadge status={scan.status} />
      </td>
      <td className="px-4 py-3 text-right">
        <span className="text-[11px]" style={{ color: "var(--muted)" }}>
          {format(parseISO(scan.created_at), "dd MMM, HH:mm")}
        </span>
      </td>
    </tr>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const user = getUser();
  const [stats,   setStats  ] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError  ] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getDashboardStats();
      setStats(data);
    } catch {
      setError("Failed to load dashboard. Check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const activeScanCount = stats?.recent_scans.filter(
    (s) =>
      s.status !== "REPORT_READY" &&
      s.status !== "FAILED" &&
      s.status !== "failed_timeout" &&
      isAfter(parseISO(s.created_at), subDays(new Date(), 1))
  ).length ?? 0;

  return (
    <AuthGuard>
      <DashboardLayout>
        <div className="max-w-[1100px] mx-auto space-y-6">

          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-[18px] font-bold" style={{ color: "var(--text)" }}>
                {user?.email ? `Good day, ${user.email.split("@")[0]}` : "Dashboard"}
              </h2>
              <p className="text-[12px] mt-0.5" style={{ color: "var(--muted)" }}>
                {format(new Date(), "EEEE, d MMMM yyyy")}
              </p>
            </div>
            <button
              onClick={load}
              disabled={loading}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg border text-[12px] font-medium transition-colors duration-150 disabled:opacity-40 disabled:cursor-not-allowed"
              style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)", color: "var(--muted)" }}
            >
              <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
              Refresh
            </button>
          </div>

          <ClinicalFlag variant="warning" message={FLAG_MESSAGES.disclaimer} compact />

          {/* Stat cards */}
          {loading && !stats ? (
            <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
              {Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)}
            </div>
          ) : error ? (
            <ErrorMessage title="Dashboard unavailable" message={error} onRetry={load} />
          ) : stats ? (
            <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
              <StatCard label="Total Patients"    value={stats.total_patients}    icon={<Users    size={16} />} accent="var(--blue)"  sub="Registered patients" />
              <StatCard label="Scans This Week"   value={stats.scans_this_week}   icon={<ScanLine size={16} />} accent="var(--amber)" sub="Last 7 days" />
              <StatCard label="Completed Reports" value={stats.completed_reports} icon={<FileText size={16} />} accent="var(--green)" sub="Ready to review" />
              <StatCard label="Pending Scans"     value={stats.pending_scans}     icon={<Clock    size={16} />}
                accent={activeScanCount > 0 ? "var(--red)" : "var(--muted)"}
                sub={activeScanCount > 0 ? `${activeScanCount} active now` : "All idle"} />
            </div>
          ) : null}

          {/* Body */}
          <div className="grid grid-cols-1 xl:grid-cols-[1fr_300px] gap-6">

            {/* Recent scans table */}
            <div className="rounded-xl border overflow-hidden" style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}>
              <div className="flex items-center justify-between px-4 py-3.5 border-b" style={{ borderColor: "var(--border)" }}>
                <p className="text-[13px] font-semibold" style={{ color: "var(--text)" }}>Recent Scans</p>
                <Link href="/patients" className="text-[11px] hover:underline" style={{ color: "var(--blue)" }}>
                  View all patients →
                </Link>
              </div>

              {loading && !stats ? (
                <SkeletonTable rows={6} cols={4} />
              ) : stats?.recent_scans.length === 0 ? (
                <div className="py-14 text-center">
                  <p className="text-sm" style={{ color: "var(--muted)" }}>No scans yet</p>
                  <p className="text-[11px] mt-1" style={{ color: "var(--muted)", opacity: 0.6 }}>Upload the first scan to get started</p>
                </div>
              ) : (
                <table className="w-full">
                  <thead>
                    <tr className="border-b" style={{ borderColor: "var(--border)", backgroundColor: "var(--surface-2)" }}>
                      {["Patient", "Scan date", "Status", "Created"].map((h) => (
                        <th key={h} className="px-4 py-2.5 text-left text-[10px] font-semibold uppercase tracking-wider" style={{ color: "var(--muted)" }}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {stats?.recent_scans.map((scan) => <ScanRow key={scan.scan_id} scan={scan} />)}
                  </tbody>
                </table>
              )}
            </div>

            {/* Quick actions */}
            <div className="space-y-3">
              <p className="text-[11px] font-semibold uppercase tracking-wider px-1" style={{ color: "var(--muted)" }}>
                Quick actions
              </p>
              <QuickAction href="/patients" icon={<Plus   size={16} />} label="New Patient"  sub="Register a patient ID"    />
              <QuickAction href="/patients" icon={<Upload size={16} />} label="Upload Scan"  sub="Start a new pipeline run" />

              {/* Pipeline info */}
              <div className="rounded-xl border p-4 mt-2" style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}>
                <p className="text-[11px] font-semibold uppercase tracking-wider mb-3" style={{ color: "var(--muted)" }}>Pipeline</p>
                <div className="space-y-2">
                  {[
                    { label: "Segmentation", note: "nnU-Net · BraTS 2024"     },
                    { label: "RANO",         note: "Agent 2 · Pure rules"      },
                    { label: "Longitudinal", note: "Agent 3 · Nadir tracking"  },
                    { label: "RAG",          note: "Agent 4 · BGE-small 384"   },
                    { label: "Report",       note: "Agent 5 · ReportLab PDF"   },
                  ].map((item) => (
                    <div key={item.label} className="flex items-center justify-between">
                      <span className="text-[11px]" style={{ color: "var(--text)" }}>{item.label}</span>
                      <span className="text-[10px] font-mono" style={{ color: "var(--muted)" }}>{item.note}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </DashboardLayout>
    </AuthGuard>
  );
}