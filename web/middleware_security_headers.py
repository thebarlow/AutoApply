"""Baseline browser security headers on every HTTP response (pure ASGI).

Pure ASGI (not BaseHTTPMiddleware) so the /api/events SSE stream is not
buffered. Headers a route sets itself are left untouched.

CSP notes (audited against the built ``react-dashboard/dist``):

* Vite emits only external ``<script type="module" src="/assets/...">`` and a
  stylesheet link -- no inline scripts, no third-party origins (no Google
  Fonts; Stripe Checkout is a top-level redirect, not Stripe.js), so
  ``script-src 'self'`` holds.
* ``style-src 'unsafe-inline'``: ResumeCompare renders ``<iframe srcdoc>``
  documents with an inline ``<style>`` block, and srcdoc frames inherit the
  parent's CSP.
* ``img-src data:`` for the CSS noise background; ``blob:`` for PDF downloads
  built via ``URL.createObjectURL``.
* ``frame-src 'self'``: the dashboard previews generated PDFs from
  ``/api/jobs/{key}/resume|cover`` in same-origin iframes.

PDF responses are the one exception to the anti-framing policy: they get
``X-Frame-Options: SAMEORIGIN`` and ``frame-ancestors 'self'`` (and no other
CSP directives, since a document policy such as ``object-src 'none'`` on the
PDF itself can stop the browser's built-in viewer from rendering it).
"""
from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from core.env import is_production

CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "font-src 'self' data:",
        "connect-src 'self'",
        "frame-src 'self' blob:",
        "worker-src 'self' blob:",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)
_PDF_CSP = "frame-ancestors 'self'"
HSTS = "max-age=31536000; includeSubDomains"

# FastAPI's Swagger UI (dev only; disabled in production) loads its JS/CSS
# from a CDN with an inline bootstrap script, which the strict CSP would block.
_DEV_DOCS_PATHS = ("/endpoints", "/docs/oauth2-redirect")


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        production = is_production()
        skip_csp = not production and scope.get("path", "") in _DEV_DOCS_PATHS

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                is_pdf = headers.get("content-type", "").startswith("application/pdf")
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("X-Frame-Options", "SAMEORIGIN" if is_pdf else "DENY")
                headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
                if not skip_csp:
                    headers.setdefault(
                        "Content-Security-Policy",
                        _PDF_CSP if is_pdf else CONTENT_SECURITY_POLICY,
                    )
                if production:
                    headers.setdefault("Strict-Transport-Security", HSTS)
            await send(message)

        await self.app(scope, receive, send_with_headers)
