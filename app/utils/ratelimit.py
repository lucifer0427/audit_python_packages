"""輕量級記憶體速率限制中間件"""

import asyncio
import logging
import time
from collections import defaultdict

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class InMemoryRateLimiter:
    """Sliding window rate limiter using in-memory storage."""

    def __init__(self, max_requests: int = 5, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._lock = asyncio.Lock()
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        async with self._lock:
            timestamps = self._requests[key]
            self._requests[key] = [t for t in timestamps if t > cutoff]
            if len(self._requests[key]) >= self.max_requests:
                return False
            self._requests[key].append(now)
            return True


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for rate limiting POST /api/audit."""

    def __init__(self, app: ASGIApp, limiter: InMemoryRateLimiter):
        super().__init__(app)
        self.limiter = limiter

    async def dispatch(self, request: Request, call_next):
        if request.method == "POST" and request.url.path == "/api/audit" and self.limiter.max_requests > 0:
            client_ip = request.client.host if request.client else "unknown"
            allowed = await self.limiter.is_allowed(client_ip)
            if not allowed:
                logger.warning("Rate limit exceeded for %s", client_ip)
                return JSONResponse(
                    status_code=429,
                    content={"detail": "請求過於頻繁，請稍後再試 (上限 5 次/分鐘)"},
                )
        return await call_next(request)
