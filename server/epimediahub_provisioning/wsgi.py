from __future__ import annotations

from datetime import datetime, timezone

from flask import render_template

from app import app, db, digest
import device_api  # registers /v1/device/* and migrations


@app.get("/connect/<token>")
def connect_page(token: str):
    token = token.strip()
    if not token:
        return render_template("connect.html", state="invalid"), 404

    with db() as con:
        row = con.execute(
            """
            SELECT a.expires_at, a.redeemed_at, c.name customer_name, c.enabled customer_enabled
            FROM activations a
            JOIN customers c ON c.id = a.customer_id
            WHERE a.token_hash = ?
            """,
            (digest(token),),
        ).fetchone()

    if row is None or not row["customer_enabled"]:
        return render_template("connect.html", state="invalid"), 404
    if row["redeemed_at"] is not None:
        return render_template("connect.html", state="used", customer_name=row["customer_name"]), 409

    expires = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
    if expires <= datetime.now(timezone.utc):
        return render_template("connect.html", state="expired", customer_name=row["customer_name"]), 410

    deep_link = f"epimediahub://connect?token={token}"
    return render_template(
        "connect.html",
        state="ready",
        customer_name=row["customer_name"],
        deep_link=deep_link,
        expires_at=row["expires_at"],
    )
