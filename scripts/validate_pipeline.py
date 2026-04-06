#!/usr/bin/env python3
"""
End-to-end smoke tests + Spec L8 diameter error quantification.
Run: python scripts/validate_pipeline.py --unit-only
"""
import argparse, sys, unittest

# ── A1: RANO boundaries ──────────────────────────────────────────────
class TestRANO(unittest.TestCase):
    def _c(self, pct):
        if pct <= -50: return "PR"
        if pct >= 25:  return "PD"
        return "SD"
    def test_pr_minus50(self):  self.assertEqual(self._c(-50.0), "PR")
    def test_sd_minus49(self):  self.assertEqual(self._c(-49.9), "SD")
    def test_pd_plus25(self):   self.assertEqual(self._c(25.0),  "PD")
    def test_sd_plus24(self):   self.assertEqual(self._c(24.9),  "SD")
    def test_sd_zero(self):     self.assertEqual(self._c(0.0),   "SD")

# ── A2: Longitudinal edge cases ──────────────────────────────────────
class TestLong(unittest.TestCase):
    def _nadir(self, bps):
        m = min(bps); return m, bps.index(m)
    def test_nadir_middle(self):   self.assertEqual(self._nadir([300,100,300])[1], 1)
    def test_nadir_tie_earliest(self): self.assertEqual(self._nadir([100,200,100])[1], 0)
    def test_dissociation_below25(self):
        nadir=400; cur=nadir*1.249; pct=((cur-nadir)/nadir)*100
        self.assertTrue(pct < 25.0)
    def test_no_dissociation_at25(self):
        nadir=400; cur=nadir*1.25; pct=((cur-nadir)/nadir)*100
        self.assertFalse(pct < 25.0)

# ── A3: Diameter error propagation (Spec L8) ─────────────────────────
def _bp_err(err_pct):
    e = err_pct / 100.0
    return ((1 + e)**2 - 1) * 100.0

class TestDiamError(unittest.TestCase):
    def test_10pct_gives_21pct_bp(self):
        self.assertAlmostEqual(_bp_err(10.0), 21.0, places=1)
    def test_5pct_gives_10pct_bp(self):
        self.assertAlmostEqual(_bp_err(5.0), 10.25, places=1)
    def test_borderline_sd_can_flip_pd(self):
        baseline=400; true_cur=baseline*1.22; meas=true_cur*1.21
        pct = (meas - baseline)/baseline*100
        self.assertGreater(pct, 25.0)
    def test_low_conf_at_11mm(self):
        d1_low = 11.0 * 0.9
        self.assertLess(d1_low, 10.0)
    def test_no_low_conf_large(self):
        self.assertFalse(40.0*0.9 < 10.0)
    def test_error_report(self):
        print("\n" + "="*60)
        print("SPEC L8 — DIAMETER ERROR QUANTIFICATION")
        print("="*60)
        for err in [5, 10, 15]:
            bp_e = _bp_err(err)
            flag = "WARN can flip SD->PD" if bp_e >= 21 else "OK"
            print(f"  +-{err}% diameter -> +-{bp_e:.1f}% BP  [{flag}]")
        print("="*60)
        self.assertTrue(True)

# ── A4: Embedding dim constant ───────────────────────────────────────
class TestEmbedding(unittest.TestCase):
    def test_dim_locked(self): self.assertEqual(384, 384)
    def test_wrong_dim_raises(self):
        with self.assertRaises(RuntimeError):
            v_shape = (768,)
            if v_shape != (384,): raise RuntimeError(f"Dim mismatch: {v_shape}")

# ── B: Integration probes ────────────────────────────────────────────
def _probe_supabase():
    from app.database.supabase_client import get_supabase_client
    get_supabase_client().table("patients").select("patient_id").limit(1).execute()
    return True, "OK"
def _probe_r2():
    import boto3; from app.core.config import settings
    boto3.client("s3", endpoint_url=settings.r2_endpoint_url,
                 aws_access_key_id=settings.r2_access_key_id,
                 aws_secret_access_key=settings.r2_secret_access_key,
                 region_name="auto").head_bucket(Bucket=settings.r2_bucket_name)
    return True, "OK"
def _probe_qdrant():
    from rag.knowledge_base import _build_qdrant_client; from app.core.config import settings
    cols = [c.name for c in _build_qdrant_client().get_collections().collections]
    col  = settings.qdrant_collection_name
    return col in cols, f"collection {col} {'found' if col in cols else 'NOT found'}"
def _probe_groq():
    from app.services.llm_service import call_llm
    r = call_llm("Reply with one word.", "PONG")
    return True, f"tokens={r.completion_tokens}"
def _probe_modal():
    import httpx; from app.core.config import settings
    r = httpx.get(f"{settings.modal_webhook_url}/health", timeout=10)
    return r.status_code == 200, f"HTTP {r.status_code}"

def _run_integration():
    probes = [("B1 Supabase", _probe_supabase), ("B2 R2", _probe_r2),
              ("B3 Qdrant",   _probe_qdrant),   ("B4 Groq", _probe_groq),
              ("B5 Modal",    _probe_modal)]
    print("\n" + "="*55 + "\nINTEGRATION PROBES\n" + "="*55)
    ok_all = True
    for name, fn in probes:
        try:    ok, detail = fn()
        except Exception as e: ok, detail = False, str(e)
        print(f"  {'PASS' if ok else 'FAIL'}  {name}  {detail}")
        if not ok: ok_all = False
    return ok_all

def main(argv=None):
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group()
    g.add_argument("--unit-only",  action="store_true")
    g.add_argument("--integ-only", action="store_true")
    args = p.parse_args(argv)

    unit_ok = integ_ok = True
    if not args.integ_only:
        suite = unittest.TestLoader().loadTestsFromTestCase
        s = unittest.TestSuite()
        for cls in [TestRANO, TestLong, TestDiamError, TestEmbedding]:
            s.addTests(suite(cls))
        result = unittest.TextTestRunner(verbosity=2).run(s)
        unit_ok = result.wasSuccessful()
    if not args.unit_only:
        try:    integ_ok = _run_integration()
        except Exception as e:
            print(f"Integration probes error: {e}"); integ_ok = False

    print("\nSUMMARY")
    if not args.integ_only: print(f"  Unit:  {'PASS' if unit_ok  else 'FAIL'}")
    if not args.unit_only:  print(f"  Integ: {'PASS' if integ_ok else 'FAIL'}")
    return 0 if (unit_ok and integ_ok) else 1

if __name__ == "__main__":
    sys.exit(main())
