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
import sqlite3

from flask import Blueprint, abort, jsonify, redirect, render_template_string, request, session, url_for, send_file
from incident_store import IncidentStore
from mobile_registry import AdminMobileRegistry
from mobile_updates import read_release
from native_status import read_status
from native_management_data import (SchemaUnavailable, overview as native_overview,
    customers as native_customers, resellers as native_resellers,
    customer_detail as native_customer_detail,
    reseller_detail as native_reseller_detail,
    device_diagnostics as native_device_diagnostics)
from native_management_actions import invoke_grant, valid_confirmation
from native_legacy_bridge import invoke_legacy, LegacyUnavailable
from native_management_edits import rename as native_rename, EditUnavailable

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
    folder=_base()/"admin-mobile"
    if folder.is_symlink():
        raise PermissionError("Unexpected linked incident directory")
    folder.mkdir(mode=0o700,parents=True,exist_ok=True)
    if folder.stat().st_mode & 0o077:
        raise PermissionError("Incident directory is not private")
    return IncidentStore(folder/"incidents.sqlite3")

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
    try:
        _registry().unregister(data["installation_id"])
    except (PermissionError, ValueError, TypeError):
        return _response({"error":"invalid_installation"},400)
    return _response({"registered":False})

@bp.get("/admin/mobile/alerts")
def alerts():
    if not session.get("admin"):
        return redirect(url_for("login",next=request.path))
    incidents=_incidents().open_incidents()[:120]
    html=render_template_string(HTML,incidents=incidents,csrf=_csrf())
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

@bp.post("/admin/mobile/alerts/ack")
def ack_json():
    _require_admin()
    _require_csrf()
    if (request.content_length is None or request.content_length>400
            or not request.is_json):
        return _response({"error":"invalid_request"},400)
    data=request.get_json(silent=True)
    if (not isinstance(data,dict) or set(data)!={"alert_key"}
            or not isinstance(data["alert_key"],str)
            or not 1<=len(data["alert_key"])<=200):
        return _response({"error":"invalid_alert_key"},400)
    acknowledged=_incidents().acknowledge(data["alert_key"],int(__import__("time").time()))
    return _response({"acknowledged":acknowledged})


@bp.get("/admin/mobile/alerts.json")
def alerts_json():
    _require_admin()
    return _response({"incidents":_incidents().open_incidents()[:120]})


@bp.get("/admin/mobile/episcene/status")
def episcene_status():
    _require_admin()
    try:
        result=read_status(_base()/"provisioning.db")
    except (RuntimeError,OSError,ValueError):
        return _response({"error":"analysis_status_unavailable"},503)
    return _response(result)


@bp.get("/admin/mobile/management/overview")
def native_management_overview():
    _require_admin()
    try:
        return _response(native_overview(_base()/"provisioning.db"))
    except (SchemaUnavailable, RuntimeError, sqlite3.Error, OSError, ValueError):
        return _response({"error":"management_unavailable"},503)


@bp.get("/admin/mobile/management/customers")
def native_management_customers():
    _require_admin()
    query=request.args.get("q","")
    cursor=request.args.get("before_id")
    if not isinstance(query,str) or len(query)>80:
        return _response({"error":"invalid_query"},400)
    if (cursor is not None and (not cursor or len(cursor)>18 or
            not cursor.isascii() or not cursor.isdecimal() or int(cursor)<1)):
        return _response({"error":"invalid_cursor"},400)
    try:
        return _response(native_customers(_base()/"provisioning.db",
            query=query,before_id=int(cursor) if cursor is not None else None))
    except (SchemaUnavailable, RuntimeError, sqlite3.Error, OSError, ValueError):
        return _response({"error":"management_unavailable"},503)


@bp.get("/admin/mobile/management/resellers")
def native_management_resellers():
    _require_admin()
    query=request.args.get("q","")
    cursor=request.args.get("before_id")
    if not isinstance(query,str) or len(query)>80:
        return _response({"error":"invalid_query"},400)
    if (cursor is not None and (not cursor or len(cursor)>18 or
            not cursor.isascii() or not cursor.isdecimal() or int(cursor)<1)):
        return _response({"error":"invalid_cursor"},400)
    try:
        return _response(native_resellers(_base()/"provisioning.db",
            query=query,before_id=int(cursor) if cursor is not None else None))
    except (SchemaUnavailable, RuntimeError, sqlite3.Error, OSError, ValueError):
        return _response({"error":"management_unavailable"},503)


@bp.get("/admin/mobile/management/customers/<int:customer_id>")
def native_management_customer_detail(customer_id):
    _require_admin()
    try:
        data=native_customer_detail(_base()/"provisioning.db",customer_id)
    except (SchemaUnavailable, RuntimeError, sqlite3.Error, OSError, ValueError):
        return _response({"error":"management_unavailable"},503)
    return _response(data) if data is not None else _response({"error":"not_found"},404)


