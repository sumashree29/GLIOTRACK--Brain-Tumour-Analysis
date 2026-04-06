"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Brain, Eye, EyeOff, Loader2, AlertCircle, CheckCircle2 } from "lucide-react";
import { registerRequest } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();

  const [email,    setEmail   ] = useState("");
  const [password, setPassword] = useState("");
  const [confirm,  setConfirm ] = useState("");
  const [showPw,   setShowPw  ] = useState(false);
  const [loading,  setLoading ] = useState(false);
  const [error,    setError   ] = useState<string | null>(null);
  const [success,  setSuccess ] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);
    try {
      await registerRequest(email.trim(), password);
      setSuccess(true);
      setTimeout(() => router.push("/login"), 2200);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })
          ?.response?.data?.detail;
      setError(detail ?? "Registration failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#0d1117] flex items-center justify-center p-8">
      <div className="w-full max-w-[380px]">

        {/* Logo */}
        <div className="flex items-center gap-3 mb-8">
          <div className="
            flex h-9 w-9 items-center justify-center rounded-lg shrink-0
            bg-gradient-to-br from-[#2f81f7] to-[#1557b0]
            shadow-[0_0_14px_rgba(47,129,247,0.4)]
          ">
            <Brain size={16} className="text-white" />
          </div>
          <div>
            <p className="text-[13px] font-bold text-[#e6edf3] leading-none">GLIOTRACK</p>
            <p className="text-[10px] text-[#8b949e] mt-0.5 leading-none">
              Brain Tumour Analysis
            </p>
          </div>
        </div>

        <h1 className="text-[22px] font-bold text-[#e6edf3] tracking-tight">
          Create account
        </h1>
        <p className="mt-1 text-sm text-[#8b949e]">
          All new accounts receive the{" "}
          <span className="text-[#2f81f7] font-medium">Doctor</span> role
        </p>

        {/* Success */}
        {success && (
          <div className="
            flex items-start gap-2.5 mt-5 px-3.5 py-3 rounded-lg
            bg-[#1a4a1f] border border-[#3fb950]
          ">
            <CheckCircle2 size={14} className="text-[#3fb950] mt-0.5 shrink-0" />
            <p className="text-[13px] text-[#3fb950] leading-snug">
              Account created! Redirecting to login…
            </p>
          </div>
        )}

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
              disabled={success}
              className="
                w-full px-3.5 py-2.5 rounded-lg text-sm
                bg-[#161b22] border border-[#30363d]
                text-[#e6edf3] placeholder-[#484f58]
                focus:outline-none focus:border-[#2f81f7]
                focus:ring-1 focus:ring-[#2f81f7]/30
                disabled:opacity-50
                transition-colors duration-150
              "
            />
          </div>

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
                autoComplete="new-password"
                placeholder="Min. 8 characters"
                disabled={success}
                className="
                  w-full px-3.5 py-2.5 pr-10 rounded-lg text-sm
                  bg-[#161b22] border border-[#30363d]
                  text-[#e6edf3] placeholder-[#484f58]
                  focus:outline-none focus:border-[#2f81f7]
                  focus:ring-1 focus:ring-[#2f81f7]/30
                  disabled:opacity-50
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

          <div>
            <label className="block text-[11px] font-semibold text-[#8b949e] uppercase tracking-wider mb-1.5">
              Confirm Password
            </label>
            <input
              type={showPw ? "text" : "password"}
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              autoComplete="new-password"
              placeholder="Repeat password"
              disabled={success}
              className="
                w-full px-3.5 py-2.5 rounded-lg text-sm
                bg-[#161b22] border border-[#30363d]
                text-[#e6edf3] placeholder-[#484f58]
                focus:outline-none focus:border-[#2f81f7]
                focus:ring-1 focus:ring-[#2f81f7]/30
                disabled:opacity-50
                transition-colors duration-150
              "
            />
          </div>

          <button
            type="submit"
            disabled={loading || success}
            className="
              w-full flex items-center justify-center gap-2 mt-2
              py-2.5 px-4 rounded-lg
              bg-gradient-to-r from-[#2f81f7] to-[#1557b0]
              text-white text-[13px] font-semibold
              hover:from-[#388bfd] hover:to-[#1d6fe8]
              disabled:opacity-50 disabled:cursor-not-allowed
              shadow-[0_0_20px_rgba(47,129,247,0.3)]
              transition-all duration-200
            "
          >
            {loading
              ? <><Loader2 size={14} className="animate-spin" /> Creating account…</>
              : "Create account"}
          </button>
        </form>

        <p className="mt-6 text-center text-[12px] text-[#8b949e]">
          Already have an account?{" "}
          <Link
            href="/login"
            className="text-[#2f81f7] font-medium hover:underline"
          >
            Sign in
          </Link>
        </p>

        <p className="
          mt-8 text-[10px] text-center text-[#484f58] leading-relaxed
          border-t border-[#21262d] pt-5
        ">
          Clinical decision support only.<br />
          Not for use without qualified clinician review.
        </p>
      </div>
    </div>
  );
}
