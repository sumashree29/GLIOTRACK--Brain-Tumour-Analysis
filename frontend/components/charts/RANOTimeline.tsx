"use client";

import React from "react";
import { format, parseISO } from "date-fns";
import { RANO_COLOURS } from "@/lib/constants";
import type { LongitudinalPoint } from "@/types";

interface RANOTimelineProps {
  data: LongitudinalPoint[];
}

export default function RANOTimeline({ data }: RANOTimelineProps) {
  const sorted = [...data].sort(
    (a, b) => new Date(a.scan_date).getTime() - new Date(b.scan_date).getTime()
  );

  return (
    <div
      className="rounded-xl border p-5"
      style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}
    >
      <p className="text-[12px] font-semibold mb-5" style={{ color: "var(--text)" }}>
        RANO Classification Timeline
      </p>

      <div className="relative">
        {sorted.length > 1 && (
          <div
            className="absolute top-[13px] left-[13px] h-px pointer-events-none"
            style={{
              backgroundColor: "var(--border)",
              right: `calc(100% - ${sorted.length * 80 - 40}px)`,
            }}
          />
        )}

        <div className="flex items-start gap-0 overflow-x-auto scrollbar-hide pb-2">
          {sorted.map((pt) => {
            const cls     = pt.rano_class;
            const colours = cls ? RANO_COLOURS[cls] : null;

            return (
              <div
                key={pt.scan_id}
                className="flex flex-col items-center shrink-0"
                style={{ minWidth: 80 }}
              >
                <div
                  className="relative z-10 flex h-7 w-7 items-center justify-center rounded-full border-2 mb-2"
                  style={
                    colours
                      ? { backgroundColor: colours.bg, borderColor: colours.border }
                      : { backgroundColor: "var(--surface-2)", borderColor: "var(--border)" }
                  }
                >
                  {pt.is_nadir && (
                    <span className="text-[10px] font-bold" style={{ color: colours?.text ?? "var(--amber)" }}>
                      ★
                    </span>
                  )}
                </div>

                <p className="text-[10px] font-mono text-center leading-tight" style={{ color: "var(--muted)" }}>
                  {format(parseISO(pt.scan_date), "MMM\nyy")}
                </p>

                {cls && (
                  <p
                    className="text-[9px] font-bold text-center mt-1 leading-tight max-w-[72px]"
                    style={{ color: colours?.text ?? "var(--muted)" }}
                  >
                    {cls === "CR_confirmed"   ? "CR ✓" :
                     cls === "CR_provisional" ? "CR ~" :
                     cls}
                  </p>
                )}

                {pt.change_from_nadir_pct !== null && (
                  <p
                    className="text-[9px] font-mono mt-0.5"
                    style={{
                      color:
                        (pt.change_from_nadir_pct ?? 0) > 25 ? "var(--red)" :
                        (pt.change_from_nadir_pct ?? 0) < 0  ? "var(--green)" :
                        "var(--muted)",
                    }}
                  >
                    {(pt.change_from_nadir_pct ?? 0) > 0 ? "+" : ""}
                    {(pt.change_from_nadir_pct ?? 0).toFixed(0)}%
                  </p>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div className="mt-4 pt-3 flex flex-wrap gap-3" style={{ borderTop: "1px solid var(--border)" }}>
        {(["CR_confirmed", "PR", "SD", "PD"] as const).map((cls) => (
          <div key={cls} className="flex items-center gap-1.5">
            <div
              className="h-2.5 w-2.5 rounded-full border"
              style={{ backgroundColor: RANO_COLOURS[cls].bg, borderColor: RANO_COLOURS[cls].border }}
            />
            <span className="text-[10px]" style={{ color: "var(--muted)" }}>
              {cls === "CR_confirmed" ? "CR" : cls}
            </span>
          </div>
        ))}
        <div className="flex items-center gap-1.5">
          <span className="text-[10px]" style={{ color: "var(--amber)" }}>★</span>
          <span className="text-[10px]" style={{ color: "var(--muted)" }}>Nadir</span>
        </div>
      </div>
    </div>
  );
}