"use client";

import React, { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { format, parseISO } from "date-fns";
import { Search, ChevronRight, UserCircle2, Archive, Loader2 } from "lucide-react";
import type { PatientRecord } from "@/types";

interface Props {
  patients:        PatientRecord[];
  scanCounts:      Record<string, number>;
  lastScans:       Record<string, string>;
  onArchive?:      (patient_id: string) => void;
  archiveLoading?: string | null;
}

export default function PatientTable({ patients, scanCounts, lastScans, onArchive, archiveLoading }: Props) {
  const router  = useRouter();
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? patients.filter((p) => p.patient_id.toLowerCase().includes(q)) : patients;
  }, [patients, query]);

  return (
    <div className="rounded-xl border overflow-hidden" style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}>

      {/* Search */}
      <div className="px-4 py-3 border-b" style={{ borderColor: "var(--border)" }}>
        <div className="relative">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: "var(--muted)" }} />
          <input
            type="search" value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by patient ID…"
            className="w-full pl-8 pr-4 py-2 rounded-lg text-[13px] border focus:outline-none transition-colors duration-150"
            style={{ backgroundColor: "var(--bg)", borderColor: "var(--border)", color: "var(--text)" }}
          />
        </div>
      </div>

      {/* Table */}
      <table className="w-full">
        <thead>
          <tr className="border-b" style={{ borderColor: "var(--border)", backgroundColor: "var(--surface-2)" }}>
            {["Patient ID", "Registered", "Last scan", "Scans", "", ""].map((h, i) => (
              <th key={i} className="px-4 py-2.5 text-left text-[10px] font-semibold uppercase tracking-wider" style={{ color: "var(--muted)" }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>

        <tbody>
          {filtered.length === 0 ? (
            <tr>
              <td colSpan={6} className="px-4 py-14 text-center">
                <p className="text-sm" style={{ color: "var(--muted)" }}>
                  {query ? `No patients matching "${query}"` : "No patients yet"}
                </p>
                {!query && <p className="text-[11px] mt-1" style={{ color: "var(--muted)", opacity: 0.6 }}>Register a patient to get started</p>}
              </td>
            </tr>
          ) : (
            filtered.map((p) => (
              <tr
                key={p.patient_id}
                className="border-b last:border-0 transition-colors duration-150"
                style={{ borderColor: "var(--border)" }}
                onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "var(--surface-2)")}
                onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
              >
                {/* Patient ID */}
                <td className="px-4 py-3 cursor-pointer" onClick={() => router.push(`/patients/${p.patient_id}`)}>
                  <div className="flex items-center gap-2.5">
                    <div className="flex h-7 w-7 items-center justify-center rounded-full shrink-0" style={{ backgroundColor: "var(--surface-2)", color: "var(--muted)" }}>
                      <UserCircle2 size={14} />
                    </div>
                    <span className="text-[13px] font-mono font-medium" style={{ color: "var(--text)" }}>{p.patient_id}</span>
                  </div>
                </td>

                {/* Registered */}
                <td className="px-4 py-3 cursor-pointer" onClick={() => router.push(`/patients/${p.patient_id}`)}>
                  <span className="text-[12px]" style={{ color: "var(--muted)" }}>
                    {p.created_at ? format(parseISO(p.created_at), "dd MMM yyyy") : "—"}
                  </span>
                </td>

                {/* Last scan */}
                <td className="px-4 py-3 cursor-pointer" onClick={() => router.push(`/patients/${p.patient_id}`)}>
                  <span className="text-[12px]" style={{ color: "var(--muted)" }}>
                    {lastScans[p.patient_id] ? format(parseISO(lastScans[p.patient_id]), "dd MMM yyyy") : "—"}
                  </span>
                </td>

                {/* Scan count */}
                <td className="px-4 py-3 cursor-pointer" onClick={() => router.push(`/patients/${p.patient_id}`)}>
                  <span
                    className="inline-flex items-center justify-center h-5 min-w-[20px] px-1.5 rounded text-[11px] font-semibold font-mono"
                    style={{ backgroundColor: "var(--surface-2)", color: "var(--muted)" }}
                  >
                    {scanCounts[p.patient_id] ?? 0}
                  </span>
                </td>

                {/* Archive */}
                <td className="px-4 py-3">
                  {onArchive && (
                    <button
                      onClick={(e) => { e.stopPropagation(); onArchive(p.patient_id); }}
                      disabled={archiveLoading === p.patient_id}
                      title="Archive patient"
                      className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-medium border transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed"
                      style={{ borderColor: "var(--red)", color: "var(--red)", backgroundColor: "transparent" }}
                    >
                      {archiveLoading === p.patient_id ? <Loader2 size={11} className="animate-spin" /> : <Archive size={11} />}
                      {archiveLoading === p.patient_id ? "Archiving…" : "Archive"}
                    </button>
                  )}
                </td>

                {/* Arrow */}
                <td className="px-4 py-3 text-right cursor-pointer" onClick={() => router.push(`/patients/${p.patient_id}`)}>
                  <ChevronRight size={14} style={{ color: "var(--muted)" }} className="inline" />
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}