@bp.get("/admin/mobile/management/resellers/<int:reseller_id>")
def native_management_reseller_detail(reseller_id):
    _require_admin()
    try:
        data=native_reseller_detail(_base()/"provisioning.db",reseller_id)
    except (SchemaUnavailable, RuntimeError, sqlite3.Error, OSError, ValueError):
        return _response({"error":"management_unavailable"},503)
    return _response(data) if data is not None else _response({"error":"not_found"},404)


@bp.get("/admin/mobile/management/devices/<int:device_row_id>/diagnostics")
def native_device_diagnostics_api(device_row_id):
    _require_admin()
    try:
        value=native_device_diagnostics(_base()/"provisioning.db",device_row_id)
    except (SchemaUnavailable,RuntimeError,sqlite3.Error,OSError,ValueError):
        return _response({"error":"diagnostics_unavailable"},503)
    return _response(value) if value is not None else _response({"error":"not_found"},404)


@bp.post("/admin/mobile/management/<kind>/<int:entity_id>/rename")
def native_management_rename(kind,entity_id):
    _require_admin()
    _require_csrf()
    if kind not in ("customers","resellers"):
        return _response({"error":"unsupported_account_type"},404)
    if (request.content_length is None or request.content_length>1000
            or not request.is_json):
        return _response({"error":"invalid_request"},400)
    data=request.get_json(silent=True)
    if not isinstance(data,dict) or set(data)!={"expected_name","name","request_id"}:
        return _response({"error":"invalid_fields"},400)
    try:
        result,status=native_rename(
            _base()/"provisioning.db",kind,entity_id,
            data["expected_name"],data["name"],data["request_id"])
        return _response(result,status)
    except ValueError:
        return _response({"error":"invalid_fields"},400)
    except (EditUnavailable,RuntimeError,sqlite3.Error,OSError):
        return _response({"error":"rename_unavailable"},503)


@bp.post("/admin/mobile/management/devices/<int:device_row_id>/<action>")
def native_management_grant(device_row_id,action):
    _require_admin()
    _require_csrf()
    if action not in ("grant-year","vpn-trial7"):
        return _response({"error":"unsupported_action"},404)
    if (request.content_length is None or request.content_length>300
            or not request.is_json):
        return _response({"error":"invalid_request"},400)
    data=request.get_json(silent=True)
    if not valid_confirmation(data):
        return _response({"error":"confirmation_required"},400)
    try:
        value,status=invoke_grant(_base()/"provisioning.db",device_row_id,action)
        return _response(value,status)
    except (SchemaUnavailable,RuntimeError,sqlite3.Error,OSError,ValueError):
        return _response({"error":"grant_unavailable"},503)


@bp.post("/admin/mobile/management/actions/<action>/<int:entity_id>")
def native_management_legacy_action(action, entity_id):
    """Native form-data adapter to audited original business handlers.

    Original handlers see their normal request.form; only our JSON reply is
    new. No HTML is rendered in the Android app.
    """
    _require_admin()
    _require_csrf()
    if action not in (
        "create-customer","create-reseller","rename-device",
        "sync-device","move-device","assign-reseller","delete-playlist"
    ):
        return _response({"error":"unsupported_action"},404)
    if (request.content_length is None or request.content_length>3500
            or request.mimetype!="application/x-www-form-urlencoded"):
        return _response({"error":"invalid_request"},400)
    if any(len(request.form.getlist(key))!=1 for key in request.form):
        return _response({"error":"duplicate_form_field"},400)
    try:
        value,status=invoke_legacy(
            _base()/"provisioning.db",action,entity_id,request.form.to_dict())
        return _response(value,status)
    except ValueError:
        return _response({"error":"invalid_fields_or_state"},400)
    except (LegacyUnavailable,SchemaUnavailable,RuntimeError,
            sqlite3.Error,OSError):
        return _response({"error":"business_action_unavailable"},503)


@bp.get("/admin/mobile/update/status")
def update_status():
    _require_admin()
    try:
        release=read_release(_base())
    except (ValueError, PermissionError, OSError):
        return _response({"available":False,"error":"release_unavailable"},503)
    if release is None:
        return _response({"available":False})
    return _response({
        "available":True,
        "package":"de.epimediahub.admin",
        "version_code":release.version_code,
        "version_name":release.version_name,
        "size_bytes":release.size_bytes,
        "sha256":release.sha256,
    })


@bp.get("/admin/mobile/update/apk")
def update_apk():
    _require_admin()
    try:
        release=read_release(_base())
    except (ValueError, PermissionError, OSError):
        abort(503)
    if release is None:
        abort(404)
    response=send_file(release.path, mimetype="application/vnd.android.package-archive",
                       as_attachment=True, download_name="epimediahub-admin.apk",
                       conditional=False, max_age=0)
    response.headers["Cache-Control"]="private, no-store"
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["X-Admin-APK-SHA256"]=release.sha256
    return response

def install(app):
    if "epimediahub_admin_mobile" not in app.blueprints:
        app.register_blueprint(bp)
