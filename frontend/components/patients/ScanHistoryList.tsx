"use client";

import React from "react";
import Link from "next/link";
import { format, parseISO } from "date-fns";
import { FileText, Trash2, Loader2, AlertCircle, Clock, CheckCircle2 } from "lucide-react";
import type { ScanRecord } from "@/types";

interface Props {
  scans: ScanRecord[];
  onDeleteScan?: (scan_id: string) => Promise<void>;
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; color: string; bg: string }> = {
    REPORT_READY:          { label: "Ready",      color: "var(--green)", bg: "var(--green-dim)" },
    FAILED:                { label: "Failed",      color: "var(--red)",   bg: "var(--red-dim)"   },
    failed_timeout:        { label: "Timeout",     color: "var(--red)",   bg: "var(--red-dim)"   },
    SEGMENTATION_RUNNING:  { label: "Running",     color: "var(--blue)",  bg: "var(--blue-dim)"  },
    SEGMENTATION_COMPLETE: { label: "Segmented",   color: "var(--blue)",  bg: "var(--blue-dim)"  },
    RANO_RUNNING:          { label: "RANO…",       color: "var(--blue)",  bg: "var(--blue-dim)"  },
    RANO_COMPLETE:         { label: "RANO done",   color: "var(--blue)",  bg: "var(--blue-dim)"  },
    REPORT_RUNNING:        { label: "Reporting…",  color: "var(--amber)", bg: "var(--amber-dim)" },
    PENDING:               { label: "Pending",     color: "var(--muted)", bg: "var(--surface-2)" },
  };
  const s = map[status] ?? { label: status, color: "var(--muted)", bg: "var(--surface-2)" };
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider"
      style={{ color: s.color, backgroundColor: s.bg }}
    >
      {s.label}
    </span>
  );
}

export default function ScanHistoryList({ scans, onDeleteScan }: Props) {
  const [deleting, setDeleting] = React.useState<string | null>(null);

  if (!scans.length) {
    return (
      <div
        className="rounded-xl p-8 text-center"
        style={{ border: "1px solid var(--border)", backgroundColor: "var(--surface)" }}
      >
        <p className="text-[13px]" style={{ color: "var(--muted)" }}>No scans uploaded yet.</p>
      </div>
    );
  }

  const sorted = [...scans].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );

  async function handleDelete(scan_id: string) {
    if (!onDeleteScan) return;
    setDeleting(scan_id);
    await onDeleteScan(scan_id);
    setDeleting(null);
  }

  return (
    <div className="rounded-xl overflow-hidden" style={{ border: "1px solid var(--border)", backgroundColor: "var(--surface)" }}>
      <table className="w-full">
        <thead>
          <tr style={{ borderBottom: "1px solid var(--border)", backgroundColor: "var(--surface-2)" }}>
            {["Scan date", "Status", "Created", "Actions"].map((h) => (
              <th key={h} className="px-4 py-2.5 text-left text-[10px] font-semibold uppercase tracking-wider" style={{ color: "var(--muted)" }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((scan) => {
            const isFailed = scan.status === "FAILED" || scan.status === "failed_timeout";
            const isReady  = scan.status === "REPORT_READY";
            const isDeleting = deleting === scan.scan_id;

            return (
              <tr
                key={scan.scan_id}
                className="transition-colors duration-100"
                style={{ borderBottom: "1px solid var(--border)" }}
                onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "var(--surface-2)")}
                onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
              >
                {/* Date */}
                <td className="px-4 py-3">
                  <span className="text-[12px] font-mono font-semibold" style={{ color: "var(--text)" }}>
                    {format(parseISO(scan.scan_date), "dd MMM yyyy")}
                  </span>
                  <p className="text-[10px] font-mono mt-0.5" style={{ color: "var(--muted)" }}>
                    {scan.scan_id.slice(0, 8)}…
                  </p>
                </td>

                {/* Status */}
                <td className="px-4 py-3">
                  <StatusBadge status={scan.status} />
                  {scan.failed_stage && (
                    <p className="text-[10px] mt-1 flex items-center gap-1" style={{ color: "var(--red)" }}>
                      <AlertCircle size={9} /> {scan.failed_stage}
                    </p>
                  )}
                </td>

                {/* Created */}
                <td className="px-4 py-3">
                  <span className="text-[11px]" style={{ color: "var(--muted)" }}>
                    {format(parseISO(scan.created_at), "dd MMM yy, HH:mm")}
                  </span>
                </td>

                {/* Actions */}
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    {isReady && (
                      <Link
                        href={`/scans/${scan.scan_id}/report`}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-medium transition-colors duration-150"
                        style={{ color: "var(--blue)", backgroundColor: "var(--blue-dim)", border: "1px solid var(--blue)" }}
                      >
                        <FileText size={11} />
                        Report
                      </Link>
                    )}

                    {!isReady && !isFailed && (
                      <span className="inline-flex items-center gap-1.5 text-[11px]" style={{ color: "var(--muted)" }}>
                        <Clock size={11} />
                        In progress
                      </span>
                    )}

                    {onDeleteScan && (
                      <button
                        onClick={() => handleDelete(scan.scan_id)}
                        disabled={isDeleting}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-medium transition-colors duration-150"
                        style={{ color: "var(--red)", backgroundColor: "var(--red-dim)", border: "1px solid var(--red)" }}
                      >
                        {isDeleting
                          ? <><Loader2 size={11} className="animate-spin" /> Deleting…</>
                          : <><Trash2 size={11} /> Delete</>}
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}