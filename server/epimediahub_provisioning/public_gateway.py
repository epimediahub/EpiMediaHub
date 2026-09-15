from __future__ import annotations

import os
import urllib.error
import urllib.request
from flask import Flask, Response, jsonify, request

INTERNAL_BASE_URL = os.environ.get(
    "EPIMEDIAHUB_INTERNAL_URL", "http://100.96.157.82:8787"
).rstrip("/")
UPSTREAM_TIMEOUT = float(os.environ.get("EPIMEDIAHUB_GATEWAY_TIMEOUT", "15"))

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024

ALLOWED = {
    ("GET", "/health"),
    ("POST", "/v1/setup/redeem"),
    ("POST", "/v1/setup/redeem-token"),
    ("GET", "/v1/device/config"),
    ("POST", "/v1/device/sync-result"),
}


def _forward(path: str) -> Response:
    if (request.method, path) not in ALLOWED:
        return jsonify(error="not_found"), 404

    headers = {"Accept": "application/json"}
    auth = request.headers.get("Authorization")
    if auth:
        headers["Authorization"] = auth
    content_type = request.headers.get("Content-Type")
    if content_type:
        headers["Content-Type"] = content_type

    body = request.get_data(cache=False) if request.method != "GET" else None
    upstream = urllib.request.Request(
        INTERNAL_BASE_URL + path,
        data=body,
        headers=headers,
        method=request.method,
    )

    try:
        with urllib.request.urlopen(upstream, timeout=UPSTREAM_TIMEOUT) as response:
            payload = response.read()
            status = response.status
            response_type = response.headers.get("Content-Type", "application/json")
    except urllib.error.HTTPError as error:
        payload = error.read()
        status = error.code
        response_type = error.headers.get("Content-Type", "application/json")
    except (urllib.error.URLError, TimeoutError, OSError):
        return jsonify(error="provisioning_backend_unreachable"), 502

    result = Response(payload, status=status, content_type=response_type)
    result.headers["Cache-Control"] = "no-store"
    return result


@app.get("/health")
def health():
    return _forward("/health")


@app.post("/v1/setup/redeem")
def setup_redeem():
    return _forward("/v1/setup/redeem")


@app.post("/v1/setup/redeem-token")
def setup_redeem_token():
    return _forward("/v1/setup/redeem-token")


@app.get("/v1/device/config")
def device_config():
    return _forward("/v1/device/config")


@app.post("/v1/device/sync-result")
def device_sync_result():
    return _forward("/v1/device/sync-result")


@app.errorhandler(404)
def not_found(_error):
    return jsonify(error="not_found"), 404


@app.errorhandler(405)
def method_not_allowed(_error):
    return jsonify(error="method_not_allowed"), 405


@app.after_request
def security_headers(response: Response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8790")))
