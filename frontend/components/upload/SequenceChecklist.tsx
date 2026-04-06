"use client";

import React from "react";
import { CheckCircle2, Circle, AlertTriangle } from "lucide-react";
import { SEQUENCES, type Sequence } from "@/lib/constants";
import type { SequenceFile } from "./SequenceDropzone";

interface Props { files: Partial<Record<Sequence, SequenceFile | null>>; }

export default function SequenceChecklist({ files }: Props) {
  const allReady   = SEQUENCES.every((seq) => files[seq] && !files[seq]!.oversized);
  const readyCount = SEQUENCES.filter((seq) => files[seq] && !files[seq]!.oversized).length;

  return (
    <div className="rounded-xl border p-4" style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}>
      <div className="flex items-center justify-between mb-3">
        <p className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--muted)" }}>Sequence checklist</p>
        <span
          className="text-[11px] font-bold font-mono px-2 py-0.5 rounded border"
          style={{
            backgroundColor: allReady ? "var(--green-dim)" : "var(--surface-2)",
            color:           allReady ? "var(--green)"     : "var(--muted)",
            borderColor:     allReady ? "var(--green)"     : "var(--border)",
          }}
        >
          {readyCount}/{SEQUENCES.length}
        </span>
      </div>

      <div className="space-y-2">
        {SEQUENCES.map((seq) => {
          const file    = files[seq];
          const isReady = !!file && !file.oversized;
          const isOver  = !!file && file.oversized;
          const color   = isReady ? "var(--green)" : isOver ? "var(--red)" : "var(--muted)";
          return (
            <div key={seq} className="flex items-center gap-2.5">
              {isReady ? <CheckCircle2 size={14} className="shrink-0" style={{ color: "var(--green)" }} />
               : isOver ? <AlertTriangle size={14} className="shrink-0" style={{ color: "var(--red)" }} />
               : <Circle size={14} className="shrink-0" style={{ color: "var(--border)" }} />}
              <span className="text-[11px] font-bold font-mono uppercase tracking-wider" style={{ color }}>{seq}</span>
              <span className="text-[10px] ml-auto" style={{ color: "var(--muted)" }}>
                {isReady ? `${(file!.sizeBytes / 1024 / 1024).toFixed(1)} MB`
                 : isOver ? "Too large"
                 : "Not uploaded"}
              </span>
            </div>
          );
        })}
      </div>

      <div className="mt-3 pt-3 border-t text-[11px] font-medium" style={{ borderColor: "var(--border)", color: allReady ? "var(--green)" : "var(--muted)" }}>
        {allReady ? "All 4 sequences ready — you can run the pipeline" : `${4 - readyCount} sequence${4 - readyCount !== 1 ? "s" : ""} still needed`}
      </div>
    </div>
  );
}