"use client";

import React, { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { ChevronRight, Sun, Moon } from "lucide-react";

// ── Breadcrumb builder ────────────────────────────────────────────────────────
interface Crumb { label: string; href: string }

const SEGMENT_LABELS: Record<string, string> = {
  dashboard:    "Dashboard",
  patients:     "Patients",
  upload:       "Upload Scan",
  status:       "Pipeline Status",
  scans:        "Scans",
  report:       "Report",
  longitudinal: "Longitudinal",
  admin:        "Administration",
  login:        "Login",
  register:     "Register",
};

function buildCrumbs(pathname: string): Crumb[] {
  const segments = pathname.split("/").filter(Boolean);
  const crumbs: Crumb[] = [];
  let built = "";
  for (const seg of segments) {
    built += `/${seg}`;
    crumbs.push({ label: SEGMENT_LABELS[seg] ?? seg, href: built });
  }
  return crumbs;
}

function pageTitle(pathname: string): string {
  const segments = pathname.split("/").filter(Boolean);
  if (!segments.length) return "GLIOTRACK";
  const last = segments[segments.length - 1];
  return SEGMENT_LABELS[last] ?? last;
}

// ── Theme toggle hook ─────────────────────────────────────────────────────────
function useTheme() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    const saved = (localStorage.getItem("gliotrack-theme") ?? "dark") as "dark" | "light";
    setTheme(saved);
  }, []);

  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    localStorage.setItem("gliotrack-theme", next);
    document.documentElement.setAttribute("data-theme", next);
  }

  return { theme, toggle };
}

// ── Component ─────────────────────────────────────────────────────────────────
export default function TopBar() {
  const pathname     = usePathname();
  const crumbs       = buildCrumbs(pathname);
  const title        = pageTitle(pathname);
  const { theme, toggle } = useTheme();

  return (
    <header
      className="sticky top-0 z-20 h-[57px] flex items-center justify-between px-6 backdrop-blur-md"
      style={{
        borderBottom: "1px solid var(--border)",
        backgroundColor: "color-mix(in srgb, var(--bg) 90%, transparent)",
      }}
    >
      {/* Left — title + breadcrumbs */}
      <div>
        <h1 className="text-[14px] font-semibold leading-none" style={{ color: "var(--text)" }}>
          {title}
        </h1>

        {crumbs.length > 1 && (
          <nav aria-label="Breadcrumb" className="flex items-center gap-1 mt-1">
            {crumbs.map((crumb, i) => (
              <React.Fragment key={crumb.href}>
                {i > 0 && <ChevronRight size={10} style={{ color: "var(--border)" }} />}
                {i < crumbs.length - 1 ? (
                  <Link
                    href={crumb.href}
                    className="text-[11px] transition-colors duration-150 hover:underline"
                    style={{ color: "var(--muted)" }}
                  >
                    {crumb.label}
                  </Link>
                ) : (
                  <span className="text-[11px]" style={{ color: "var(--text)" }}>
                    {crumb.label}
                  </span>
                )}
              </React.Fragment>
            ))}
          </nav>
        )}
      </div>

      {/* Right — theme toggle */}
      <button
        onClick={toggle}
        aria-label="Toggle theme"
        className="flex items-center justify-center w-8 h-8 rounded-lg transition-colors duration-150"
        style={{
          border: "1px solid var(--border)",
          backgroundColor: "var(--surface-2)",
          color: "var(--muted)",
        }}
      >
        {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
      </button>
    </header>
  );
}