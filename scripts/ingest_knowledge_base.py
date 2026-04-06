#!/usr/bin/env python3
"""
Ingest clinical guidelines into Qdrant RAG knowledge base.

Usage:
    python scripts/ingest_knowledge_base.py \
        --docs-dir /path/to/guidelines \
        --map '{"RANO_2010.pdf": ["RANO 2010", 2010], "iRANO_2015.pdf": ["iRANO 2015", 2015]}'
"""
import argparse, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ingest")

def _parse_args(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--docs-dir",  required=True, type=Path)
    p.add_argument("--map",       required=False, type=str, default=None)
    p.add_argument("--map-file",  required=False, type=Path, default=None)
    p.add_argument("--dry-run",   action="store_true")
    p.add_argument("--rebuild",   action="store_true")
    return p.parse_args(argv)

def _validate_map(raw: str) -> dict:
    try:   data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("--map invalid JSON: %s", e); sys.exit(1)
    validated = {}
    for fname, meta in data.items():
        if not isinstance(meta, list) or len(meta) != 2:
            logger.error("Entry for %s must be [version, year]", fname); sys.exit(1)
        validated[fname] = (str(meta[0]), int(meta[1]))
    return validated

def main(argv=None) -> int:
    args = _parse_args(argv)
    if args.map_file:
        import json as _json
        gmap = _validate_map(_json.dumps(_json.loads(args.map_file.read_text(encoding="utf-8-sig"))))
    else:
        gmap = _validate_map(args.map)
    if not args.docs_dir.is_dir():
        logger.error("--docs-dir not found: %s", args.docs_dir); return 1

    if args.rebuild and not args.dry_run:
        from rag.knowledge_base import _build_qdrant_client
        from app.core.config import settings
        from qdrant_client.models import Distance, VectorParams
        client = _build_qdrant_client()
        col = settings.qdrant_collection_name
        cols = [c.name for c in client.get_collections().collections]
        if col in cols:
            client.delete_collection(col)
            logger.info("Dropped collection: %s", col)
        client.create_collection(col, vectors_config=VectorParams(size=384, distance=Distance.COSINE))
        logger.info("Created collection: %s (dim=384, cosine)", col)

    from rag.document_loader import load_and_chunk
    from rag.embeddings import embedding_model
    from rag.knowledge_base import upsert_passages

    total_up = total_sk = total_f = 0
    failed = []

    for fname, (version, year) in gmap.items():
        fpath = args.docs_dir / fname
        if not fpath.exists():
            logger.warning("File not found: %s", fpath); failed.append(fname); continue
        try:
            texts, payloads = load_and_chunk(fpath, fname, version, year)
            if not texts: continue
            if args.dry_run:
                logger.info("[DRY RUN] %s: %d chunks", fname, len(texts)); continue
            vecs = embedding_model.encode_batch(texts)
            up, sk = upsert_passages(texts, vecs, payloads)
            total_up += up; total_sk += sk; total_f += 1
            logger.info("%s: upserted=%d skipped=%d", fname, up, sk)
        except Exception as e:
            logger.error("Failed %s: %s", fname, e); failed.append(fname)

    print("\nINGESTION SUMMARY")
    print(f"  Files processed: {total_f}")
    print(f"  Chunks upserted: {total_up}")
    print(f"  Chunks skipped:  {total_sk}  (duplicate hash)")
    print(f"  Files failed:    {len(failed)}")
    if args.dry_run: print("  [DRY RUN]")
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
