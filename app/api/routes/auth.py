"""
Auth routes.
Fix #8  — role included in JWT token.
Fix #10 — rate limiter on login and register.
Fix #20 — email verification endpoint added.
Fix #21 — forgot-password and reset-password endpoints added.
Fix Q1  — role removed from public RegisterRequest. Public registration always
           creates doctor accounts. To create an admin, insert directly into
           the Supabase users table — it cannot be self-assigned via the API.
"""
from fastapi import APIRouter, Request
from pydantic import BaseModel, EmailStr
from app.services.supabase_service import (
    authenticate_user, register_user,
    verify_email_token, forgot_password, reset_password,
)
from app.core.auth import create_access_token
from app.core.rate_limit import auth_limiter, get_client_ip

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    # Fix Q1 — no role field. All public registrations are doctors.
    # To create an admin account, run this SQL in Supabase directly:
    #   INSERT INTO users (email, hashed_password, role, email_verified)
    #   VALUES ('admin@hospital.com', '<bcrypt_hash>', 'admin', true);


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


@router.post("/login")
def login(req: LoginRequest, request: Request):
    auth_limiter.check(get_client_ip(request))
    user  = authenticate_user(req.email, req.password)
    token = create_access_token({"sub": user["email"], "role": user.get("role", "doctor")})
    return {
        "access_token": token,
        "token_type":   "bearer",
        "role":         user.get("role", "doctor"),
        "email":        user["email"],
    }


@router.post("/register", status_code=201)
def register(req: RegisterRequest, request: Request):
    auth_limiter.check(get_client_ip(request))
    # Fix Q1 — always "doctor", never trust role from request body
    return register_user(req.email, req.password, role="doctor")


class VerifyEmailRequest(BaseModel):
    token: str


@router.post("/verify-email")
def verify_email(req: VerifyEmailRequest):
    """
    Fix S4 — token submitted via POST body, not GET query parameter.
    GET tokens appear in server access logs, browser history, and Referer headers.
    The frontend should POST the token from the URL fragment or a form field.
    """
    return verify_email_token(req.token)


@router.post("/forgot-password")
def forgot_password_route(req: ForgotPasswordRequest, request: Request):
    auth_limiter.check(get_client_ip(request))
    return forgot_password(req.email)


@router.post("/reset-password")
def reset_password_route(req: ResetPasswordRequest, request: Request):
    auth_limiter.check(get_client_ip(request))
    return reset_password(req.token, req.new_password)
