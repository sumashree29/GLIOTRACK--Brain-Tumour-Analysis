"use client";

import React, { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { format, parseISO } from "date-fns";

import AuthGuard         from "@/components/layout/AuthGuard";
import DashboardLayout   from "@/components/layout/DashboardLayout";
import LongitudinalChart from "@/components/charts/LongitudinalChart";
import RANOTimeline      from "@/components/charts/RANOTimeline";
import RANOBadge         from "@/components/ui/RANOBadge";
import ClinicalFlag      from "@/components/ui/ClinicalFlag";
import ErrorMessage      from "@/components/ui/ErrorMessage";
import { SkeletonCard }  from "@/components/ui/SkeletonLoader";

import { getPatientScans, getScanReport } from "@/lib/api";
import { FLAG_MESSAGES }                  from "@/lib/constants";
import type { LongitudinalPoint, ScanRecord, FullReportData } from "@/types";

function buildPoints(
  scans:   ScanRecord[],
  reports: Map<string, FullReportData>
): { points: LongitudinalPoint[]; nadirDate: string } {
  const pts: LongitudinalPoint[] = [];

  for (const scan of scans) {
    if (scan.status !== "REPORT_READY") continue;
    const report = reports.get(scan.scan_id);
    if (!report?.agent1) continue;

    pts.push({
      scan_id:                   scan.scan_id,
      scan_date:                 scan.scan_date,
      et_volume_ml:              report.agent1.et_volume_ml,
      bidimensional_product_mm2: report.agent1.bidimensional_product_mm2,
      rano_class:                report.agent2?.rano_class ?? null,
      change_from_nadir_pct:     report.agent3?.change_from_nadir_pct ?? null,
      is_nadir:                  false,
    });
  }

  pts.sort((a, b) => new Date(a.scan_date).getTime() - new Date(b.scan_date).getTime());

  let minProd  = Infinity;
  let nadirIdx = 0;
  pts.forEach((p, i) => {
    if (p.bidimensional_product_mm2 < minProd) {
      minProd  = p.bidimensional_product_mm2;
      nadirIdx = i;
    }
  });
  if (pts.length) pts[nadirIdx].is_nadir = true;

  return { points: pts, nadirDate: pts[nadirIdx]?.scan_date ?? "" };
}

export default function LongitudinalPage() {
  const params     = useParams();
  const patient_id = params.patient_id as string;

  const [points,    setPoints   ] = useState<LongitudinalPoint[]>([]);
  const [nadirDate, setNadirDate] = useState("");
  const [loading,   setLoading  ] = useState(true);
  const [error,     setError    ] = useState<string | null>(null);
  const [hasDissoc, setHasDissoc] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const scans      = await getPatientScans(patient_id);
      const readyScans = scans.filter((s) => s.status === "REPORT_READY");

      if (readyScans.length < 2) {
        setError("Longitudinal analysis requires at least 2 completed scans for this patient.");
        setLoading(false);
        return;
      }

      const reportResults = await Promise.allSettled(
        readyScans.map((s) => getScanReport(s.scan_id))
      );

      const reportMap = new Map<string, FullReportData>();
      let dissoc = false;
      reportResults.forEach((r, i) => {
        if (r.status === "fulfilled") {
          reportMap.set(readyScans[i].scan_id, r.value);
          if (r.value.agent3?.dissociation_flag) dissoc = true;
        }
      });

      const { points: pts, nadirDate: nd } = buildPoints(readyScans, reportMap);
      setPoints(pts);
      setNadirDate(nd);
      setHasDissoc(dissoc);
    } catch {
      setError("Failed to load longitudinal data.");
    } finally {
      setLoading(false);
    }
  }, [patient_id]);

  useEffect(() => { load(); }, [load]);

  return (
    <AuthGuard>
      <DashboardLayout>
        <div className="max-w-[900px] mx-auto space-y-5">

          <div>
            <h2 className="text-[18px] font-bold" style={{ color: "var(--text)" }}>
              Longitudinal Analysis
            </h2>
            <p className="text-[11px] font-mono mt-0.5" style={{ color: "var(--muted)" }}>
              Patient: {patient_id}
            </p>
          </div>

          {loading ? (
            <div className="grid grid-cols-1 gap-5">
              <SkeletonCard className="h-64" />
              <SkeletonCard className="h-64" />
              <SkeletonCard className="h-32" />
            </div>
          ) : error ? (
            <ErrorMessage title="Longitudinal analysis unavailable" message={error} onRetry={load} />
          ) : (
            <>
              <ClinicalFlag variant="warning" message={FLAG_MESSAGES.disclaimer} compact />

              {hasDissoc && (
                <ClinicalFlag variant="warning" message={FLAG_MESSAGES.dissociation} />
              )}

              <LongitudinalChart
                data={points}
                metric="et_volume_ml"
                title="Enhancing Tumour Volume over time"
                unit="mL"
                nadirDate={nadirDate}
              />

              <LongitudinalChart
                data={points}
                metric="bidimensional_product_mm2"
                title="Bidimensional Product over time"
                unit="mm²"
                nadirDate={nadirDate}
              />

              <RANOTimeline data={points} />

              {/* All timepoints table */}
              <div
                className="rounded-xl border overflow-hidden"
                style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}
              >
                <div className="px-4 py-3.5" style={{ borderBottom: "1px solid var(--border)" }}>
                  <p className="text-[12px] font-semibold" style={{ color: "var(--text)" }}>
                    All timepoints
                  </p>
                </div>
                <table className="w-full">
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border)" }}>
                      {["Scan date", "ET volume", "Bi-product", "RANO", "Δ from nadir"].map((h) => (
                        <th
                          key={h}
                          className="px-4 py-2.5 text-left text-[10px] font-semibold uppercase tracking-wider"
                          style={{ color: "var(--muted)" }}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {points.map((pt) => (
                      <tr
                        key={pt.scan_id}
                        className="transition-colors duration-100"
                        style={{
                          borderBottom: "1px solid var(--border)",
                          backgroundColor: pt.is_nadir ? "var(--amber-dim)" : "transparent",
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "var(--surface-2)")}
                        onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = pt.is_nadir ? "var(--amber-dim)" : "transparent")}
                      >
                        <td className="px-4 py-3">
                          <span className="text-[12px]" style={{ color: "var(--text)" }}>
                            {format(parseISO(pt.scan_date), "dd MMM yyyy")}
                          </span>
                          {pt.is_nadir && (
                            <span className="ml-2 text-[9px] font-bold uppercase" style={{ color: "var(--amber)" }}>
                              ★ nadir
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <span className="font-mono text-[12px] font-bold" style={{ color: "var(--blue)" }}>
                            {pt.et_volume_ml.toFixed(2)}
                          </span>
                          <span className="text-[10px] ml-1" style={{ color: "var(--muted)" }}>mL</span>
                        </td>
                        <td className="px-4 py-3">
                          <span className="font-mono text-[12px]" style={{ color: "var(--text)" }}>
                            {pt.bidimensional_product_mm2.toFixed(1)}
                          </span>
                          <span className="text-[10px] ml-1" style={{ color: "var(--muted)" }}>mm²</span>
                        </td>
                        <td className="px-4 py-3">
                          {pt.rano_class ? (
                            <RANOBadge ranoClass={pt.rano_class} size="sm" />
                          ) : (
                            <span className="text-[11px]" style={{ color: "var(--muted)" }}>—</span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          {pt.change_from_nadir_pct !== null ? (
                            <span
                              className="font-mono text-[12px] font-bold"
                              style={{
                                color:
                                  pt.change_from_nadir_pct > 25 ? "var(--red)"   :
                                  pt.change_from_nadir_pct < 0  ? "var(--green)" :
                                  "var(--muted)",
                              }}
                            >
                              {pt.change_from_nadir_pct > 0 ? "+" : ""}
                              {pt.change_from_nadir_pct.toFixed(1)}%
                            </span>
                          ) : (
                            <span className="text-[11px]" style={{ color: "var(--muted)" }}>—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </DashboardLayout>
    </AuthGuard>
  );
}