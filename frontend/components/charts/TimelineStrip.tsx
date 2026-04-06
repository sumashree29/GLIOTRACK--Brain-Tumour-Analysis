"use client";

import React from "react";
import { format, parseISO } from "date-fns";
import type { RANOClass } from "@/types";

interface TimelinePoint {
  date: string;
  rano_class: RANOClass | null;
}

interface Props { points: TimelinePoint[]; }

const RANO_DOT: Record<string, string> = {
  CR_confirmed:   "var(--green)",
  CR_provisional: "var(--blue)",
  PR:             "var(--green)",
  SD:             "var(--muted)",
  PD:             "var(--red)",
};

const RANO_SHORT: Record<string, string> = {
  CR_confirmed:   "CR",
  CR_provisional: "CR?",
  PR:             "PR",
  SD:             "SD",
  PD:             "PD",
};

export default function TimelineStrip({ points }: Props) {
  if (!points.length) return null;

  return (
    <div className="rounded-xl border p-4" style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}>
      <p className="text-[10px] font-semibold uppercase tracking-wider mb-3" style={{ color: "var(--muted)" }}>
        RANO timeline
      </p>
      <div className="flex items-center">
        {points.map((pt, i) => {
          const color = pt.rano_class ? (RANO_DOT[pt.rano_class] ?? "var(--muted)") : "var(--muted)";
          const label = pt.rano_class ? (RANO_SHORT[pt.rano_class] ?? "—") : "—";
          return (
            <React.Fragment key={pt.date}>
              <div className="flex flex-col items-center gap-1.5 shrink-0">
                <div
                  className="h-4 w-4 rounded-full border-2 flex items-center justify-center"
                  style={{ backgroundColor: color, borderColor: "var(--surface)", boxShadow: `0 0 0 2px ${color}` }}
                />
                <span className="text-[9px] font-bold" style={{ color }}>{label}</span>
                <span className="text-[9px]" style={{ color: "var(--muted)" }}>
                  {format(parseISO(pt.date), "dd MMM yy")}
                </span>
              </div>
              {i < points.length - 1 && (
                <div className="flex-1 h-px mx-2" style={{ backgroundColor: "var(--border)" }} />
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
}