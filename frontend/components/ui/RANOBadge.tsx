"use client";

import React from "react";
import { CheckCircle2, Clock, TrendingDown, Minus, TrendingUp } from "lucide-react";
import type { RANOClass } from "@/types";

const COLOURS: Record<RANOClass, { bg: string; color: string; border: string }> = {
  CR_confirmed:   { bg: "var(--green-dim)", color: "var(--green)", border: "var(--green)" },
  CR_provisional: { bg: "var(--blue-dim)",  color: "var(--blue)",  border: "var(--blue)"  },
  PR:             { bg: "var(--green-dim)", color: "var(--green)", border: "var(--green)" },
  SD:             { bg: "var(--amber-dim)", color: "var(--amber)", border: "var(--amber)" },
  PD:             { bg: "var(--red-dim)",   color: "var(--red)",   border: "var(--red)"   },
};

const LABELS: Record<RANOClass, string> = {
  CR_confirmed:   "Complete Response — Confirmed",
  CR_provisional: "Complete Response — Provisional",
  PR:             "Partial Response",
  SD:             "Stable Disease",
  PD:             "Progressive Disease",
};

const ICONS: Record<RANOClass, React.ElementType> = {
  CR_confirmed:   CheckCircle2,
  CR_provisional: Clock,
  PR:             TrendingDown,
  SD:             Minus,
  PD:             TrendingUp,
};

const SIZE = {
  sm: { iconPx: 11, text: "text-[11px]", pad: "px-2 py-0.5", gap: "gap-1"   },
  md: { iconPx: 13, text: "text-xs",     pad: "px-3 py-1",   gap: "gap-1.5" },
  lg: { iconPx: 15, text: "text-sm",     pad: "px-4 py-1.5", gap: "gap-2"   },
};

interface Props { ranoClass: RANOClass | null; size?: "sm" | "md" | "lg"; className?: string; }

export default function RANOBadge({ ranoClass, size = "md", className = "" }: Props) {
  if (!ranoClass) {
    return (
      <span className={`inline-flex items-center font-semibold rounded border px-3 py-1 text-xs gap-1.5 ${className}`}
        style={{ backgroundColor: "var(--surface-2)", color: "var(--muted)", borderColor: "var(--border)" }}>
        N/A — First scan
      </span>
    );
  }
  const c = COLOURS[ranoClass];
  const s = SIZE[size];
  const Icon = ICONS[ranoClass];
  return (
    <span
      className={`inline-flex items-center font-semibold rounded border ${s.pad} ${s.gap} ${s.text} ${className}`}
      style={{ backgroundColor: c.bg, color: c.color, borderColor: c.border }}
    >
      <Icon size={s.iconPx} />
      {LABELS[ranoClass]}
    </span>
  );
}