"use client";

import React, { useState } from "react";
import { BookOpen, ChevronDown, ChevronUp, AlertTriangle, FileText } from "lucide-react";
import ClinicalFlag from "@/components/ui/ClinicalFlag";
import { FLAG_MESSAGES } from "@/lib/constants";
import type { Agent4Output, RAGPassage } from "@/types";

// ── Types ─────────────────────────────────────────────────────────────────────
// RAGPassage extended with backend-generated bullets
interface EnrichedPassage extends RAGPassage {
  bullets?: string[];
}

// ── Raw passage text with expand toggle ───────────────────────────────────────
function RawPassage({ text }: { text: string }) {
  const [showFull, setShowFull] = useState(false);
  const preview = text.slice(0, 300).trim();
  const hasMore = text.length > 300;

  return (
    <div>
      <div className="flex items-center gap-1.5 mb-2">
        <FileText size={11} style={{ color: "var(--muted)" }} />
        <p
          className="text-[10px] font-semibold uppercase tracking-wider"
          style={{ color: "var(--muted)" }}
        >
          Source passage
        </p>
      </div>
      <p
        className="text-[11px] leading-relaxed"
        style={{ color: "var(--muted)" }}
      >
        {showFull ? text : preview}
        {!showFull && hasMore && "…"}
      </p>
      {hasMore && (
        <button
          onClick={() => setShowFull(v => !v)}
          className="mt-1.5 text-[10px] font-semibold"
          style={{ color: "var(--blue)" }}
        >
          {showFull ? "Show less" : "Read full passage"}
        </button>
      )}
    </div>
  );
}

// ── Single passage card ───────────────────────────────────────────────────────
function PassageCard({ passage, index }: { passage: EnrichedPassage; index: number }) {
  const [expanded, setExpanded] = useState(false);

  const scoreColor =
    passage.relevance_score >= 0.8 ? "var(--green)" :
    passage.relevance_score >= 0.6 ? "var(--amber)" :
    "var(--muted)";

  const bullets = passage.bullets ?? [];

  return (
    <div
      className="rounded-lg border overflow-hidden"
      style={{ borderColor: "var(--border)", backgroundColor: "var(--surface-2)" }}
    >
      {/* ── Header ── */}
      <button
        onClick={() => setExpanded(v => !v)}
        className="w-full flex items-start justify-between gap-3 p-4 text-left transition-colors duration-150"
        style={{ backgroundColor: "transparent" }}
        onMouseEnter={e => (e.currentTarget.style.backgroundColor = "var(--surface)")}
        onMouseLeave={e => (e.currentTarget.style.backgroundColor = "transparent")}
      >
        <div className="flex items-start gap-3 min-w-0">
          {/* Index badge */}
          <div
            className="flex h-6 w-6 items-center justify-center rounded text-[10px] font-bold font-mono shrink-0 mt-0.5"
            style={{ backgroundColor: "var(--surface)", color: "var(--muted)" }}
          >
            {index + 1}
          </div>

          <div className="min-w-0">
            <p
              className="text-[12px] font-semibold truncate"
              style={{ color: "var(--text)" }}
            >
              {passage.source_document}
            </p>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-[10px] font-mono" style={{ color: "var(--muted)" }}>
                {passage.guideline_version}
              </span>
              <span style={{ color: "var(--border)" }}>·</span>
              <span className="text-[10px]" style={{ color: "var(--muted)" }}>
                {passage.publication_year}
              </span>
              <span style={{ color: "var(--border)" }}>·</span>
              <span
                className="text-[10px] font-semibold font-mono"
                style={{ color: scoreColor }}
              >
                {Math.round(passage.relevance_score * 100)}% relevant
              </span>
            </div>

            {/* Bullet preview — show first bullet collapsed */}
            {!expanded && bullets.length > 0 && (
              <p
                className="text-[11px] mt-1.5 leading-relaxed line-clamp-2"
                style={{ color: "var(--text)" }}
              >
                • {bullets[0]}
              </p>
            )}
          </div>
        </div>

        <span className="shrink-0 mt-0.5" style={{ color: "var(--muted)" }}>
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </span>
      </button>

      {/* ── Expanded content ── */}
      {expanded && (
        <div
          className="px-4 pb-4 pt-0 border-t"
          style={{ borderColor: "var(--border)" }}
        >
          {/* Key clinical bullets */}
          {bullets.length > 0 && (
            <div className="mt-3 mb-4">
              <div className="flex items-center gap-1.5 mb-2">
                <BookOpen size={11} style={{ color: "var(--blue)" }} />
                <p
                  className="text-[10px] font-semibold uppercase tracking-wider"
                  style={{ color: "var(--blue)" }}
                >
                  Key clinical points
                </p>
              </div>
              <ul className="space-y-2">
                {bullets.map((b, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span
                      className="text-[10px] font-bold mt-0.5 shrink-0"
                      style={{ color: "var(--blue)" }}
                    >
                      •
                    </span>
                    <span
                      className="text-[11px] leading-relaxed"
                      style={{ color: "var(--text)" }}
                    >
                      {b}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Divider between bullets and raw text */}
          {bullets.length > 0 && (
            <div className="h-px my-3" style={{ backgroundColor: "var(--border)" }} />
          )}

          {/* Raw source passage */}
          <RawPassage text={passage.passage_text} />
        </div>
      )}
    </div>
  );
}

// ── Main export ───────────────────────────────────────────────────────────────
export default function RAGPassages({ agent4 }: { agent4: Agent4Output | null }) {
  if (!agent4 || !agent4.rag_available || agent4.passages.length === 0) {
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <AlertTriangle size={14} style={{ color: "var(--amber)" }} />
          <p
            className="text-[11px] font-semibold uppercase tracking-wider"
            style={{ color: "var(--muted)" }}
          >
            Clinical Literature Context
          </p>
        </div>
        <ClinicalFlag variant="warning" message={FLAG_MESSAGES.ragUnavailable} />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BookOpen size={14} style={{ color: "var(--blue)" }} />
          <p
            className="text-[11px] font-semibold uppercase tracking-wider"
            style={{ color: "var(--muted)" }}
          >
            Clinical Literature Context
          </p>
        </div>
        <span
          className="text-[10px] font-semibold font-mono px-2 py-0.5 rounded border"
          style={{
            backgroundColor: "var(--blue-dim)",
            color: "var(--blue)",
            borderColor: "var(--blue)",
          }}
        >
          {agent4.passages.length} passage{agent4.passages.length !== 1 ? "s" : ""}
        </span>
      </div>

      <p className="text-[11px] leading-relaxed px-0.5" style={{ color: "var(--muted)" }}>
        Retrieved from indexed clinical guidelines based on this scan's clinical profile.
        Expand each passage to see key clinical points and the full source text.
        Context only — does not replace clinical judgement.
      </p>

      <div className="space-y-2">
        {(agent4.passages as EnrichedPassage[]).map((p, i) => (
          <PassageCard key={i} passage={p} index={i} />
        ))}
      </div>
    </div>
  );
}
