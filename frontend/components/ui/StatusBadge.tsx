"use client";

import React from "react";
import { Loader2, CheckCircle2, XCircle, Clock, Hourglass } from "lucide-react";
import type { ScanStatus } from "@/types";
import { STATUS_MAP } from "@/lib/constants";

function getStyle(status: ScanStatus) {
  switch (status) {
    case "REPORT_READY":    return { bg: "var(--green-dim)", text: "var(--green)", border: "var(--green)" };
    case "FAILED":
    case "failed_timeout":  return { bg: "var(--red-dim)",   text: "var(--red)",   border: "var(--red)"   };
    case "PENDING":         return { bg: "var(--surface-2)", text: "var(--muted)", border: "var(--border)" };
    case "REPORT_RUNNING":  return { bg: "var(--amber-dim)", text: "var(--amber)", border: "var(--amber)" };
    default:                return { bg: "var(--blue-dim)",  text: "var(--blue)",  border: "var(--blue)"  };
  }
}

function StatusIcon({ status, size = 11 }: { status: ScanStatus; size?: number }) {
  if (status === "REPORT_READY")              return <CheckCircle2 size={size} />;
  if (status === "FAILED" || status === "failed_timeout") return <XCircle size={size} />;
  if (status === "PENDING")                   return <Clock size={size} />;
  if (status === "REPORT_RUNNING")            return <Hourglass size={size} />;
  return <Loader2 size={size} className="animate-spin" />;
}

export default function StatusBadge({ status, className = "" }: { status: ScanStatus; className?: string }) {
  const style     = getStyle(status);
  const { label } = STATUS_MAP[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded text-[11px] font-semibold border select-none whitespace-nowrap ${className}`}
      style={{ backgroundColor: style.bg, color: style.text, borderColor: style.border }}
    >
      <StatusIcon status={status} />
      {label}
    </span>
  );
}