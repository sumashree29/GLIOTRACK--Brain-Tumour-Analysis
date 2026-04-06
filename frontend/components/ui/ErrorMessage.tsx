"use client";

import React from "react";
import { AlertOctagon, RefreshCw } from "lucide-react";

interface ErrorMessageProps {
  title?:    string;
  message:   string;
  onRetry?:  () => void;
  inline?:   boolean;
  className?: string;
}

export default function ErrorMessage({
  title    = "Something went wrong",
  message,
  onRetry,
  inline   = false,
  className = "",
}: ErrorMessageProps) {
  if (inline) {
    return (
      <div
        className={`flex items-start gap-3 px-4 py-3 rounded-lg border ${className}`}
        style={{ backgroundColor: "var(--red-dim)", borderColor: "var(--red)" }}
        role="alert"
      >
        <AlertOctagon size={15} className="mt-0.5 shrink-0" style={{ color: "var(--red)" }} />
        <div className="min-w-0">
          <p className="text-sm font-semibold" style={{ color: "var(--red)" }}>{title}</p>
          <p className="text-xs mt-0.5 leading-relaxed" style={{ color: "var(--red)", opacity: 0.8 }}>{message}</p>
        </div>
        {onRetry && (
          <button onClick={onRetry} className="ml-auto shrink-0 transition-colors" style={{ color: "var(--red)" }} aria-label="Retry">
            <RefreshCw size={14} />
          </button>
        )}
      </div>
    );
  }

  return (
    <div className={`flex flex-col items-center justify-center gap-5 py-16 px-8 text-center ${className}`} role="alert">
      <div className="flex h-14 w-14 items-center justify-center rounded-full border" style={{ backgroundColor: "var(--red-dim)", borderColor: "var(--red)" }}>
        <AlertOctagon size={24} style={{ color: "var(--red)" }} />
      </div>
      <div className="space-y-1.5 max-w-sm">
        <p className="text-sm font-semibold" style={{ color: "var(--text)" }}>{title}</p>
        <p className="text-sm leading-relaxed" style={{ color: "var(--muted)" }}>{message}</p>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border text-sm font-medium transition-colors duration-150"
          style={{ borderColor: "var(--border)", backgroundColor: "var(--surface-2)", color: "var(--text)" }}
        >
          <RefreshCw size={13} />
          Try again
        </button>
      )}
    </div>
  );
}