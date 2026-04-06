# Brain Tumour Response Assessment System

**Constrained Autonomous Multi-Agent Framework for Longitudinal Brain Tumour Analysis**
Academic prototype — zero-budget stack — NOT for clinical use without expert review.

## Architecture

```
Browser (upload.js)
    |
    v
FastAPI (Render.com)
    |
    |-- Agent 1: nnU-Net Segmentation (Modal GPU, A10G)
    |-- Agent 2: RANO 2010 Classification
    |-- Agent 3: Longitudinal Analysis
    |-- Agent 4: Clinical RAG (Qdrant + BAAI/bge-small-en-v1.5)
    |-- Agent 5: Report Generation (Groq llama-3.3-70b-versatile + ReportLab PDF)
    |
    v
Supabase (metadata DB) + Cloudflare R2 (DICOM files + PDF reports)
```

## Stack (all free/low-cost tiers)

| Service | Purpose | Cost |
|---------|---------|------|
| Modal.com | GPU segmentation (A10G) | $30/mo credit |
| Render.com | FastAPI backend | Free tier |
| Supabase | PostgreSQL metadata | Free tier |
| Cloudflare R2 | File storage | Free 10GB |
| Qdrant Cloud | Vector DB for RAG | Free 1GB |
| Groq | LLM (llama-3.3-70b-versatile) | Free tier |

---

## Setup (step-by-step)

### 1. Clone and install

```bash
git clone <your-repo>
cd brain-tumour-system
pip install -r requirements.txt
cp .env.example .env
# Fill in all values in .env
```

### 2. Supabase setup

1. Create a project at https://supabase.com
2. Open SQL Editor → paste contents of `scripts/supabase_schema.sql` → Run
3. Copy Project URL and Service Role Key into `.env`

### 3. Cloudflare R2 setup

1. Create account at https://cloudflare.com
2. Storage → R2 → Create bucket named `brain-tumour-scans`
3. Manage R2 API tokens → Create token with Read/Write
4. Copy endpoint URL, Access Key ID, Secret into `.env`

### 4. Qdrant Cloud setup

1. Create free cluster at https://cloud.qdrant.io
2. Copy cluster URL and API key into `.env`

### 5. Groq API key

1. Sign up at https://console.groq.com
2. Create API key → copy into `.env` as `GROQ_API_KEY`

### 6. Modal setup

```bash
pip install modal
modal setup                           # authenticate
python scripts/setup_modal_volumes.py # create volume
python modal_workers/deploy.py        # deploy worker
# Copy the printed webhook URL into MODAL_WEBHOOK_URL in .env
```

Upload nnU-Net BraTS weights to the Modal volume:
```bash
modal volume put nnunet-weights /local/path/to/Dataset001_BraTS /weights/Dataset001_BraTS
```

### 7. Ingest clinical guidelines (RAG)

Place PDF/TXT guideline files in a directory, then:
```bash
python scripts/ingest_knowledge_base.py \
    --docs-dir /path/to/guidelines \
    --map '{"RANO_2010.pdf": ["RANO 2010", 2010], "iRANO_2015.pdf": ["iRANO 2015", 2015]}'
```

### 8. Run backend locally

```bash
uvicorn app.main:app --reload --port 8000
# API docs: http://localhost:8000/docs
```

### 9. Run validation (no credentials needed for unit tests)

```bash
python scripts/validate_pipeline.py --unit-only
# Full integration test (requires all credentials):
python scripts/validate_pipeline.py
```

### 10. Deploy backend to Render.com

1. Push to GitHub
2. Render → New Web Service → connect repo
3. Build: `pip install -r requirements.txt`
4. Start: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
5. Add all `.env` variables as Environment Variables in Render dashboard
6. Copy Render URL → update `window.BTS_API_BASE` in `frontend/index.html`

### 11. Serve frontend

Serve `frontend/index.html` and `frontend/upload.js` from any static host
(GitHub Pages, Cloudflare Pages, Netlify — all free).

---

## Locked spec constraints

| Constraint | Value |
|------------|-------|
| LLM model  | llama-3.3-70b-versatile |
| Embedding model | BAAI/bge-small-en-v1.5 (dim=384) |
| Preprocessing order | dcm2niix → N4 → rigid co-reg → 1mm resample → HD-BET → z-norm |
| Sequences required | T1, T1ce, T2, FLAIR (always 4) |
| RANO PR threshold | ≤ -50% bidimensional product |
| RANO PD threshold | ≥ +25% bidimensional product |
| Polling interval | 15 s |
| Polling max | 80 attempts (20 min) |
| RAG dim | 384 (FIXED — changing requires Qdrant rebuild) |
| ET label | 3 (nnU-Net BraTS convention) |
| Connectivity | 26 |

## Limitations

- Not HIPAA/GDPR compliant — de-identified academic data only
- ±10% diameter error can approach ±25% RANO threshold at borderline cases (L8)
- Intra-patient co-registration is rigid only (SimpleITK)
- CR_provisional requires confirmatory scan ≥4 weeks for CR_confirmed
- Dice scores require ground truth labels; set to 0.0 if unavailable
