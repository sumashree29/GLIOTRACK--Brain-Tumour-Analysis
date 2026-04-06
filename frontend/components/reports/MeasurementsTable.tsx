"use client";
import React from "react";
import VolumeBars from "@/components/charts/VolumeBar";
import type { Agent1Output } from "@/types";
interface Props { agent1: Agent1Output; }
function Row({ label, value, unit, highlight, sub, muted }: {
  label: string; value: number | string; unit: string; highlight?: boolean; sub?: string; muted?: boolean;
}) {
  return (
    <tr
      className="border-b last:border-0 transition-colors duration-100"
      style={{ borderColor: "var(--border)" }}
      onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "var(--surface-2)")}
      onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
    >
      <td className="px-4 py-3">
        <span className="text-[12px]" style={{ color: "var(--muted)" }}>{label}</span>
        {sub && <p className="text-[10px] mt-0.5" style={{ color: "var(--muted)", opacity: 0.6 }}>{sub}</p>}
      </td>
      <td className="px-4 py-3 text-right">
        <span className="font-mono font-bold text-[14px]" style={{ color: highlight ? "var(--blue)" : muted ? "var(--muted)" : "var(--text)" }}>
          {typeof value === "number" ? value.toFixed(2) : value}
        </span>
        <span className="text-[11px] ml-1.5" style={{ color: "var(--muted)" }}>{unit}</span>
      </td>
    </tr>
  );
}
export default function MeasurementsTable({ agent1 }: Props) {
  return (
    <div className="space-y-4">
      <VolumeBars et={agent1.et_volume_ml} tc={agent1.tc_volume_ml} wt={agent1.wt_volume_ml} />
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-wider px-1 mb-2" style={{ color: "var(--muted)" }}>
          Tumour volume snapshot
        </p>
        <div className="rounded-xl border overflow-hidden" style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}>
          <table className="w-full">
            <tbody>
              <Row label="ET — Enhancing Tumour" value={agent1.et_volume_ml} unit="mL" highlight sub="RANO target" />
              <Row label="TC — Tumour Core"       value={agent1.tc_volume_ml} unit="mL" />
              <Row label="WT — Whole Tumour"      value={agent1.wt_volume_ml} unit="mL" />
              <Row label="RC — Resection Cavity"  value={agent1.rc_volume_ml ?? 0} unit="mL" muted sub="Excluded from RANO — surgical cavity" />
            </tbody>
          </table>
        </div>
      </div>
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-wider px-1 mb-2" style={{ color: "var(--muted)" }}>
          RANO bidimensional measurements (ET only)
        </p>
        <div className="rounded-xl border overflow-hidden" style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}>
          <table className="w-full">
            <tbody>
              <Row label="Longest axial diameter" value={agent1.et_diameter1_mm}           unit="mm"  highlight />
              <Row label="Perpendicular diameter"  value={agent1.et_diameter2_mm}           unit="mm"            />
              <Row label="Bidimensional product"   value={agent1.bidimensional_product_mm2} unit="mm²" highlight sub="Sum across all measurable ET lesions" />
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
