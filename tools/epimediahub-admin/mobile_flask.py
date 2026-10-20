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
from datetime import date, datetime, timezone, timedelta
from io import BytesIO

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
from expiry_cache import read_verified, Unavailable as ExpiryUnavailable
from expiry_report_rows import linked_expiries
from expiry_report_calendar import weekly_entries

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
        "sync-device","move-device","assign-reseller","delete-playlist",
        "add-playlist","edit-playlist"
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


def _expiry_entries():
    # Fails closed if no provider-verified snapshot has been installed;
    # an empty or absent feed is never silently reported as "no expirations".
    observations=read_verified(
        _base()/"admin-mobile"/"expiry-cache.sqlite3")
    if not observations:
        raise ExpiryUnavailable("provider results unavailable")
    now=datetime.now(timezone.utc)
    if not any(-300 <= (now-x.observed_at).total_seconds() <= 48*3600
               for x in observations):
        raise ExpiryUnavailable("provider results stale")
    return linked_expiries(_base()/"provisioning.db",observations,now)


def _month_period():
    y=request.args.get("year","")
    m=request.args.get("month","")
    if (not y.isascii() or not y.isdecimal() or len(y)!=4
            or not m.isascii() or not m.isdecimal() or len(m)>2
            or not 2000<=int(y)<=2100 or not 1<=int(m)<=12):
        raise ValueError("invalid month")
    return int(y),int(m)


WEB_EXPIRY_HTML = """<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EpiMediaHub Admin · Ablaufübersicht</title>
<style>
:root{color-scheme:light}body{font:15px system-ui,Arial,sans-serif;margin:0;background:#f1f4f9;color:#152238}
main{max-width:1030px;margin:0 auto;padding:25px 18px}
header{background:#10243a;color:white;padding:20px;border-radius:15px;margin-bottom:18px}
h1{margin:0 0 7px;font-size:24px}h2{margin:24px 0 12px;font-size:19px}
a{color:#145984}nav{display:flex;gap:14px;flex-wrap:wrap;padding:12px 0}
a.action{display:inline-block;border-radius:9px;background:#145984;color:white;
 padding:10px 14px;text-decoration:none}
section{background:white;border:1px solid #d5deea;border-radius:12px;
padding:13px;margin:12px 0;break-inside:avoid}
table{width:100%;border-collapse:collapse}th,td{padding:11px;text-align:left;
border-bottom:1px solid #e5eaf0}th{background:#edf2f7}
small{color:#4f617a} .error{color:#9f2525;font-weight:600}
@media print {body{background:white}nav{display:none}header{color:#111;background:white}
section{break-before:page}}
</style></head><body><main>
<header><h1>Monats- &amp; Wochenübersichten</h1>
<div>Nur bestätigte Abläufe beim IPTV-Anbieter</div></header>
<nav>
<a href="?year={{ year }}&amp;month={{ month }}">Monat anzeigen</a>
<a href="?kind=week&amp;from={{ monday }}">Aktuelle Woche anzeigen</a>
{% if not weekly %}
<a class="action" href="/admin/mobile/reports/expiry/month.pdf?year={{ year }}&amp;month={{ month }}">Monats-PDF herunterladen / drucken</a>
{% endif %}
</nav>
{% if error %}<p class="error">{{ error|e }}</p>{% else %}
<h2>{{ label|e }} — {{ count }} bestätigte Abläufe</h2>
{% if not groups %}<p>Für diesen Zeitraum sind keine bestätigten Abläufe erfasst.</p>{% endif %}
{% for group in groups %}
<section><h2>{{ group.name|e }} <small>({{ group.entries|length }})</small></h2>
<table><thead><tr><th>Kundenname</th><th>Ablaufdatum</th></tr></thead>
<tbody>{% for entry in group.entries %}
<tr><td>{{ entry.customer|e }}</td><td>{{ entry.day|e }}</td></tr>
{% endfor %}</tbody></table></section>
{% endfor %}
{% endif %}
<small>Vertraulich. Nur im geschützten Administratorbereich.</small>
</main></body></html>"""


