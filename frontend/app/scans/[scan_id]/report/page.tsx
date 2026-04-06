"use client";
import LongitudinalChart from "@/components/charts/LongitudinalChart";
import TimelineStrip     from "@/components/charts/TimelineStrip";

import React, { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { format, parseISO } from "date-fns";
import { Download, ExternalLink, AlertTriangle, CheckCircle2, Info } from "lucide-react";

import AuthGuard         from "@/components/layout/AuthGuard";
import DashboardLayout   from "@/components/layout/DashboardLayout";
import MeasurementsTable from "@/components/reports/MeasurementsTable";
import RAGPassages       from "@/components/reports/RAGPassages";
import RANOBadge         from "@/components/ui/RANOBadge";
import ClinicalFlag      from "@/components/ui/ClinicalFlag";
import ErrorMessage      from "@/components/ui/ErrorMessage";
import { SkeletonCard, SkeletonText } from "@/components/ui/SkeletonLoader";

import { getPatientScans, getScanReport } from "@/lib/api";
import { FLAG_MESSAGES } from "@/lib/constants";
import type { FullReportData, RANOClass } from "@/types";

// ── Known limitations ─────────────────────────────────────────────────────────
const LIMITATIONS = [
  "L1 — Steroid logic does not incorporate neurological status or performance score.",
  "L2 — Pseudoprogression window: 24 weeks post-RT. MGMT methylation not available.",
  "L3 — Diameter measurement is strictly axial per RANO spec.",
  "L4 — T2/FLAIR non-enhancing progression not tracked.",
  "L5 — BGE-small (dim=384) used due to memory constraints.",
  "L8 — ±10% diameter error can approach ±25% RANO threshold in borderline cases.",
  "L9 — Intra-patient co-registration is SimpleITK rigid only.",
  "L10 — CR confirmation requires a second scan ≥4 weeks later.",
];

// ── Small reusable pieces ─────────────────────────────────────────────────────
function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div
      className="flex items-center justify-between px-4 py-2.5 border-b last:border-0"
      style={{ borderColor: "var(--border)" }}
    >
      <span className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--muted)" }}>
        {label}
      </span>
      <span className="text-[12px] font-mono" style={{ color: "var(--text)" }}>{value}</span>
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[10px] font-semibold uppercase tracking-wider mb-2" style={{ color: "var(--muted)" }}>
      {children}
    </p>
  );
}

function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={`rounded-xl border overflow-hidden ${className}`}
      style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}
    >
      {children}
    </div>
  );
}

// ── Right panel — Alerts ──────────────────────────────────────────────────────
function AlertsPanel({ agent1, agent2 }: { agent1: FullReportData["agent1"]; agent2: FullReportData["agent2"] }) {
  const alerts: { type: "red" | "amber" | "green"; msg: string }[] = [];

  if (agent1?.low_confidence_flag)
    alerts.push({ type: "amber", msg: "Low segmentation confidence — manual review recommended." });
  if (agent2?.rano_class === "PD")
    alerts.push({ type: "red", msg: "Progressive Disease detected — immediate clinical review required." });
  if (agent2?.pseudoprogression_flag)
    alerts.push({ type: "amber", msg: "Pseudoprogression flag raised — within 24 weeks of RT." });
  if (!alerts.length)
    alerts.push({ type: "green", msg: "No critical alerts for this scan." });

  const colours = {
    red:   { bg: "var(--red-dim)",   border: "var(--red)",   icon: <AlertTriangle size={12} style={{ color: "var(--red)" }} /> },
    amber: { bg: "var(--amber-dim)", border: "var(--amber)", icon: <AlertTriangle size={12} style={{ color: "var(--amber)" }} /> },
    green: { bg: "var(--green-dim)", border: "var(--green)", icon: <CheckCircle2  size={12} style={{ color: "var(--green)" }} /> },
  };

  return (
    <div className="space-y-2">
      {alerts.map((a, i) => {
        const c = colours[a.type];
        return (
          <div
            key={i}
            className="flex items-start gap-2 rounded-lg border px-3 py-2.5"
            style={{ backgroundColor: c.bg, borderColor: c.border }}
          >
            <span className="mt-0.5 shrink-0">{c.icon}</span>
            <p className="text-[11px] leading-relaxed" style={{ color: "var(--text)" }}>{a.msg}</p>
          </div>
        );
      })}
    </div>
  );
}

