# GLIOTRACK Frontend

**CT-Based Tumour Analysis — Clinical Dashboard**

Next.js 14 frontend for the Constrained Autonomous Multi-Agent Framework for Longitudinal Brain Tumour Analysis.

---

## Quick start

```bash
# 1. Install dependencies (exact versions pinned in package.json)
npm install

# 2. Configure environment
cp .env.example .env.local
# Edit .env.local and set NEXT_PUBLIC_API_BASE to your Render URL

# 3. Run development server
npm run dev
# → http://localhost:3000
```

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `NEXT_PUBLIC_API_BASE` | ✅ | Full URL of your Render FastAPI backend. No trailing slash. |

> All API calls go **directly** to `NEXT_PUBLIC_API_BASE`. There is no Next.js API route proxy. The Render backend handles CORS headers.

---

## Tech stack (exact pinned versions)

| Package | Version |
|---|---|
| next | 14.2.3 |
| react | 18.3.1 |
| typescript | 5.4.5 |
| tailwindcss | 3.4.1 |
| axios | 1.6.8 |
| recharts | 2.12.3 |
| lucide-react | 0.383.0 |
| jszip | 3.10.1 |
| jwt-decode | 4.0.0 |
| date-fns | 3.6.0 |

---

## Project structure

```
gliotrack-frontend/
├── app/                          # Next.js 14 App Router pages
│   ├── login/                    # /login
│   ├── register/                 # /register
│   ├── dashboard/                # /dashboard
│   ├── patients/                 # /patients
│   │   └── [patient_id]/         # /patients/:id
│   ├── upload/
│   │   └── [patient_id]/         # /upload/:id  — 3-step wizard
│   ├── status/
│   │   └── [scan_id]/            # /status/:id  — live pipeline
│   ├── scans/
│   │   └── [scan_id]/report/     # /scans/:id/report
│   ├── longitudinal/
│   │   └── [patient_id]/         # /longitudinal/:id — charts
│   └── admin/                    # /admin — admin role only
│
├── components/
│   ├── layout/                   # Sidebar, TopBar, DashboardLayout, AuthGuard
│   ├── ui/                       # StatusBadge, RANOBadge, ClinicalFlag,
│   │                             # SkeletonLoader, ErrorMessage
│   ├── patients/                 # PatientTable, ScanHistoryList
│   ├── reports/                  # MeasurementsTable, RAGPassages
│   ├── charts/                   # LongitudinalChart, RANOTimeline
│   └── upload/                   # SequenceDropzone, SequenceChecklist
│
├── lib/
│   ├── api.ts                    # Axios instance + all API functions
│   ├── auth.ts                   # JWT decode, cookie helpers, role checks
│   ├── constants.ts              # POLL_INTERVAL_MS, POLL_MAX, STATUS_MAP,
│   │                             # RANO_COLOURS, FLAG_MESSAGES
│   └── polling.ts                # Pure polling engine (no React)
│
├── hooks/
│   └── usePolling.ts             # React hook wrapping polling engine
│
└── types/
    └── index.ts                  # All TypeScript interfaces
```

---

## Pages overview

| Route | Description |
|---|---|
| `/login` | Email + password login. Routes to `/admin` or `/dashboard` by role. |
| `/register` | New account creation. All accounts receive the `doctor` role. |
| `/dashboard` | Stat cards + recent scans table + quick actions. |
| `/patients` | Searchable patient list. Create patient modal. |
| `/patients/:id` | Patient detail: info cards + scan history + upload button. |
| `/upload/:id` | 3-step wizard: date → upload 4 sequences → review + launch. |
| `/status/:id` | Live pipeline status. Polls every 15s, max 80 attempts (20 min). |
| `/scans/:id/report` | Full clinical report: 8 sections in spec order, all flags, PDF download. |
| `/longitudinal/:id` | ET volume + bidimensional product charts, RANO timeline, data table. |
| `/admin` | Admin only. System health card + user management note. |

---

## Auth

- JWT stored in a **browser cookie** (`gliotrack_token`). Never in `localStorage`.
- All outgoing requests have `Authorization: Bearer <token>` attached by the Axios interceptor.
- `401` responses automatically clear the session and redirect to `/login`.
- `AuthGuard` wraps every protected page and checks token expiry on mount.
- Admin role is **set in the database directly** — the UI never exposes a way to change roles.

---

## Upload flow

```
Step 1  POST /scans               → get scan_id
Step 2  POST /scans/:id/files × 4  → upload T1, T1ce, T2, FLAIR separately
        (each DICOM folder is zipped client-side by JSZip before upload)
Step 3  POST /scans/:id/run        → start the pipeline
        → redirect to /status/:id
```

Per-file size warning fires at **500 MB** (from `MAX_FILE_SIZE_BYTES` in `lib/constants.ts`).

---

## Polling constants (locked)

These values are defined **once** in `lib/constants.ts` and imported everywhere. Never hardcode them inline.

```ts
POLL_INTERVAL_MS = 15000  // 15 seconds between polls
POLL_MAX         = 80     // 80 attempts = 20 minute hard timeout
```

---

## Clinical flags

All flag messages are defined in `lib/constants.ts → FLAG_MESSAGES` and use the **exact text from the clinical specification**. Never paraphrase them.

| Flag | Variant | Trigger |
|---|---|---|
| `lowConfidence` | warning | `agent1.low_confidence_flag = true` |
| `crProvisional` | info | `rano_class = "CR_provisional"` |
| `crConfirmed` | success | `rano_class = "CR_confirmed"` |
| `pd` | error | `rano_class = "PD"` |
| `dissociation` | warning | `agent3.dissociation_flag = true` |
| `ragUnavailable` | warning | `agent4.rag_available = false` or null |
| `disclaimer` | warning | Always visible on every report and upload page |

---

## Build for production

```bash
npm run build
npm run start
```

Or deploy to Vercel:

```bash
npx vercel
# Set NEXT_PUBLIC_API_BASE in the Vercel dashboard
```

---

## Type check

```bash
npm run type-check
```

---

> **Clinical decision support only. Not for use without qualified clinician review.**
