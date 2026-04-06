"use client";

import React, { useEffect, useState, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  CheckCircle2, XCircle, Loader2, Clock,
  FileText, RefreshCw, AlertTriangle,
} from "lucide-react";

import AuthGuard       from "@/components/layout/AuthGuard";
import DashboardLayout from "@/components/layout/DashboardLayout";
import ClinicalFlag    from "@/components/ui/ClinicalFlag";

import { getScanStatus } from "@/lib/api";
import { STATUS_MAP, POLL_INTERVAL_MS, POLL_MAX, FLAG_MESSAGES, RUNNING_STATUSES } from "@/lib/constants";
import type { ScanStatus, ScanStatusResponse } from "@/types";

const PIPELINE_STAGES: { status: ScanStatus; label: string; agent: string }[] = [
  { status: "SEGMENTATION_RUNNING", label: "Tumour segmentation",    agent: "Agent 1 · Modal GPU" },
  { status: "RANO_RUNNING",         label: "RANO classification",     agent: "Agent 2 · Render"    },
  { status: "LONGITUDINAL_RUNNING", label: "Longitudinal analysis",   agent: "Agent 3 · Render"    },
  { status: "RAG_RUNNING",          label: "Clinical literature RAG", agent: "Agent 4 · Render"    },
  { status: "REPORT_RUNNING",       label: "PDF report generation",   agent: "Agent 5 · Render"    },
];

function getActiveStageIndex(status: ScanStatus): number {
  const ORDER: ScanStatus[] = [
    "PENDING",
    "SEGMENTATION_RUNNING", "SEGMENTATION_COMPLETE",
    "RANO_RUNNING",         "RANO_COMPLETE",
    "LONGITUDINAL_RUNNING", "LONGITUDINAL_COMPLETE",
    "RAG_RUNNING",          "RAG_COMPLETE",
    "REPORT_RUNNING",       "REPORT_READY",
  ];
  const idx = ORDER.indexOf(status);
  if (idx <= 2) return 0;
  if (idx <= 4) return 1;
  if (idx <= 6) return 2;
  if (idx <= 8) return 3;
  return 4;
}

function stageState(stageIndex: number, activeIndex: number, currentStatus: ScanStatus): "done" | "active" | "idle" | "failed" {
  if (currentStatus === "FAILED" || currentStatus === "failed_timeout") {
    if (stageIndex < activeIndex)  return "done";
    if (stageIndex === activeIndex) return "failed";
    return "idle";
  }
  if (currentStatus === "REPORT_READY") return "done";
  if (stageIndex < activeIndex)  return "done";
  if (stageIndex === activeIndex) return "active";
  return "idle";
}

function StageRow({ label, agent, state, isLast }: {
  label: string; agent: string; state: "done" | "active" | "idle" | "failed"; isLast: boolean;
}) {
  const color =
    state === "done"   ? "var(--green)" :
    state === "active" ? "var(--blue)"  :
    state === "failed" ? "var(--red)"   :
    "var(--border)";

  const textColor =
    state === "done"   ? "var(--text)"  :
    state === "active" ? "var(--blue)"  :
    state === "failed" ? "var(--red)"   :
    "var(--muted)";

  return (
    <div className="flex gap-4">
      <div className="flex flex-col items-center">
        <div
          className="flex h-7 w-7 items-center justify-center rounded-full border-2 shrink-0 transition-all duration-500"
          style={{ borderColor: color, backgroundColor: color + "18" }}
        >
          {state === "done"   && <CheckCircle2 size={13} style={{ color }} />}
          {state === "active" && <Loader2 size={13} style={{ color }} className="animate-spin" />}
          {state === "failed" && <XCircle size={13} style={{ color }} />}
          {state === "idle"   && <div className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />}
        </div>
        {!isLast && <div className="w-px flex-1 mt-1 transition-colors duration-500" style={{ backgroundColor: state === "done" ? "var(--green)" : "var(--border)", minHeight: 24 }} />}
      </div>
      <div className="pb-5 pt-0.5 min-w-0">
        <p className="text-[13px] font-semibold transition-colors duration-300" style={{ color: textColor }}>{label}</p>
        <p className="text-[11px] font-mono mt-0.5" style={{ color: "var(--muted)" }}>{agent}</p>
      </div>
    </div>
  );
}

