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
    if request.path in {"/api/auth", "/api/reset-passcode", "/manifest.webmanifest", "/sw.js", "/icon.svg", "/"}:
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


CATEGORY_TABLES = {
    "note-types": (core.get_note_types, core.add_note_type, core.remove_note_type),
    "moods": (core.get_moods, core.add_mood, core.remove_mood),
    "place-categories": (core.get_place_categories, core.add_place_category, core.remove_place_category),
    "link-types": (core.get_link_types, core.add_link_type, core.remove_link_type),
}


def category_route(category: str):
    if request.method == "GET":
        get_fn, _, _ = CATEGORY_TABLES[category]
        return json_response(get_fn())
    elif request.method == "POST":
        data = request.get_json(silent=True) or {}
        name = data.get("name", "").strip()
        if not name:
            return json_response({"ok": False, "error": "الاسم فارغ"}, 400)
        _, add_fn, _ = CATEGORY_TABLES[category]
        result = add_fn(name)
        return json_response(result, 200 if result.get("ok") else 400)


def category_delete_route(category: str, name: str):
    _, _, remove_fn = CATEGORY_TABLES[category]
    result = remove_fn(name)
    return json_response(result, 200 if result.get("ok") else 400)


for cat_key in CATEGORY_TABLES:
    app.add_url_rule(f"/api/categories/{cat_key}",
                     view_func=lambda c=cat_key: category_route(c),
                     methods=["GET", "POST"],
                     endpoint=f"cat_list_{cat_key}")
    app.add_url_rule(f"/api/categories/{cat_key}/<path:name>",
                     view_func=lambda c=cat_key, n="": category_delete_route(c, n),
                     methods=["DELETE"],
                     endpoint=f"cat_del_{cat_key}")


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


@app.post("/api/reset-passcode")
def reset_passcode():
    """إعادة تعيين رمز الدخول إلى 000000 (دون الحاجة للرمز القديم)."""
    result = core.change_passcode("000000")
    return json_response(result, 200 if result.get("ok") else 400)


@app.post("/api/change-passcode")
def change_passcode():
    data = request.get_json(silent=True) or {}
    new_code = data.get("passcode", "")
    result = core.change_passcode(new_code)
    return json_response(result, 200 if result.get("ok") else 400)


# ─── تصدير البيانات ───


@app.get("/api/export/<data_type>")
def export(data_type: str):
    fmt = request.args.get("format", "docx")
    if fmt not in ("docx", "pdf", "txt"):
        return json_response({"ok": False, "error": "الصيغة غير مدعومة. استخدم docx, pdf, txt"}, 400)
    try:
        result = core.export_data(data_type, fmt)
        if not result.get("ok"):
            return json_response(result, 400)
        return Response(
            result["blob"],
            status=200,
            mimetype=result["mime"],
            headers={
                "Content-Disposition": f'attachment; filename="{result["filename"]}"',
                "Cache-Control": "no-store",
            },
        )
    except Exception as exc:
        return json_response({"ok": False, "error": str(exc)}, 500)


@app.errorhandler(404)
def not_found(_):
    # Keep PWA refreshes working.
    if not request.path.startswith("/api/"):
        return index()
    return json_response({"ok": False, "error": "Not found"}, 404)
