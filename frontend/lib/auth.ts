// ─────────────────────────────────────────────────────────────────────────────
// GLIOTRACK — Auth helpers
//
// JWT is stored in browser cookies — never in localStorage or sessionStorage.
// Two cookies are written on login:
//   gliotrack_token  — the raw JWT (read by api.ts interceptor)
//   gliotrack_user   — { email, role } JSON (read by UI components)
// ─────────────────────────────────────────────────────────────────────────────

import { jwtDecode } from "jwt-decode";
import type { User } from "@/types";

// ── Cookie names ──────────────────────────────────────────────────────────────
const TOKEN_COOKIE = "gliotrack_token";
const USER_COOKIE  = "gliotrack_user";

// ── Low-level cookie helpers ──────────────────────────────────────────────────
function setCookie(name: string, value: string, maxAgeSecs = 86400): void {
  if (typeof document === "undefined") return;
  document.cookie =
    `${name}=${encodeURIComponent(value)}; Max-Age=${maxAgeSecs}; path=/; SameSite=Lax`;
}

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=")[1]) : null;
}

function deleteCookie(name: string): void {
  if (typeof document === "undefined") return;
  document.cookie = `${name}=; Max-Age=0; path=/; SameSite=Lax`;
}

// ── JWT payload shape ─────────────────────────────────────────────────────────
interface JWTPayload {
  sub:    string;
  role:   "doctor" | "admin";
  exp:    number;
  email?: string;
}

// ── Public API ────────────────────────────────────────────────────────────────

/** Persist a session after successful login */
export function saveSession(
  token: string,
  email: string,
  role: "doctor" | "admin"
): void {
  setCookie(TOKEN_COOKIE, token);
  setCookie(USER_COOKIE, JSON.stringify({ email, role }));
}

/** Returns the raw JWT string, or null if not logged in */
export function getToken(): string | null {
  return getCookie(TOKEN_COOKIE);
}

/** Returns the full User object, or null if no valid session */
export function getUser(): User | null {
  const userRaw = getCookie(USER_COOKIE);
  const token   = getToken();
  if (!userRaw || !token) return null;

  try {
    const { email, role } = JSON.parse(userRaw) as {
      email: string;
      role: "doctor" | "admin";
    };
    return { email, role, access_token: token };
  } catch {
    return null;
  }
}

/** Wipe all session cookies — used on logout and 401 responses */
export function clearSession(): void {
  deleteCookie(TOKEN_COOKIE);
  deleteCookie(USER_COOKIE);
}

/** True if the JWT exists and has not expired */
export function isAuthenticated(): boolean {
  const token = getToken();
  if (!token) return false;
  return !isTokenExpired(token);
}

/** True if the JWT exp claim is in the past */
export function isTokenExpired(token: string): boolean {
  try {
    const { exp } = jwtDecode<JWTPayload>(token);
    return Date.now() / 1000 > exp;
  } catch {
    return true;
  }
}

/** Returns the current user's role, or null if not logged in */
export function getRole(): "doctor" | "admin" | null {
  return getUser()?.role ?? null;
}

/** Convenience: true when role === "admin" */
export function isAdmin(): boolean {
  return getRole() === "admin";
}

/** Decode any JWT string without verifying signature */
export function decodeToken(token: string): JWTPayload | null {
  try {
    return jwtDecode<JWTPayload>(token);
  } catch {
    return null;
  }
}