function useElapsed(): string {
  const [secs, setSecs] = useState(0);
  const start = useRef(Date.now());
  useEffect(() => {
    const id = setInterval(() => setSecs(Math.floor((Date.now() - start.current) / 1000)), 1000);
    return () => clearInterval(id);
  }, []);
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export default function StatusPage() {
  const params  = useParams();
  const router  = useRouter();
  const scan_id = params.scan_id as string;

  const [statusData, setStatusData] = useState<ScanStatusResponse | null>(null);
  const [attempts,   setAttempts  ] = useState(0);
  const [timedOut,   setTimedOut  ] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const elapsed = useElapsed();

  useEffect(() => {
    let stopped = false;
    let attempt = 0;
    let timerId: ReturnType<typeof setTimeout> | null = null;

    async function tick() {
      if (stopped) return;
      attempt++;
      setAttempts(attempt);
      try {
        const data = await getScanStatus(scan_id);
        if (!stopped) {
          setStatusData(data);
          setFetchError(null);
          const terminal = data.status === "REPORT_READY" || data.status === "FAILED" || data.status === "failed_timeout";
          if (terminal) { stopped = true; return; }
        }
      } catch {
        if (!stopped) setFetchError("Connection error — retrying…");
      }
      if (stopped) return;
      if (attempt >= POLL_MAX) { setTimedOut(true); stopped = true; return; }
      timerId = setTimeout(tick, POLL_INTERVAL_MS);
    }

    timerId = setTimeout(tick, 0);
    return () => { stopped = true; if (timerId) clearTimeout(timerId); };
  }, [scan_id]);

  const status      = statusData?.status ?? "PENDING";
  const progress    = STATUS_MAP[status]?.progress ?? 0;
  const statusLabel = STATUS_MAP[status]?.label    ?? status;
  const activeIdx   = getActiveStageIndex(status);
  const isTerminal  = status === "REPORT_READY" || status === "FAILED" || status === "failed_timeout" || timedOut;
  const isFailed    = status === "FAILED" || status === "failed_timeout" || timedOut;

  const statusColor = status === "REPORT_READY" ? "var(--green)" : isFailed ? "var(--red)" : "var(--blue)";

  return (
    <AuthGuard>
      <DashboardLayout>
        <div className="max-w-[680px] mx-auto space-y-5">

          {/* Header */}
          <div>
            <h2 className="text-[18px] font-bold" style={{ color: "var(--text)" }}>Pipeline Status</h2>
            <p className="text-[11px] font-mono mt-0.5" style={{ color: "var(--muted)" }}>{scan_id}</p>
          </div>

          {/* Progress card */}
          <div className="rounded-xl border p-5 space-y-4" style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                {status === "REPORT_READY" && <CheckCircle2 size={16} style={{ color: "var(--green)" }} />}
                {isFailed && !timedOut && status !== "REPORT_READY" && <XCircle size={16} style={{ color: "var(--red)" }} />}
                {timedOut && <Clock size={16} style={{ color: "var(--red)" }} />}
                {!isTerminal && <Loader2 size={16} className="animate-spin" style={{ color: "var(--blue)" }} />}
                <span className="text-[14px] font-bold" style={{ color: statusColor }}>
                  {timedOut ? STATUS_MAP["failed_timeout"].label : statusLabel}
                </span>
              </div>
              <div className="flex items-center gap-3">
                {!isTerminal && (
                  <div className="flex items-center gap-1.5 text-[11px]" style={{ color: "var(--muted)" }}>
                    <Clock size={11} />{elapsed}
                  </div>
                )}
                <span className="text-[11px] font-mono" style={{ color: "var(--muted)" }}>Poll {attempts}/{POLL_MAX}</span>
              </div>
            </div>

            {/* Progress bar */}
            <div className="space-y-1.5">
              <div className="w-full h-2 rounded-full overflow-hidden" style={{ backgroundColor: "var(--surface-2)" }}>
                <div
                  className="h-full rounded-full transition-all duration-700"
                  style={{
                    width: `${progress}%`,
                    backgroundColor: isFailed ? "var(--red)" : status === "REPORT_READY" ? "var(--green)" : "var(--blue)",
                  }}
                />
              </div>
              <div className="flex justify-between text-[10px] font-mono" style={{ color: "var(--muted)" }}>
                <span>0%</span><span>{progress}%</span><span>100%</span>
              </div>
            </div>

            {fetchError && !isTerminal && (
              <p className="text-[11px] flex items-center gap-1.5" style={{ color: "var(--amber)" }}>
                <AlertTriangle size={11} /> {fetchError}
              </p>
            )}
          </div>

          {/* Pipeline timeline */}
          <div className="rounded-xl border p-5" style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}>
            <p className="text-[11px] font-semibold uppercase tracking-wider mb-5" style={{ color: "var(--muted)" }}>
              Pipeline stages
            </p>
            {PIPELINE_STAGES.map((stage, i) => (
              <StageRow
                key={stage.status}
                label={stage.label}
                agent={stage.agent}
                state={stageState(i, activeIdx, status)}
                isLast={i === PIPELINE_STAGES.length - 1}
              />
            ))}
          </div>

          {/* Terminal — success */}
          {status === "REPORT_READY" && (
            <Link
              href={`/scans/${scan_id}/report`}
              className="flex items-center gap-2 px-5 py-2.5 rounded-lg text-white text-[13px] font-semibold transition-all duration-150 w-fit"
              style={{ background: "linear-gradient(to right, var(--blue), #1557b0)" }}
            >
              <FileText size={14} />
              View report
            </Link>
          )}

          {/* Terminal — failed */}
          {(isFailed || timedOut) && (
            <div className="space-y-3">
              <ClinicalFlag
                variant="error"
                message={
                  timedOut
                    ? "Pipeline timed out after 20 minutes. The Modal GPU worker may be overloaded."
                    : statusData?.error
                    ? `Pipeline failed at stage: ${statusData.failed_stage ?? "unknown"}. ${statusData.error}`
                    : "Pipeline failed. Check system logs for details."
                }
              />
              <button
                onClick={() => router.back()}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border text-[12px] font-medium transition-colors duration-150"
                style={{ borderColor: "var(--border)", backgroundColor: "var(--surface-2)", color: "var(--muted)" }}
              >
                <RefreshCw size={12} />
                Go back and retry
              </button>
            </div>
          )}

          <ClinicalFlag variant="warning" message={FLAG_MESSAGES.disclaimer} compact />
        </div>
      </DashboardLayout>
    </AuthGuard>
  );
}