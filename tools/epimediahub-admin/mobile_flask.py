"""Flask integration for private EpiMediaHub Admin Android app.

Installed only on the provisioning/dashboard host, AFTER login + CSRF middleware.
An administrator web session remains the sole authentication authority. No
bearer admin API token, Firebase service credentials or customer secrets are
ever returned to the Android client.
"""
from __future__ import annotations

import hmac
import os
from pathlib import Path
import secrets

from flask import Blueprint, abort, jsonify, redirect, render_template_string, request, session, url_for
from incident_store import IncidentStore
from mobile_registry import AdminMobileRegistry

bp=Blueprint("epimediahub_admin_mobile",__name__)
ALLOWED_KEYS=frozenset({"installation_id","fcm_token","platform"})
CSRF="_dashboard_csrf"

HTML="""<!doctype html><html lang="de"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EpiMediaHub Admin – Meldungen</title>
<style>
body{background:#101827;color:#edf4fb;font:15px system-ui;margin:0;padding:16px}
a{color:#a6dbff} .head{display:flex;justify-content:space-between;gap:12px}
h1{font-size:21px} .item{border:1px solid #344660;background:#1a283b;
border-radius:12px;padding:14px;margin:11px 0}
.meta{font-size:12px;color:#b7cce1} .critical{border-left:5px solid #ed7777}
.warning{border-left:5px solid #e4b36b}.info{border-left:5px solid #77baff}
button{background:#315b95;border:0;color:white;padding:9px 12px;border-radius:8px}
small{color:#a1b1c3}form{margin-top:10px}
</style><body>
<div class="head"><h1>Admin · Meldungen</h1><a href="/admin/diagnostics">Diagnose</a></div>
<small>Nur bestätigte Alarmzustände. Ausbleibende Messwerte gelten nicht als Entwarnung.</small>
{% if not incidents %}<p>Zurzeit keine offenen oder bestätigten Meldungen im Alarmregister.</p>{% endif %}
{% for item in incidents %}
<section class="item {{ item['severity']|e }}">
 <strong>{{ item['message']|e }}</strong>
 <p class="meta">{{ item['kind']|e }} · {{ item['state']|e }}
 · Letzte Erkennung: {{ item['last_seen_epoch']|int }}</p>
 {% if item['state']=='open' %}
 <form action="{{ url_for('epimediahub_admin_mobile.ack',key=item['alert_key']) }}"
 method="post"><input type="hidden" name="_dashboard_csrf" value="{{ csrf|e }}">
 <button type="submit">Zur Kenntnis genommen</button></form>
 {% endif %}
</section>
{% endfor %}
</body></html>"""


def _base():
    value=Path(os.environ.get("EPIMEDIAHUB_DATA_DIR","/var/lib/epimediahub"))
    if value.is_symlink():
        raise PermissionError("Unexpected linked data directory")
    return value

def _require_admin():
    if not session.get("admin"):
        abort(401)

def _csrf():
    value=session.get(CSRF)
    if not isinstance(value,str) or len(value)<32:
        value=secrets.token_urlsafe(32)
        session[CSRF]=value
    return value

def _require_csrf():
    supplied=request.headers.get("X-Dashboard-CSRF","") or request.form.get(CSRF,"")
    if not hmac.compare_digest(str(supplied),_csrf()):
        abort(403)

def _registry():
    return AdminMobileRegistry(_base()/"admin-mobile"/"registrations.sqlite3")

def _incidents():
    return IncidentStore(_base()/"admin-mobile"/"incidents.sqlite3")

def _response(data,status=200):
    response=jsonify(data)
    response.headers["Cache-Control"]="private, no-store"
    response.headers["X-Content-Type-Options"]="nosniff"
    return response,status

@bp.get("/admin/mobile/bootstrap")
def bootstrap():
    _require_admin()
    return _response({"csrf":_csrf(),
       "push_available":bool(os.environ.get("EPIMEDIAHUB_ADMIN_FCM_PROJECT_ID")),
       "app":"EpiMediaHub Admin"})

@bp.post("/admin/mobile/register")
def register():
    _require_admin()
    _require_csrf()
    if not os.environ.get("EPIMEDIAHUB_ADMIN_FCM_PROJECT_ID"):
        return _response({"error":"push_not_configured"},503)
    if (request.content_length is None or request.content_length>5500
        or not request.is_json):
        return _response({"error":"invalid_request"},400)
    data=request.get_json(silent=True)
    if not isinstance(data,dict) or set(data)!=ALLOWED_KEYS or data.get("platform")!="android-admin":
        return _response({"error":"invalid_fields"},400)
    try:
        _registry().register(data["installation_id"],data["fcm_token"])
    except (ValueError,TypeError,PermissionError):
        return _response({"error":"invalid_installation_or_token"},400)
    return _response({"registered":True},201)

@bp.post("/admin/mobile/unregister")
def unregister():
    _require_admin()
    _require_csrf()
    data=request.get_json(silent=True)
    if not isinstance(data,dict) or set(data)!={"installation_id"}:
        return _response({"error":"invalid_fields"},400)
    _registry().unregister(data["installation_id"])
    return _response({"registered":False})

@bp.get("/admin/mobile/alerts")
def alerts():
    if not session.get("admin"):
        return redirect(url_for("login",next=request.path))
    incidents=_incidents().open_incidents()[:120]
    html=render_template_string(HTML,incidents=incidents,csrf=_csrf())
    response=bp.make_response(html) if hasattr(bp,"make_response") else None
    from flask import make_response
    result=make_response(html)
    result.headers["Cache-Control"]="no-store, private"
    result.headers["X-Content-Type-Options"]="nosniff"
    result.headers["X-Frame-Options"]="DENY"
    return result

@bp.post("/admin/mobile/ack/<path:key>")
def ack(key):
    _require_admin()
    _require_csrf()
    if len(key)>200 or not key:
        abort(400)
    _incidents().acknowledge(key,int(__import__("time").time()))
    return redirect(url_for("epimediahub_admin_mobile.alerts"),code=303)

@bp.get("/admin/mobile/alerts.json")
def alerts_json():
    _require_admin()
    return _response({"incidents":_incidents().open_incidents()[:120]})

def install(app):
    if "epimediahub_admin_mobile" not in app.blueprints:
        app.register_blueprint(bp)
