"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Brain, Eye, EyeOff, Loader2, AlertCircle } from "lucide-react";
import { loginRequest } from "@/lib/api";
import { saveSession } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();

  const [email,    setEmail   ] = useState("");
  const [password, setPassword] = useState("");
  const [showPw,   setShowPw  ] = useState(false);
  const [loading,  setLoading ] = useState(false);
  const [error,    setError   ] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const data = await loginRequest(email.trim(), password);
      saveSession(data.access_token, data.email, data.role);
      router.push(data.role === "admin" ? "/admin" : "/dashboard");
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })
          ?.response?.data?.detail;
      setError(detail ?? "Invalid credentials. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#0d1117] flex">

      {/* ── Left panel — branding ─────────────────────────────── */}
      <div className="
        hidden lg:flex flex-col justify-between
        w-[460px] shrink-0 relative overflow-hidden
        border-r border-[#21262d]
        p-10
      ">
        {/* Dot-grid background */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            backgroundImage:
              "radial-gradient(circle, #30363d 1px, transparent 1px)",
            backgroundSize: "28px 28px",
            opacity: 0.4,
          }}
        />
        {/* Blue glow */}
        <div className="
          absolute -top-32 -left-32 w-[480px] h-[480px] rounded-full
          bg-[#2f81f7] opacity-[0.07] blur-3xl pointer-events-none
        " />
        <div className="
          absolute -bottom-32 -right-32 w-[360px] h-[360px] rounded-full
          bg-[#2f81f7] opacity-[0.04] blur-3xl pointer-events-none
        " />

        {/* Logo */}
        <div className="relative z-10 flex items-center gap-3">
          <div className="
            flex h-9 w-9 items-center justify-center rounded-lg shrink-0
            bg-gradient-to-br from-[#2f81f7] to-[#1557b0]
            shadow-[0_0_16px_rgba(47,129,247,0.45)]
          ">
            <Brain size={17} className="text-white" />
          </div>
          <div>
            <p className="text-[14px] font-bold text-[#e6edf3] leading-none">GLIOTRACK</p>
            <p className="text-[10px] text-[#8b949e] mt-0.5 leading-none">MRI-Based Tumour Analysis</p>
          </div>
        </div>

        {/* Hero copy */}
        <div className="relative z-10 space-y-7">
          <div>
            <h2 className="text-[32px] font-bold text-[#e6edf3] leading-[1.15] tracking-tight">
              AI-powered<br />
              <span className="text-[#2f81f7]">brain tumour</span><br />
              analysis.
            </h2>
            <p className="mt-4 text-sm text-[#8b949e] leading-relaxed max-w-[300px]">
              Five sequential AI agents. Grounded RANO classification.
              Fully auditable clinical PDF reports. Zero hallucination by design.
            </p>
          </div>

          {/* Stats grid */}
          <div className="grid grid-cols-2 gap-2.5">
            {[
              { value: "5",    label: "AI Agents"      },
              { value: "0",    label: "Hallucinations" },
              { value: "RANO", label: "Compliant"      },
              { value: "PDF",  label: "Audit trail"    },
            ].map((s) => (
              <div
                key={s.label}
                className="
                  rounded-xl border border-[#21262d] bg-[#161b22]/70
                  p-3.5 backdrop-blur-sm
                "
              >
                <p className="text-[18px] font-bold text-[#2f81f7] font-mono leading-none">
                  {s.value}
                </p>
                <p className="text-[11px] text-[#8b949e] mt-1">{s.label}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Footer disclaimer */}
        <p className="relative z-10 text-[10px] text-[#484f58] leading-relaxed">
          Clinical decision support only.<br />
          Not for use without qualified clinician review.
        </p>
      </div>

      {/* ── Right panel — form ────────────────────────────────── */}
      <div className="flex flex-1 items-center justify-center p-8">
        <div className="w-full max-w-[360px]">

          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-3 mb-8">
            <div className="
              flex h-8 w-8 items-center justify-center rounded-lg
              bg-gradient-to-br from-[#2f81f7] to-[#1557b0]
            ">
              <Brain size={15} className="text-white" />
            </div>
            <span className="text-[13px] font-bold text-[#e6edf3]">GLIOTRACK</span>
          </div>

          <h1 className="text-[22px] font-bold text-[#e6edf3] tracking-tight">
            Welcome back
          </h1>
          <p className="mt-1 text-sm text-[#8b949e]">
            Sign in to your clinical dashboard
          </p>

          {/* Error */}
          {error && (
            <div className="
              flex items-start gap-2.5 mt-5 px-3.5 py-3 rounded-lg
              bg-[#4a1a1a] border border-[#f85149]
            ">
              <AlertCircle size={14} className="text-[#f85149] mt-0.5 shrink-0" />
              <p className="text-[13px] text-[#f85149] leading-snug">{error}</p>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} className="mt-6 space-y-4">

            {/* Email */}
            <div>
              <label className="block text-[11px] font-semibold text-[#8b949e] uppercase tracking-wider mb-1.5">
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                placeholder="doctor@hospital.org"
                className="
                  w-full px-3.5 py-2.5 rounded-lg text-sm
                  bg-[#161b22] border border-[#30363d]
                  text-[#e6edf3] placeholder-[#484f58]
                  focus:outline-none focus:border-[#2f81f7]
                  focus:ring-1 focus:ring-[#2f81f7]/30
                  transition-colors duration-150
                "
              />
            </div>

            {/* Password */}
            <div>
              <label className="block text-[11px] font-semibold text-[#8b949e] uppercase tracking-wider mb-1.5">
                Password
              </label>
              <div className="relative">
                <input
                  type={showPw ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                  placeholder="••••••••"
                  className="
                    w-full px-3.5 py-2.5 pr-10 rounded-lg text-sm
                    bg-[#161b22] border border-[#30363d]
                    text-[#e6edf3] placeholder-[#484f58]
                    focus:outline-none focus:border-[#2f81f7]
                    focus:ring-1 focus:ring-[#2f81f7]/30
                    transition-colors duration-150
                  "
                />
                <button
                  type="button"
                  onClick={() => setShowPw((v) => !v)}
                  className="
                    absolute right-3 top-1/2 -translate-y-1/2
                    text-[#484f58] hover:text-[#8b949e]
                    transition-colors duration-150
                  "
                  aria-label={showPw ? "Hide password" : "Show password"}
                >
                  {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="
                w-full flex items-center justify-center gap-2
                py-2.5 px-4 mt-2 rounded-lg
                bg-gradient-to-r from-[#2f81f7] to-[#1557b0]
                text-white text-[13px] font-semibold
                hover:from-[#388bfd] hover:to-[#1d6fe8]
                disabled:opacity-50 disabled:cursor-not-allowed
                shadow-[0_0_20px_rgba(47,129,247,0.3)]
                hover:shadow-[0_0_28px_rgba(47,129,247,0.45)]
                transition-all duration-200
              "
            >
              {loading
                ? <><Loader2 size={14} className="animate-spin" /> Signing in…</>
                : "Sign in"}
            </button>
          </form>

          <p className="mt-6 text-center text-[12px] text-[#8b949e]">
            Don&apos;t have an account?{" "}
            <Link
              href="/register"
              className="text-[#2f81f7] font-medium hover:underline"
            >
              Register
            </Link>
          </p>

          <p className="
            mt-8 text-[10px] text-center text-[#484f58] leading-relaxed
            border-t border-[#21262d] pt-5
          ">
            Clinical decision support only. Not for use without qualified clinician review.
          </p>
        </div>
      </div>
    </div>
  );
}
