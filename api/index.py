# -*- coding: utf-8 -*-
"""Vercel entrypoint for مذكرتي الذكية.

The original app.py is a local BaseHTTPRequestHandler server. Vercel expects
serverless/WSGI style handlers, so this file adapts the same functions to Flask.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_file

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app as core  # noqa: E402

# Vercel's deployed project files are read-only. Use /tmp for the local mirror,
# while Supabase remains the durable cloud store when env vars are configured.
core.VAULT = Path(os.environ.get("VAULT_PATH", "/tmp/mudhakkirati_vault")).expanduser()
core.PASSCODE = str(os.environ.get("PASSCODE", os.environ.get("MUDHAKKIRATI_PASSCODE", core.PASSCODE)))

app = Flask(__name__)


def json_response(obj, status: int = 200):
    return Response(
        json.dumps(obj, ensure_ascii=False),
        status=status,
        mimetype="application/json; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


def authorized() -> bool:
    if request.path in {"/api/auth", "/manifest.webmanifest", "/sw.js", "/icon.svg", "/"}:
        return True
    return request.headers.get("X-Passcode", "") == core.PASSCODE


@app.get("/")
def index():
    return send_file(core.STATIC / "index.html", mimetype="text/html; charset=utf-8")


@app.get("/manifest.webmanifest")
def manifest():
    return send_file(core.STATIC / "manifest.webmanifest", mimetype="application/manifest+json; charset=utf-8")


@app.get("/sw.js")
def service_worker():
    return send_file(core.STATIC / "sw.js", mimetype="application/javascript; charset=utf-8")


@app.get("/icon.svg")
def icon():
    return send_file(core.STATIC / "icon.svg", mimetype="image/svg+xml; charset=utf-8")


@app.post("/api/auth")
def auth():
    data = request.get_json(silent=True) or {}
    return jsonify({"ok": str(data.get("passcode", "")) == core.PASSCODE})


@app.before_request
def check_auth():
    if request.path.startswith("/api/") and not authorized():
        return json_response({"ok": False, "error": "رمز الدخول غير صحيح"}, 401)
    return None


@app.get("/api/status")
def status():
    return json_response(core.status())


@app.get("/api/search")
def search():
    return json_response(core.search(request.args.get("q", "")))


@app.get("/api/resolve-link")
def resolve_link():
    q = request.args.get("q", "")
    resolved = core.resolve_site_query(q)
    url = resolved.get("url") or q
    return json_response({
        "ok": True,
        "url": url,
        "title": resolved.get("title") or core.title_from_url(url),
        "kind": core.infer_link_kind(url),
        "image": core.site_image_url(url),
    })


@app.get("/api/trackers")
def trackers():
    return json_response(core.list_trackers())


@app.get("/api/sync-from-supabase")
def sync_from_supabase():
    return json_response(core.sync_from_supabase())


@app.get("/api/open-url")
def open_url():
    rel = request.args.get("path", "")
    target = core.VAULT / rel
    url = "obsidian://open?path=" + urllib.parse.quote(str(target))
    return json_response({"ok": True, "url": url})


def body() -> dict:
    return request.get_json(silent=True) or {}


@app.post("/api/save-note")
def save_note():
    try:
        return json_response(core.save_note(body()))
    except Exception as exc:
        return json_response({"ok": False, "error": str(exc)}, 500)


@app.post("/api/save-link")
def save_link():
    try:
        return json_response(core.save_link(body()))
    except Exception as exc:
        return json_response({"ok": False, "error": str(exc)}, 500)


@app.post("/api/save-place")
def save_place():
    try:
        return json_response(core.save_place(body()))
    except Exception as exc:
        return json_response({"ok": False, "error": str(exc)}, 500)


@app.post("/api/upsert-tracker")
def upsert_tracker():
    try:
        return json_response(core.upsert_tracker(body()))
    except Exception as exc:
        return json_response({"ok": False, "error": str(exc)}, 500)


@app.post("/api/add-tracker-entry")
def add_tracker_entry():
    try:
        return json_response(core.add_tracker_entry(body()))
    except Exception as exc:
        return json_response({"ok": False, "error": str(exc)}, 500)


@app.errorhandler(404)
def not_found(_):
    # Keep PWA refreshes working.
    if not request.path.startswith("/api/"):
        return index()
    return json_response({"ok": False, "error": "Not found"}, 404)