// ── Right panel — Confidence bar ──────────────────────────────────────────────
function ConfidenceBar({ value }: { value: number }) {
  const pct   = Math.round(value * 100);
  const color = pct >= 75 ? "var(--green)" : pct >= 50 ? "var(--amber)" : "var(--red)";
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-[11px]" style={{ color: "var(--muted)" }}>Softmax confidence</span>
        <span className="text-[13px] font-bold font-mono" style={{ color }}>{pct}%</span>
      </div>
      <div className="h-2 rounded-full" style={{ backgroundColor: "var(--surface-2)" }}>
        <div
          className="h-2 rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

// ── Right panel — Agent trace ─────────────────────────────────────────────────
function AgentTrace({ report }: { report: FullReportData }) {
  const agents = [
    { label: "Seg",   done: !!report.agent1 },
    { label: "RANO",  done: !!report.agent2 },
    { label: "Long",  done: !!report.agent3 },
    { label: "RAG",   done: !!report.agent4 },
    { label: "Report",done: true            },
  ];

  return (
    <div className="flex items-center justify-between">
      {agents.map((a, i) => (
        <React.Fragment key={a.label}>
          <div className="flex flex-col items-center gap-1">
            <div
              className="h-3 w-3 rounded-full border-2"
              style={{
                backgroundColor: a.done ? "var(--green)" : "var(--muted)",
                borderColor:     a.done ? "var(--green)" : "var(--border)",
              }}
            />
            <span className="text-[9px]" style={{ color: "var(--muted)" }}>{a.label}</span>
          </div>
          {i < agents.length - 1 && (
            <div className="flex-1 h-px mx-1" style={{ backgroundColor: "var(--border)" }} />
          )}
        </React.Fragment>
      ))}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function ReportPage() {
  const params  = useParams();
  const scan_id = params.scan_id as string;

  const [report,  setReport ] = useState<FullReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError  ] = useState<string | null>(null);
  const [timelinePoints, setTimelinePoints] = useState<
    { date: string; rano_class: RANOClass | null }[]
  >([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getScanReport(scan_id);
      setReport(data);
      setTimelinePoints([]);

      // Build RANO timeline from all completed scans for this patient.
      const scans = await getPatientScans(data.patient_id);
      const readyScans = scans.filter((s) => s.status === "REPORT_READY");
      const reportResults = await Promise.allSettled(
        readyScans.map((s) => getScanReport(s.scan_id))
      );

      const points = reportResults.flatMap((r, i) => {
        if (r.status !== "fulfilled") return [];
        return [{
          date: readyScans[i].scan_date,
          rano_class: r.value.agent2?.rano_class ?? null,
        }];
      });

      points.sort(
        (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime()
      );
      setTimelinePoints(points);
    } catch {
      setError("Failed to load report. The report may not be ready yet.");
    } finally {
      setLoading(false);
    }
  }, [scan_id]);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <AuthGuard>
        <DashboardLayout>
          <div className="space-y-4">
            <SkeletonCard className="h-16" />
            <div className="flex gap-5">
              <div className="flex-1 space-y-4">
                <SkeletonCard /><SkeletonCard /><SkeletonCard />
              </div>
              <div className="w-[240px] space-y-4">
                <SkeletonCard /><SkeletonCard />
              </div>
            </div>
          </div>
        </DashboardLayout>
      </AuthGuard>
    );
  }

  if (error || !report) {
    return (
      <AuthGuard>
        <DashboardLayout>
          <ErrorMessage
            title="Report unavailable"
            message={error ?? "Report data could not be loaded."}
            onRetry={load}
          />
        </DashboardLayout>
      </AuthGuard>
    );
  }

  const { agent1, agent2, agent3, agent4 } = report;

  return (
    <AuthGuard>
      <DashboardLayout>
        <div className="flex flex-col gap-4 pb-12">

          {/* ── Top bar ─────────────────────────────────────── */}
          <div
            className="flex items-center justify-between px-5 py-3 rounded-xl border"
            style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}
          >
            <div className="flex items-center gap-6">
              <div>
                <p className="text-[10px] uppercase tracking-wider font-semibold" style={{ color: "var(--muted)" }}>Patient</p>
                <p className="text-[13px] font-bold font-mono" style={{ color: "var(--text)" }}>{report.patient_id}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wider font-semibold" style={{ color: "var(--muted)" }}>Scan date</p>
                <p className="text-[13px] font-mono" style={{ color: "var(--text)" }}>
                  {format(parseISO(report.scan_date), "dd MMM yyyy")}
                </p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wider font-semibold" style={{ color: "var(--muted)" }}>Status</p>
                <p className="text-[12px] font-semibold" style={{ color: "var(--green)" }}>Report ready</p>
              </div>
              {agent1 && agent1.mean_softmax_prob !== undefined && (
                <div>
                  <p className="text-[10px] uppercase tracking-wider font-semibold" style={{ color: "var(--muted)" }}>Confidence</p>
                  <p className="text-[13px] font-bold font-mono" style={{
                    color: agent1.mean_softmax_prob >= 0.75
                      ? "var(--green)"
                      : agent1.mean_softmax_prob >= 0.5
                      ? "var(--amber)"
                      : "var(--red)",
                  }}>
                    {Math.round(agent1.mean_softmax_prob * 100)}%
                  </p>
                </div>
              )}
            </div>

            {report.download_url && (
              <button
                onClick={() => window.open(report.download_url, "_blank", "noopener,noreferrer")}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-white text-[12px] font-semibold transition-all duration-150"
                style={{ background: "linear-gradient(to right, #2f81f7, #1557b0)" }}
              >
                <Download size={13} />
                Download PDF
                <ExternalLink size={11} className="opacity-60" />
              </button>
            )}
          </div>

          {/* ── Disclaimer ──────────────────────────────────── */}
          <ClinicalFlag variant="warning" message={FLAG_MESSAGES.disclaimer} />

          {/* ── 2-column body ───────────────────────────────── */}
          <div className="flex gap-5 items-start">

            {/* ── Main column ─────────────────────────────────── */}
            <div className="flex-1 min-w-0 space-y-5">

              {/* §1 Measurements */}
              <div>
                <SectionLabel>Tumour measurements</SectionLabel>
                {agent1 ? (
                  <MeasurementsTable agent1={agent1} />
                ) : (
                  <ClinicalFlag variant="warning" message="Segmentation data unavailable — Agent 1 output missing." />
                )}
              </div>

              {/* §2 RANO */}
              <div>
                <SectionLabel>RANO classification</SectionLabel>
                {agent2 ? (
                  <div className="space-y-3">
                    <Card>
                      <div className="flex items-center justify-between px-4 py-4 border-b" style={{ borderColor: "var(--border)" }}>
                        <span className="text-[12px] font-semibold" style={{ color: "var(--muted)" }}>Classification</span>
                        <RANOBadge ranoClass={agent2.rano_class} size="lg" />
                      </div>
                      {agent2.pct_change_from_baseline !== null && (
                        <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: "var(--border)" }}>
                          <span className="text-[11px]" style={{ color: "var(--muted)" }}>Change from baseline</span>
                          <span className="text-[14px] font-bold font-mono" style={{
                            color: agent2.pct_change_from_baseline > 0 ? "var(--red)"
                              : agent2.pct_change_from_baseline < 0 ? "var(--green)"
                              : "var(--text)",
                          }}>
                            {agent2.pct_change_from_baseline > 0 ? "+" : ""}
                            {agent2.pct_change_from_baseline.toFixed(1)}%
                          </span>
                        </div>
                      )}
                      {agent2.baseline_type && (
                        <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: "var(--border)" }}>
                          <span className="text-[11px]" style={{ color: "var(--muted)" }}>Baseline type</span>
                          <span className="text-[11px] font-mono" style={{ color: "var(--text)" }}>{agent2.baseline_type}</span>
                        </div>
                      )}
                      <div className="flex items-center gap-4 px-4 py-3">
                        {[
                          { label: "New lesion", val: agent2.new_lesion_detected, color: agent2.new_lesion_detected ? "var(--red)" : "var(--green)" },
                          { label: "Steroid increase", val: agent2.steroid_increase, color: agent2.steroid_increase ? "var(--amber)" : "var(--green)" },
                        ].map(f => (
                          <div key={f.label} className="flex items-center gap-1.5">
                            <div className="h-2 w-2 rounded-full" style={{ backgroundColor: f.color }} />
                            <span className="text-[11px]" style={{ color: "var(--muted)" }}>
                              {f.label}: {f.val ? "Yes" : "No"}
                            </span>
                          </div>
                        ))}
                      </div>
                      {agent2.reasoning && (
                        <div className="px-4 py-3 border-t" style={{ borderColor: "var(--border)", backgroundColor: "var(--surface-2)" }}>
                          <p className="text-[10px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: "var(--muted)" }}>
                            Classification reasoning
                          </p>
                          <p className="text-[12px] leading-relaxed" style={{ color: "var(--muted)" }}>{agent2.reasoning}</p>
                        </div>
                      )}
                    </Card>
                    {agent2.rano_class === "CR_provisional" && <ClinicalFlag variant="info"    message={FLAG_MESSAGES.crProvisional} />}
                    {agent2.rano_class === "CR_confirmed"   && <ClinicalFlag variant="success"  message={FLAG_MESSAGES.crConfirmed}   />}
                    {agent2.rano_class === "PD"             && <ClinicalFlag variant="error"    message={FLAG_MESSAGES.pd}            />}
                    {agent2.pseudoprogression_flag          && <ClinicalFlag variant="warning"  message="Pseudoprogression flag raised — PD within 24 weeks of RT completion." />}
                  </div>
                ) : (
                  <ClinicalFlag variant="warning" message="RANO classification data unavailable." />
                )}
              </div>

              {/* §3 Longitudinal */}
              <div>
                <SectionLabel>Longitudinal trajectory</SectionLabel>
                {agent3 ? (
                  <div className="space-y-3">
                    <LongitudinalChart
                      data={(() => {
                        if (!agent3 || !Array.isArray(agent3.scan_dates)) return [];
                        return agent3.scan_dates.map((date, i) => {
                          const intervals = Array.isArray(agent3.trajectory_intervals)
                            ? agent3.trajectory_intervals : [];
                          const bp = i === 0
                            ? (intervals[0]?.bp_start ?? 0)
                            : (intervals[i - 1]?.bp_end ?? 0);
                          const isNadir = date === agent3.nadir_scan_date;
                          const changeFromNadir = agent3.nadir_bp_mm2 > 0
                            ? ((bp - agent3.nadir_bp_mm2) / agent3.nadir_bp_mm2) * 100
                            : 0;
                          const tp = timelinePoints.find((p) => p.date === date);
                          return {
                            scan_id:                   report.scan_id,
                            scan_date:                 date,
                            et_volume_ml:              bp / 100,
                            bidimensional_product_mm2: bp,
                            rano_class:                tp?.rano_class ?? null,
                            change_from_nadir_pct:     changeFromNadir,
                            is_nadir:                  isNadir,
                          };
                        });
                      })()}
                      metric="bidimensional_product_mm2"
                      title="Bidimensional product over time"
                      unit="mm²"
                      nadirDate={agent3.nadir_scan_date}
                    />
                    {Array.isArray(agent3.scan_dates) && agent3.scan_dates.length >= 2 && (
                      <TimelineStrip
                        points={
                          timelinePoints.length > 0
                            ? timelinePoints
                            : agent3.scan_dates.map((date) => ({
                                date,
                                rano_class: null,
                              }))
                        }
                      />
                    )}
                    <Card>
                      <MetaRow label="Overall trend"     value={agent3.overall_trend ?? "—"} />
                      <MetaRow label="Change from nadir" value={`${agent3.change_from_nadir_pct >= 0 ? "+" : ""}${agent3.change_from_nadir_pct.toFixed(1)}%`} />
                      <MetaRow label="Nadir scan"        value={agent3.nadir_scan_date ? format(parseISO(agent3.nadir_scan_date), "dd MMM yyyy") : "—"} />
                      <MetaRow label="Nadir product"     value={`${agent3.nadir_bp_mm2.toFixed(1)} mm²`} />
                      <MetaRow label="Timepoints"        value={String(Array.isArray(agent3.scan_dates) ? agent3.scan_dates.length : 0)} />
                    </Card>
                    {Array.isArray(agent3.inflection_points) && agent3.inflection_points.length > 0 && (
                      <Card className="p-4">
                        <p className="text-[10px] font-semibold uppercase tracking-wider mb-2" style={{ color: "var(--muted)" }}>
                          Trend turning points
                        </p>
                        <p className="text-[11px] mb-2" style={{ color: "var(--muted)" }}>
                          These are dates where the tumour trajectory changed direction (for example, worsening to improving).
                        </p>
                        <ul className="space-y-1">
                          {agent3.inflection_points.map((pt, i) => (
                            <li key={i} className="text-[12px] flex items-start gap-2" style={{ color: "var(--muted)" }}>
                              <span style={{ color: "var(--border)" }}>›</span>
                              <span>
                                Trend changed on{" "}
                                {format(parseISO(pt), "dd MMM yyyy")}
                              </span>
                            </li>
                          ))}
                        </ul>
                      </Card>
                    )}
                    {agent3.dissociation_flag && <ClinicalFlag variant="warning" message={FLAG_MESSAGES.dissociation} />}
                  </div>
                ) : (
                  <ClinicalFlag variant="warning" message="Longitudinal data unavailable — requires at least 2 timepoints." />
                )}
              </div>

              {/* §4 Literature */}
              <div>
                <SectionLabel>Clinical literature context</SectionLabel>
                <RAGPassages agent4={agent4} />
              </div>

              {/* §5 Limitations */}
              <div>
                <SectionLabel>Known limitations</SectionLabel>
                <Card className="p-4">
                  <ul className="space-y-2">
                    {LIMITATIONS.map((l) => (
                      <li key={l} className="text-[11px] leading-relaxed flex items-start gap-2" style={{ color: "var(--muted)" }}>
                        <span style={{ color: "var(--border)" }}>›</span>{l}
                      </li>
                    ))}
                  </ul>
                </Card>
              </div>

              {/* §6 Audit */}
              <div>
                <SectionLabel>Disclaimer & audit</SectionLabel>
                <ClinicalFlag variant="warning" message={FLAG_MESSAGES.disclaimer} />
                <div
                  className="flex items-center justify-between px-4 py-2.5 rounded-lg border mt-3"
                  style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}
                >
                  <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: "var(--muted)" }}>Audit reference</span>
                  <span className="text-[11px] font-mono" style={{ color: "var(--muted)" }}>{report.scan_id}</span>
                </div>
              </div>

            </div>

            {/* ── Right context panel ──────────────────────────── */}
            <div className="w-[240px] shrink-0 space-y-4 sticky top-4">

              {/* Alerts */}
              <div>
                <SectionLabel>Alerts</SectionLabel>
                <AlertsPanel agent1={agent1} agent2={agent2} />
              </div>

              {agent1 && (
                <div>
                  <SectionLabel>Segmentation confidence</SectionLabel>
                  <Card className="p-4">
                    {agent1.mean_softmax_prob !== undefined ? (
                      <ConfidenceBar value={agent1.mean_softmax_prob} />
                    ) : (
                      <p className="text-[11px]" style={{ color: "var(--muted)" }}>
                        {agent1.low_confidence_flag ? "⚠ Low confidence flagged" : "Confidence score not available"}
                      </p>
                    )}
                  </Card>
                </div>
              )}

              {/* Agent trace */}
              <div>
                <SectionLabel>Agent trace</SectionLabel>
                <Card className="p-4">
                  <AgentTrace report={report} />
                </Card>
              </div>

              {/* Scan metadata */}
              <div>
                <SectionLabel>Scan metadata</SectionLabel>
                <Card>
                  <MetaRow label="Scan ID"  value={report.scan_id.slice(0, 16) + "…"} />
                  <MetaRow label="R2 key"   value={report.r2_key.slice(0, 16) + "…"} />
                  <MetaRow label="Generated" value={format(parseISO(report.generation_ts), "dd MMM, HH:mm")} />
                </Card>
              </div>

            </div>
          </div>
        </div>
      </DashboardLayout>
    </AuthGuard>
  );
}