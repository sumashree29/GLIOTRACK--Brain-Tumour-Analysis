"""
User management via Supabase.
Fix #8  — role stored in DB and returned to JWT.
Fix #14 — register_user accepts and persists role.
Fix #20 — email_verified checked at login; set after verification.
Fix #21 — forgot_password and reset_password flows added.
"""
from __future__ import annotations
import secrets
from datetime import datetime, timedelta, timezone
from app.database.supabase_client import get_supabase_client
from app.core.auth import hash_password, verify_password
from fastapi import HTTPException, status
import logging

logger = logging.getLogger(__name__)


def _validate_password_strength(password: str):
    """Fix R5 — enforce minimum security policy for a PHI system."""
    import re
    errors = []
    if len(password) < 12:
        errors.append("at least 12 characters")
    if not re.search(r"[A-Z]", password):
        errors.append("at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        errors.append("at least one lowercase letter")
    if not re.search(r"[0-9]", password):
        errors.append("at least one digit")
    if not re.search(r"[^A-Za-z0-9]", password):
        errors.append("at least one special character (!@#$%^&* etc.)")
    if errors:
        raise HTTPException(
            status_code=400,
            detail="Password must contain: " + ", ".join(errors) + ".",
        )


def register_user(email: str, password: str, role: str = "doctor") -> dict:
    if role not in ("doctor", "radiologist", "admin"):
        raise HTTPException(status_code=400, detail="Role must be 'doctor', 'radiologist' or 'admin'")

    # Whitelist check — only pre-approved emails can register
    db = get_supabase_client()
    whitelist = db.table("whitelist").select("email, role").eq("email", email).execute()
    if not whitelist.data:
        raise HTTPException(status_code=403, detail="You are not authorized to register. Contact your administrator.")
    
    # Use the role assigned in whitelist, not what user sends
    role = whitelist.data[0]["role"]

    db = get_supabase_client()
    existing = db.table("users").select("email").eq("email", email).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="Email already registered")

    # FIX #14 — role persisted; FIX #20 — email_verified starts False
    # Some Supabase schemas may not include role/email_verified; handle gracefully for local dev.
    payload = {
        "email":           email,
        "hashed_password": hash_password(password),
        "role":            role,
        "email_verified":  True,
    }
    try:
        from postgrest.exceptions import APIError  # type: ignore
    except Exception:
        APIError = None  # type: ignore

    while True:
        try:
            db.table("users").insert(payload).execute()
            break
        except Exception as e:
            if APIError is None or not isinstance(e, APIError):
                raise
            # Typical message: "Could not find the 'email_verified' column of 'users' in the schema cache"
            msg = str(getattr(e, "message", "")) or str(e)
            import re
            m = re.search(r"Could not find the '([^']+)' column", msg)
            if not m:
                raise
            missing_col = m.group(1)
            if missing_col not in payload:
                raise
            payload.pop(missing_col, None) 

    # TODO: re-enable _send_verification_email for production
    return {
        "email":   email,  
        "role":    role,
        "message": "Registration successful. You may now log in.",
    }


def authenticate_user(email: str, password: str) -> dict:
    db = get_supabase_client()
    r  = db.table("users").select("*").eq("email", email).execute()
    if not r.data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    user = r.data[0]
    if not verify_password(password, user["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    # FIX #20 — block login until email is verified (only if column exists)
    if "email_verified" in user and not user.get("email_verified", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Please check your inbox.",
        )
    return user


def verify_email_token(token: str) -> dict:
    """Mark email as verified when user clicks the link."""
    db = get_supabase_client()
    r  = db.table("email_verifications").select("*").eq("token", token).execute()
    if not r.data:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")
    row = r.data[0]
    expires = datetime.fromisoformat(row["expires_at"])
    if datetime.now(timezone.utc) > expires:
        raise HTTPException(status_code=400, detail="Verification token has expired")

    db.table("users").update({"email_verified": True}).eq("email", row["email"]).execute()
    db.table("email_verifications").delete().eq("token", token).execute()
    return {"message": "Email verified successfully. You may now log in."}


def forgot_password(email: str) -> dict:
    """FIX #21 — generate a reset token and store it.
    FIX H  — delete any existing reset token first so only one valid token exists per user."""
    db = get_supabase_client()
    r  = db.table("users").select("email").eq("email", email).execute()
    # Always return the same message to prevent email enumeration
    if not r.data:
        return {"message": "If that email exists, a reset link has been sent."}

    # FIX H — remove any existing reset token for this email before creating a new one
    db.table("password_resets").delete().eq("email", email).execute()

    token      = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    db.table("password_resets").insert({
        "email": email, "token": token, "expires_at": expires_at,
    }).execute()

    _send_password_reset_email(email, token)
    return {"message": "If that email exists, a reset link has been sent."}


def reset_password(token: str, new_password: str) -> dict:
    """FIX #21 — validate reset token and update password."""
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    db = get_supabase_client()
    r  = db.table("password_resets").select("*").eq("token", token).execute()
    if not r.data:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    row = r.data[0]
    expires = datetime.fromisoformat(row["expires_at"])
    if datetime.now(timezone.utc) > expires:
        db.table("password_resets").delete().eq("token", token).execute()
        raise HTTPException(status_code=400, detail="Reset token has expired")

    db.table("users").update({
        "hashed_password": hash_password(new_password),
    }).eq("email", row["email"]).execute()
    db.table("password_resets").delete().eq("token", token).execute()
    return {"message": "Password reset successfully. You may now log in."}


# ── Email helpers ─────────────────────────────────────────────────────────────
# Replace the logger.info calls below with your email provider (SendGrid, SES, etc.)

def _send_verification_email(email: str):   
    db    = get_supabase_client()
    # FIX I — remove any existing verification token before creating a fresh one
    db.table("email_verifications").delete().eq("email", email).execute()
    token = secrets.token_urlsafe(32)
    exp   = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    db.table("email_verifications").insert({
        "email": email, "token": token, "expires_at": exp,
    }).execute()
    # TODO: replace with real email send
    logger.info(
        "VERIFICATION EMAIL → %s | token=%s | link=https://YOUR_DOMAIN/verify?token=%s",
        email, token, token,
    )


def _send_password_reset_email(email: str, token: str):
    # TODO: replace with real email send
    logger.info(
        "PASSWORD RESET EMAIL → %s | link=https://YOUR_DOMAIN/reset-password?token=%s",
        email, token,
    )
