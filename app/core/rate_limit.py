"""
In-process sliding-window rate limiter.
Fix #10 — protects all API endpoints from brute-force and abuse.
Fix Q4  — X-Forwarded-For only trusted from configured TRUSTED_PROXY IP.
Fix R10 — LRU cap on _windows to prevent OOM from rotating-IP scanners.
Fix S2  — LRU now uses collections.OrderedDict for true O(1) eviction.
          (Previous list-based _order was O(n) — misleading comment fixed.)

For multi-instance deployments replace with a Redis-backed store.
"""
from __future__ import annotations
from collections import deque, OrderedDict
from fastapi import HTTPException, Request
import time
from app.core.config import settings


class RateLimiter:
    # Fix R10/S2 — cap at 50k IPs; evict oldest with O(1) OrderedDict LRU.
    MAX_KEYS = 50_000

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests   = max_requests
        self.window_seconds = window_seconds
        # OrderedDict preserves insertion order — popitem(last=False) is O(1)
        self._windows: OrderedDict[str, deque] = OrderedDict()

    def check(self, key: str):
        now    = time.monotonic()

        if key in self._windows:
            # Move to end so it is not evicted as "oldest"
            self._windows.move_to_end(key)
        else:
            # Evict the oldest entry if at capacity
            if len(self._windows) >= self.MAX_KEYS:
                self._windows.popitem(last=False)  # O(1)
            self._windows[key] = deque()

        window = self._windows[key]
        cutoff = now - self.window_seconds
        while window and window[0] < cutoff:
            window.popleft()

        if len(window) >= self.max_requests:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Max {self.max_requests} requests per {self.window_seconds}s.",
                headers={"Retry-After": str(self.window_seconds)},
            )
        window.append(now)


# Per-IP limiters
auth_limiter     = RateLimiter(max_requests=10,  window_seconds=60)
pipeline_limiter = RateLimiter(max_requests=5,   window_seconds=60)
upload_limiter   = RateLimiter(max_requests=30,  window_seconds=60)
api_limiter      = RateLimiter(max_requests=200, window_seconds=60)


def get_client_ip(request: Request) -> str:
    """
    Fix Q4 — real TCP peer IP used by default.
    X-Forwarded-For only trusted when the connection comes from TRUSTED_PROXY.
    """
    direct_ip = request.client.host if request.client else "unknown"
    trusted_proxy = getattr(settings, "trusted_proxy", "")
    if trusted_proxy and direct_ip == trusted_proxy:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return direct_ip
