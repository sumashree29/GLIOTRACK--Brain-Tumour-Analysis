"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Brain } from "lucide-react";
import { isAuthenticated, getRole } from "@/lib/auth";

interface AuthGuardProps {
  children:      React.ReactNode;
  /** Set true on /admin — redirects doctors to /dashboard */
  requireAdmin?: boolean;
}

type CheckState = "pending" | "ok" | "redirecting";

export default function AuthGuard({
  children,
  requireAdmin = false,
}: AuthGuardProps) {
  const router = useRouter();
  const [check, setCheck] = useState<CheckState>("pending");

  useEffect(() => {
    // No valid token → go to login
    if (!isAuthenticated()) {
      router.replace("/login");
      setCheck("redirecting");
      return;
    }

    // Admin-only page but user is a doctor
    if (requireAdmin && getRole() !== "admin") {
      router.replace("/dashboard");
      setCheck("redirecting");
      return;
    }

    setCheck("ok");
  }, [router, requireAdmin]);

  // Show branded loading state while checking
  if (check === "pending" || check === "redirecting") {
    return (
      <div className="min-h-screen bg-[#0d1117] flex items-center justify-center">
        <div className="flex flex-col items-center gap-5">
          {/* Pulsing logo */}
          <div className="relative">
            <div className="
              absolute inset-0 rounded-xl
              bg-[#2f81f7] opacity-20 blur-xl animate-pulse
            " />
            <div className="
              relative flex h-12 w-12 items-center justify-center rounded-xl
              bg-gradient-to-br from-[#2f81f7] to-[#1557b0]
            ">
              <Brain size={22} className="text-white" />
            </div>
          </div>
          <p className="text-[13px] text-[#8b949e] font-medium">
            {check === "redirecting" ? "Redirecting…" : "Verifying session…"}
          </p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
