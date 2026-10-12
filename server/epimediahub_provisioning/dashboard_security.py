"""CSRF and response hardening for the browser-only admin and reseller surfaces.

Existing device/API endpoints keep their independent authentication protocols.
Forms are augmented server-side so shared templates and historic views retain
their business behavior. No cookie state is trusted without its CSRF counterpart.
"""
from __future__ import annotations

import hmac
import re
import secrets

from flask import abort, current_app, request, session

FORM = re.compile(r"<form\\b[^>]*>", re.I)
METHOD_POST = re.compile(r"\\bmethod\\s*=\\s*(['\"]?)post\\1(?=\\s|>)", re.I)
EXISTING_TOKEN = re.compile(r'name\\s*=\\s*["\']_dashboard_csrf["\']', re.I)
SAFE_PATHS = ("/admin", "/reseller")
VPN_OWN_CSRF = frozenset({"/admin/vpn/action", "/reseller/vpn/action"})
FIELD = "_dashboard_csrf"


def install(app):
    if app.extensions.get("epimediahub_dashboard_security"):
        return
    app.extensions["epimediahub_dashboard_security"] = True

    def managed():
        return any(request.path == path or request.path.startswith(path + "/") for path in SAFE_PATHS)

    @app.before_request
    def protect_dashboard_posts():
        if not managed():
            return
        token = session.get(FIELD)
        if not isinstance(token, str) or len(token) < 32:
            token = secrets.token_urlsafe(32)
            session[FIELD] = token
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return
        # The VPN addon already independently validates vpn_csrf on each write.
        if request.path in VPN_OWN_CSRF:
            return
        # All other browser mutations require a same-session secret, including login.
        supplied = request.form.get(FIELD, "") or request.headers.get("X-Dashboard-CSRF", "")
        if not hmac.compare_digest(str(supplied), token):
            abort(403, "Missing or invalid form verification token")

    @app.after_request
    def harden_dashboard_response(response):
        if not managed():
            return response
        response.headers["Cache-Control"] = "no-store, private"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'; base-uri 'self'; object-src 'none'"
        if (response.status_code != 200
                or not response.mimetype == "text/html"
                or response.direct_passthrough):
            return response
        html = response.get_data(as_text=True)
        token = session.get(FIELD, "")
        if not token:
            return response
        hidden = '<input type="hidden" name="_dashboard_csrf" value="' + token + '">'
        def inject(match):
            tag = match.group(0)
            if not METHOD_POST.search(tag):
                return tag
            return tag + hidden
        new_html = FORM.sub(inject, html)
        if new_html != html:
            response.set_data(new_html)
        return response
