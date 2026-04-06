"use client";

import React, { useEffect, useState, useCallback } from "react";
import { format } from "date-fns";
import {
  CheckCircle2,
  XCircle,
  Loader2,
  Database,
  HardDrive,
  Server,
  RefreshCw,
  Brain,
  Shield,
} from "lucide-react";

import AuthGuard        from "@/components/layout/AuthGuard";
import DashboardLayout  from "@/components/layout/DashboardLayout";
import ClinicalFlag     from "@/components/ui/ClinicalFlag";
import { SkeletonCard } from "@/components/ui/SkeletonLoader";
import { getHealth }    from "@/lib/api";
import type { HealthResponse } from "@/types";

function HealthRow({
  icon,
  label,
  value,
  status,
}: {
  icon:   React.ReactNode;
  label:  string;
  value:  string;
  status: "ok" | "warn" | "error" | "unknown";
}) {
  const colour =
    status === "ok"    ? "#3fb950" :
    status === "warn"  ? "#d29922" :
    status === "error" ? "#f85149" :
    "#8b949e";

  return (
    <div className="flex items-center justify-between px-4 py-3.5 border-b border-[#21262d] last:border-0">
      <div className="flex items-center gap-3">
        <span className="text-[#484f58]">{icon}</span>
        <span className="text-[12px] text-[#8b949e]">{label}</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-[12px] font-mono text-[#e6edf3]">{value}</span>
        <div className="h-2 w-2 rounded-full" style={{ backgroundColor: colour }} />
      </div>
    </div>
  );
}

export default function AdminPage() {
  const [health,    setHealth  ] = useState<HealthResponse | null>(null);
  const [loading,   setLoading ] = useState(true);
  const [error,     setError   ] = useState<string | null>(null);
  const [lastCheck, setLastCheck] = useState<Date | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const h = await getHealth();
      setHealth(h);
      setLastCheck(new Date());
    } catch {
      setError("Health endpoint unreachable.");
      setHealth(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  function deriveStatus(val?: string): "ok" | "warn" | "error" | "unknown" {
    if (!val) return "unknown";
    const v = val.toLowerCase();
    if (v === "ok" || v === "healthy" || v === "connected") return "ok";
    if (v.includes("warn") || v.includes("degraded"))       return "warn";
    if (v.includes("error") || v.includes("fail"))          return "error";
    return "ok";
  }

  return (
    <AuthGuard requireAdmin>
      <DashboardLayout>
        <div className="max-w-[700px] mx-auto space-y-5">

          {/* ── Header ──────────────────────────────────────── */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="
                flex h-9 w-9 items-center justify-center rounded-lg
                bg-[#3d2e00] border border-[#d29922] text-[#d29922]
              ">
                <Shield size={16} />
              </div>
              <div>
                <h2 className="text-[18px] font-bold text-[#e6edf3]">
                  System Administration
                </h2>
                <p className="text-[11px] text-[#8b949e] mt-0.5">
                  Admin access only
                </p>
              </div>
            </div>

            <button
              onClick={load}
              disabled={loading}
              className="
                flex items-center gap-2 px-3 py-1.5 rounded-lg
                border border-[#30363d] bg-[#161b22]
                text-[12px] text-[#8b949e] font-medium
                hover:text-[#e6edf3] hover:border-[#484f58]
                disabled:opacity-40 disabled:cursor-not-allowed
                transition-colors duration-150
              "
            >
              <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
              Refresh
            </button>
          </div>

          {/* ── System health ────────────────────────────────── */}
          <div className="rounded-xl border border-[#21262d] bg-[#161b22] overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3.5 border-b border-[#21262d]">
              <p className="text-[12px] font-semibold text-[#e6edf3]">
                System Health
              </p>
              {lastCheck && (
                <span className="text-[10px] font-mono text-[#484f58]">
                  Last check: {format(lastCheck, "HH:mm:ss")}
                </span>
              )}
            </div>

            {loading ? (
              <div className="p-5 space-y-3">
                {Array.from({ length: 4 }).map((_, i) => (
                  <SkeletonCard key={i} className="h-10" />
                ))}
              </div>
            ) : error || !health ? (
              <div className="p-5">
                <ClinicalFlag
                  variant="error"
                  message={error ?? "Health check failed. Backend may be unavailable."}
                />
              </div>
            ) : (
              <div>
                <HealthRow
                  icon={<Server size={14} />}
                  label="API server"
                  value={health.status}
                  status={deriveStatus(health.status)}
                />
                {health.db && (
                  <HealthRow
                    icon={<Database size={14} />}
                    label="PostgreSQL (Supabase)"
                    value={health.db}
                    status={deriveStatus(health.db)}
                  />
                )}
                {health.storage && (
                  <HealthRow
                    icon={<HardDrive size={14} />}
                    label="Cloudflare R2 storage"
                    value={health.storage}
                    status={deriveStatus(health.storage)}
                  />
                )}
                {health.vector_db && (
                  <HealthRow
                    icon={<Brain size={14} />}
                    label="Qdrant vector DB (dim=384)"
                    value={health.vector_db}
                    status={deriveStatus(health.vector_db)}
                  />
                )}
                {health.version && (
                  <HealthRow
                    icon={<CheckCircle2 size={14} />}
                    label="Version"
                    value={health.version}
                    status="ok"
                  />
                )}
              </div>
            )}
          </div>

          {/* ── User management note ─────────────────────────── */}
          <div className="rounded-xl border border-[#21262d] bg-[#161b22] p-5">
            <p className="text-[12px] font-semibold text-[#e6edf3] mb-2">
              User Management
            </p>
            <p className="text-[13px] text-[#8b949e] leading-relaxed">
              User roles are managed directly in Supabase — contact your system
              administrator. All public registrations receive the{" "}
              <span className="text-[#2f81f7] font-mono font-semibold">doctor</span>{" "}
              role. Upgrading to{" "}
              <span className="text-[#d29922] font-mono font-semibold">admin</span>{" "}
              requires direct database modification by a Supabase admin.
            </p>
          </div>

          {/* ── Pipeline info ─────────────────────────────────── */}
          <div className="rounded-xl border border-[#21262d] bg-[#161b22] p-5">
            <p className="text-[12px] font-semibold text-[#e6edf3] mb-3">
              Pipeline Architecture
            </p>
            <div className="space-y-2">
              {[
                { tier: "Modal.com GPU",  detail: "Agent 1 — nnU-Net BraTS 2024, T4 GPU, per-second billing" },
                { tier: "Render.com",     detail: "Agents 2–5 — RANO, Longitudinal, RAG, Report" },
                { tier: "Supabase",       detail: "PostgreSQL + Storage — patients, scans, reports, jobs" },
                { tier: "Cloudflare R2",  detail: "DICOM zips + NIfTI masks — permanent keys, no presigned URLs" },
                { tier: "Qdrant Cloud",   detail: "Vector DB — BGE-small dim=384, 1GB free" },
                { tier: "Groq API",       detail: "LLM polish — grammar/readability only, numerical guard enforced" },
              ].map((row) => (
                <div key={row.tier} className="flex items-start gap-3">
                  <span className="
                    shrink-0 text-[10px] font-bold font-mono px-2 py-0.5 rounded
                    bg-[#21262d] text-[#8b949e] border border-[#30363d]
                    whitespace-nowrap
                  ">
                    {row.tier}
                  </span>
                  <p className="text-[11px] text-[#8b949e] leading-relaxed">
                    {row.detail}
                  </p>
                </div>
              ))}
            </div>
          </div>

        </div>
      </DashboardLayout>
    </AuthGuard>
  );
}
