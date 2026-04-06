"use client";

import React from "react";
import { AlertTriangle, Info, CheckCircle2, XCircle } from "lucide-react";

export type FlagVariant = "warning" | "info" | "success" | "error";

interface Props {
  variant: FlagVariant; message: string; compact?: boolean; className?: string;
}

const STYLES: Record<FlagVariant, { bg: string; border: string; color: string; Icon: React.ElementType }> = {
  warning: { bg: "var(--amber-dim)", border: "var(--amber)", color: "var(--amber)", Icon: AlertTriangle },
  info:    { bg: "var(--blue-dim)",  border: "var(--blue)",  color: "var(--blue)",  Icon: Info          },
  success: { bg: "var(--green-dim)", border: "var(--green)", color: "var(--green)", Icon: CheckCircle2  },
  error:   { bg: "var(--red-dim)",   border: "var(--red)",   color: "var(--red)",   Icon: XCircle       },
};

export default function ClinicalFlag({ variant, message, compact = false, className = "" }: Props) {
  const { bg, border, color, Icon } = STYLES[variant];
  return (
    <div
      role="alert"
      className={`flex items-start gap-3 rounded-lg border ${compact ? "px-3 py-2" : "px-4 py-3"} ${className}`}
      style={{ backgroundColor: bg, borderColor: border, color }}
    >
      <Icon size={compact ? 13 : 15} className="mt-0.5 shrink-0" />
      <span className={`${compact ? "text-xs" : "text-sm"} font-medium leading-snug`}>{message}</span>
    </div>
  );
}