@bp.get("/admin/mobile/reports/expiry")
def expiry_report_web():
    """Private desktop report overview on the existing admin host."""
    _require_admin()
    berlin=__import__("zoneinfo").ZoneInfo("Europe/Berlin")
    today=datetime.now(berlin).date()
    next_month=(today.replace(day=1)+timedelta(days=32)).replace(day=1)
    current_monday=today-timedelta(days=today.weekday())
    requested_monday=request.args.get("from",current_monday.isoformat())
    weekly=request.args.get("kind","month")=="week"
    yr=request.args.get("year",str(next_month.year))
    mo=request.args.get("month",str(next_month.month))
    groups=[]
    error=None
    count=0
    label=""
    try:
        if not yr.isascii() or not yr.isdecimal() or len(yr)!=4 or not (
            2000<=int(yr)<=2100) or not mo.isascii() or not mo.isdecimal() or not 1<=len(mo)<=2 or not 1<=int(mo)<=12:
            raise ValueError()
        year,month=int(yr),int(mo)
        monday=date.fromisoformat(requested_monday)
        if (monday.weekday()!=0 or monday.isoformat()!=requested_monday):
            raise ValueError()
        result=_expiry_entries()
        if weekly:
            grouped=weekly_entries(result,monday)
            label=monday.strftime("%d.%m.%Y")+" – "+(
                monday+timedelta(days=6)).strftime("%d.%m.%Y")
        else:
            grouped={}
            for item in result:
                if (item.day.year,item.day.month)==(year,month):
                    grouped.setdefault(item.playlist,[]).append(item)
            label=f"{year}-{month:02d}"
        for name in sorted(grouped,key=str.casefold):
            entries=[{"customer":item.customer,
                      "day":item.day.strftime("%d.%m.%Y")}
                     for item in sorted(grouped[name],
                        key=lambda x:(x.day,x.customer.casefold()))]
            groups.append({"name":name,"entries":entries})
            count+=len(entries)
    except ValueError:
        abort(400)
    except (ExpiryUnavailable,sqlite3.Error,OSError,RuntimeError):
        error="Ablaufdaten des Anbieters sind derzeit nicht bestätigt."
    html=render_template_string(WEB_EXPIRY_HTML,year=year,month=month,
        monday=monday.isoformat(),weekly=weekly,label=label,
        count=count,groups=groups,error=error)
    from flask import make_response
    reply=make_response(html,503 if error else 200)
    reply.headers["Cache-Control"]="private, no-store"
    reply.headers["X-Frame-Options"]="DENY"
    reply.headers["X-Content-Type-Options"]="nosniff"
    reply.headers["Content-Security-Policy"]="default-src 'none'; style-src 'unsafe-inline'"
    return reply


@bp.get("/admin/mobile/reports/expiry/month")
def expiry_month_json():
    _require_admin()
    try:
        year,month=_month_period()
        records=[row for row in _expiry_entries()
                 if (row.day.year,row.day.month)==(year,month)]
    except ValueError:
        return _response({"error":"invalid_month"},400)
    except (ExpiryUnavailable,sqlite3.Error,OSError,RuntimeError):
        return _response({"error":"provider_expiry_unavailable"},503)
    data={}
    for row in records:
        data.setdefault(row.playlist,[]).append({
            "customer":row.customer,"expires_on":row.day.isoformat()})
    return _response({"year":year,"month":month,
        "playlists":[{"name":name,"entries":data[name]}
            for name in sorted(data,key=str.casefold)],
        "count":len(records),"source":"verified_provider_only"})


@bp.get("/admin/mobile/reports/expiry/week")
def expiry_week_json():
    _require_admin()
    value=request.args.get("from","")
    try:
        if len(value)!=10 or date.fromisoformat(value).isoformat()!=value:
            raise ValueError("invalid date")
        monday=date.fromisoformat(value)
        if monday.weekday()!=0:
            raise ValueError("not Monday")
        groups=weekly_entries(_expiry_entries(),monday)
    except ValueError:
        return _response({"error":"invalid_week"},400)
    except (ExpiryUnavailable,sqlite3.Error,OSError,RuntimeError):
        return _response({"error":"provider_expiry_unavailable"},503)
    return _response({"week_start":monday.isoformat(),
        "week_end":(monday+timedelta(days=6)).isoformat(),
        "playlists":[{"name":name,"entries":[
            {"customer":r.customer,"expires_on":r.day.isoformat()}
            for r in rows]} for name,rows in groups.items()],
        "count":sum(map(len,groups.values())),"source":"verified_provider_only"})


@bp.get("/admin/mobile/reports/expiry/month.pdf")
def expiry_month_pdf():
    _require_admin()
    try:
        year,month=_month_period()
        records=_expiry_entries()
        from expiry_report_pdf import monthly_pdf
        output=BytesIO()
        monthly_pdf(records,year,month,output)
        if output.tell()>8*1024*1024:
            raise ExpiryUnavailable("PDF too large")
        output.seek(0)
    except ValueError:
        return _response({"error":"invalid_month"},400)
    except (ExpiryUnavailable,ImportError,sqlite3.Error,OSError,RuntimeError):
        return _response({"error":"provider_expiry_unavailable"},503)
    response=send_file(output,as_attachment=True,
        download_name=f"epimediahub-ablauf-{year}-{month:02d}.pdf",
        mimetype="application/pdf",max_age=0,conditional=False)
    response.headers["Cache-Control"]="private, no-store"
    response.headers["Pragma"]="no-cache"
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["X-Frame-Options"]="DENY"
    return response


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
