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

# ─── دوال تخزين رمز الدخول في Supabase ───


def _supabase_get_passcode() -> str | None:
    """قراءة رمز الدخول من Supabase (نظام key-value في جدول notes)."""
    try:
        resp = core.supabase_request("GET", "/rest/v1/notes?local_id=eq.__system_passcode__&select=metadata&limit=1")
        if resp.get("ok") and isinstance(resp.get("data"), list) and len(resp["data"]) > 0:
            meta = resp["data"][0].get("metadata") or {}
            return meta.get("passcode")
    except Exception:
        pass
    return None


def _supabase_save_passcode(passcode: str) -> bool:
    """حفظ رمز الدخول في Supabase كـ metadata في سجل خاص."""
    try:
        # Check if system row exists
        meta = {"passcode": passcode}
        resp = core.supabase_request("GET", "/rest/v1/notes?local_id=eq.__system_passcode__&select=id&limit=1")
        if resp.get("ok") and isinstance(resp.get("data"), list) and len(resp["data"]) > 0:
            # Update existing
            sid = resp["data"][0]["id"]
            upd = core.supabase_request("PATCH", f"/rest/v1/notes?id=eq.{sid}", {"metadata": meta})
            return upd.get("ok", False)
        else:
            # Insert new
            from datetime import datetime
            ins = core.supabase_request("POST", "/rest/v1/notes", {
                "local_id": "__system_passcode__",
                "title": "إعدادات النظام",
                "metadata": meta,
                "date": datetime.now().isoformat(),
            })
            return ins.get("ok", False)
    except Exception:
        pass
    return False


# Vercel's deployed project files are read-only. Use /tmp for the local mirror,
# while Supabase remains the durable cloud store when env vars are configured.
core.VAULT = Path(os.environ.get("VAULT_PATH", "/tmp/mudhakkirati_vault")).expanduser()
core.PASSCODE = str(os.environ.get("PASSCODE", os.environ.get("MUDHAKKIRATI_PASSCODE", core.PASSCODE)))

# Check if Supabase has a stored passcode (overrides env var for persistence)
supabase_pc = _supabase_get_passcode()
if supabase_pc:
    core.PASSCODE = supabase_pc

# رمز دخول ثابت للطوارئ إلى أن يتم ضبط PASSCODE/Supabase نهائياً على Vercel.
# هذا يمنع قفل المستخدم خارج التطبيق بعد cold start.
FALLBACK_PASSCODE = "10101"

app = Flask(__name__)


def json_response(obj, status: int = 200):
    return Response(
        json.dumps(obj, ensure_ascii=False),
        status=status,
        mimetype="application/json; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


def _normalize_passcode(value: str) -> str:
    """Normalize Arabic/Persian numerals to ASCII digits for mobile Arabic keyboards."""
    table = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
    return str(value or "").strip().translate(table)


def _valid_passcode(value: str) -> bool:
    value = _normalize_passcode(value)
    return value in {_normalize_passcode(core.PASSCODE), _normalize_passcode(FALLBACK_PASSCODE)}


def authorized() -> bool:
    if request.path in {"/api/auth", "/api/reset-passcode", "/fix-login", "/manifest.webmanifest", "/sw.js", "/icon.svg", "/"}:
        return True
    return _valid_passcode(request.headers.get("X-Passcode", ""))


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


@app.get("/fix-login")
def fix_login():
    html = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>إصلاح الدخول</title>
<style>
body{font-family:Tahoma,Arial,sans-serif;background:#f7f7fa;color:#222;display:grid;place-items:center;min-height:100vh;margin:0;padding:20px;text-align:center}
.box{background:white;border:1px solid #ddd;border-radius:22px;padding:24px;max-width:520px;box-shadow:0 18px 50px rgba(0,0,0,.10)}
button,a{display:inline-block;margin:10px;padding:14px 18px;border-radius:14px;border:0;background:#2f7df6;color:white;text-decoration:none;font-weight:bold;font-size:18px}
.small{color:#666;line-height:1.8}
</style>
</head>
<body>
<div class="box">
<h1>جاري إصلاح الدخول…</h1>
<p class="small" id="msg">سأمسح النسخة القديمة وأدخل بالرمز 10101.</p>
<button onclick="fixNow()">إصلاح الدخول الآن</button>
<a href="/?pass=10101&v=force-clean-login">فتح التطبيق</a>
</div>
<script>
async function fixNow(){
  const msg=document.getElementById('msg');
  try{msg.textContent='مسح التخزين المحلي…'; localStorage.clear(); sessionStorage.clear();}catch(e){}
  try{msg.textContent='مسح الكاش…'; if(window.caches){let keys=await caches.keys(); await Promise.all(keys.map(k=>caches.delete(k)));}}catch(e){}
  try{msg.textContent='إلغاء service worker القديم…'; if(navigator.serviceWorker){let regs=await navigator.serviceWorker.getRegistrations(); await Promise.all(regs.map(r=>r.unregister()));}}catch(e){}
  try{localStorage.setItem('mudhakkirati_passcode','10101');}catch(e){}
  msg.textContent='تم الإصلاح. سيتم فتح التطبيق الآن…';
  setTimeout(()=>{location.replace('/?pass=10101&v=force-clean-login-'+Date.now())},700);
}
fixNow();
</script>
</body></html>"""
    return Response(
        html,
        status=200,
        mimetype="text/html; charset=utf-8",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.post("/api/auth")
def auth():
    data = request.get_json(silent=True) or {}
    return jsonify({"ok": _valid_passcode(str(data.get("passcode", "")))})


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
    "tracker-types": (core.get_tracker_types, core.add_tracker_type, core.remove_tracker_type),
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
                     view_func=lambda name, c=cat_key: category_delete_route(c, name),
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
    if result.get("ok"):
        core.PASSCODE = "000000"
        result["supabase_saved"] = _supabase_save_passcode("000000")
    return json_response(result, 200 if result.get("ok") else 400)


@app.post("/api/change-passcode")
def change_passcode():
    data = request.get_json(silent=True) or {}
    new_code = str(data.get("passcode", "")).strip()
    result = core.change_passcode(new_code)
    if result.get("ok"):
        core.PASSCODE = new_code
        result["supabase_saved"] = _supabase_save_passcode(new_code)
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
