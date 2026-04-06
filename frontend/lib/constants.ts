// ─────────────────────────────────────────────────────────────────────────────
// GLIOTRACK — Application constants
//
// POLLING VALUES ARE LOCKED PER SPEC — never override inline anywhere.
// Always import POLL_INTERVAL_MS and POLL_MAX from this file.
// ─────────────────────────────────────────────────────────────────────────────

import type { ScanStatus, RANOClass } from "@/types";

// ── Polling — LOCKED ──────────────────────────────────────────────────────────
export const POLL_INTERVAL_MS = 15000; // 15 seconds — do not change
export const POLL_MAX         = 80;    // 80 attempts = 20 min hard timeout

// ── Pipeline status → display label + progress % ─────────────────────────────
export const STATUS_MAP: Record<ScanStatus, { label: string; progress: number }> = {
  PENDING:                { label: "Queued",                   progress: 2   },
  SEGMENTATION_RUNNING:   { label: "Segmenting tumour...",     progress: 20  },
  SEGMENTATION_COMPLETE:  { label: "Segmentation complete",    progress: 35  },
  RANO_RUNNING:           { label: "Classifying (RANO)...",    progress: 45  },
  RANO_COMPLETE:          { label: "RANO classification done", progress: 55  },
  LONGITUDINAL_RUNNING:   { label: "Longitudinal analysis...", progress: 65  },
  LONGITUDINAL_COMPLETE:  { label: "Longitudinal done",        progress: 72  },
  RAG_RUNNING:            { label: "Querying guidelines...",   progress: 80  },
  RAG_COMPLETE:           { label: "Guidelines retrieved",     progress: 87  },
  REPORT_RUNNING:         { label: "Generating report...",     progress: 93  },
  REPORT_READY:           { label: "Report ready",             progress: 100 },
  FAILED:                 { label: "Pipeline failed",          progress: 0   },
  failed_timeout:         { label: "Timed out after 20 min",  progress: 0   },
};

// Statuses that are still running (used to decide whether to keep polling)
export const RUNNING_STATUSES: ScanStatus[] = [
  "PENDING",
  "SEGMENTATION_RUNNING",
  "SEGMENTATION_COMPLETE",
  "RANO_RUNNING",
  "RANO_COMPLETE",
  "LONGITUDINAL_RUNNING",
  "LONGITUDINAL_COMPLETE",
  "RAG_RUNNING",
  "RAG_COMPLETE",
  "REPORT_RUNNING",
];

export const TERMINAL_STATUSES: ScanStatus[] = [
  "REPORT_READY",
  "FAILED",
  "failed_timeout",
];

// ── RANO class → badge colours ────────────────────────────────────────────────
export const RANO_COLOURS: Record<
  RANOClass,
  { bg: string; text: string; border: string }
> = {
  CR_confirmed:  { bg: "#1a4a1f", text: "#3fb950", border: "#3fb950" },
  CR_provisional:{ bg: "#1a2e4a", text: "#2f81f7", border: "#2f81f7" },
  PR:            { bg: "#1a4a1f", text: "#3fb950", border: "#3fb950" },
  SD:            { bg: "#3d2e00", text: "#d29922", border: "#d29922" },
  PD:            { bg: "#4a1a1a", text: "#f85149", border: "#f85149" },
};

export const RANO_LABELS: Record<RANOClass, string> = {
  CR_confirmed:  "Complete Response — Confirmed",
  CR_provisional:"Complete Response — Provisional",
  PR:            "Partial Response",
  SD:            "Stable Disease",
  PD:            "Progressive Disease",
};

// ── Clinical flag messages — exact text per spec, never paraphrase ────────────
export const FLAG_MESSAGES = {
  lowConfidence:
    "Segmentation confidence is low. Manual review is strongly recommended.",

  crProvisional:
    "Complete Response is provisional. Confirmation scan required in ≥4 weeks.",

  crConfirmed:
    "Complete Response confirmed. No measurable enhancing " +
    "tumour detected. Confirmation scan required ≥4 weeks " +
    "after initial CR scan.",

  pd:
    "Progressive Disease detected. ≥25% increase in " +
    "bidimensional product compared to nadir, or new lesion " +
    "identified. Immediate clinical review required.",

  dissociation:
    "Tumour sub-region dissociation detected. May indicate radiation necrosis.",

  ragUnavailable:
    "Clinical literature context unavailable for this report. RAG service was unreachable or returned no results. Clinical decisions should not rely on this section.",

  disclaimer:
    "Clinical decision support only. Not for use without qualified clinician review.",
} as const;

// ── Upload ────────────────────────────────────────────────────────────────────
export const SEQUENCES = ["T1", "T1ce", "T2", "FLAIR"] as const;
export type   Sequence  = (typeof SEQUENCES)[number];

/** Per-file size warning threshold: 500 MB */
export const MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024;

// ── Design tokens (mirrors tailwind config for use in JS/inline styles) ───────
export const COLOURS = {
  background:      "#0d1117",
  surface:         "#161b22",
  surfaceElevated: "#21262d",
  border:          "#30363d",
  accentBlue:      "#2f81f7",
  successGreen:    "#3fb950",
  warningAmber:    "#d29922",
  errorRed:        "#f85149",
  textPrimary:     "#e6edf3",
  textMuted:       "#8b949e",
} as const;
