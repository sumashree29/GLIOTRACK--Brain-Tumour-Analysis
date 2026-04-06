"use client";

import React from "react";

interface VolumeBarProps {
  label: string;
  sub: string;
  value: number;
  max: number;
  color: string;
}

function VolumeBar({ label, sub, value, max, color }: VolumeBarProps) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <div>
          <span className="text-[12px] font-semibold" style={{ color: "var(--text)" }}>{label}</span>
          <span className="text-[10px] ml-1.5" style={{ color: "var(--muted)" }}>{sub}</span>
        </div>
        <span className="text-[13px] font-bold font-mono" style={{ color }}>{value.toFixed(2)} mL</span>
      </div>
      <div className="h-2 rounded-full" style={{ backgroundColor: "var(--surface-2)" }}>
        <div
          className="h-2 rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

interface Props {
  et: number;
  tc: number;
  wt: number;
}

export default function VolumeBars({ et, tc, wt }: Props) {
  const max = Math.max(et, tc, wt, 0.01);
  return (
    <div
      className="rounded-xl border p-4 space-y-4"
      style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}
    >
      <p className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: "var(--muted)" }}>
        Tumour volume snapshot
      </p>
      <VolumeBar label="ET" sub="Enhancing Tumour" value={et} max={max} color="var(--blue)"  />
      <VolumeBar label="TC" sub="Tumour Core"       value={tc} max={max} color="var(--amber)" />
      <VolumeBar label="WT" sub="Whole Tumour"      value={wt} max={max} color="var(--muted)" />
    </div>
  );
}