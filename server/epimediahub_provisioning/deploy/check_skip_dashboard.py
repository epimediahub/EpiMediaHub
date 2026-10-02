"""Render the installed intro dashboard against a read-only database snapshot.

This is a local installation check. It never starts a server or changes the
authentication settings of the running application.
"""
from __future__ import annotations

import contextlib
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def check(database, templates):
    from flask import Flask, jsonify
    import skip_markers

    with tempfile.TemporaryDirectory(prefix="epimediahub-dashboard-check-") as directory:
        snapshot = Path(directory) / "dashboard.db"
        with contextlib.closing(sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True)) as source:
            with contextlib.closing(sqlite3.connect(snapshot)) as target:
                source.backup(target)

        @contextlib.contextmanager
        def db():
            con = sqlite3.connect(snapshot.as_uri() + "?mode=ro", uri=True)
            con.row_factory = sqlite3.Row
            try:
                yield con
            finally:
                con.close()

        site = Flask("skip-installation-check", template_folder=str(Path(templates).resolve()))
        site.secret_key = "local-render-check"
        site.testing = True
        site.add_url_rule("/dashboard", "dashboard", lambda: "Dashboard")
        site.add_url_rule("/health", "health", lambda: jsonify(status="ok"))
        backend = types.ModuleType("app")
        backend.digest = lambda value: value
        backend.web_auth = lambda: None
        with mock.patch.dict(sys.modules, {"app": backend}), mock.patch.object(skip_markers, "migrate"):
            skip_markers.install(site, db)
        response = site.test_client().get("/admin/skip")
        if response.status_code != 200 or "Serienfortschritt" not in response.get_data(as_text=True):
            raise RuntimeError("Intro dashboard did not render")


if __name__ == "__main__":
    try:
        check(sys.argv[1], sys.argv[2])
    except Exception as error:
        raise SystemExit("Intro-Dashboard konnte mit dem vorhandenen Datenbestand nicht geladen werden (" + type(error).__name__ + ").") from None
    print("Intro-Dashboard mit vorhandenem Datenbestand erfolgreich geladen.")
