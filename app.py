#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""مذكرتي الذكية - PWA محلي لحفظ المذكرات والروابط في ملفات Markdown/Obsidian."""

from __future__ import annotations

import json
import os
import re
import socket
import sys
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
CONFIG_PATH = ROOT / "config.json"

DEFAULT_CONFIG = {
    "vault_path": str(Path.home() / "Documents" / "الأرشيف الشخصي"),
    "port": 9657,
    "passcode": "000000",
}


def load_config() -> dict:
    """Load local config without crashing on read-only hosts such as Vercel."""
    config = DEFAULT_CONFIG.copy()
    if CONFIG_PATH.exists():
        try:
            config.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass
    else:
        # Local desktop runs may create a starter config.json. Serverless hosts have
        # a read-only project filesystem, so failing to write must not crash import.
        try:
            CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
    if os.environ.get("VAULT_PATH"):
        config["vault_path"] = os.environ["VAULT_PATH"]
    if os.environ.get("PORT"):
        config["port"] = os.environ["PORT"]
    if os.environ.get("PASSCODE") or os.environ.get("MUDHAKKIRATI_PASSCODE"):
        config["passcode"] = os.environ.get("PASSCODE") or os.environ.get("MUDHAKKIRATI_PASSCODE")
    return config


CONFIG = load_config()
VAULT = Path(CONFIG["vault_path"]).expanduser()
PASSCODE = str(CONFIG.get("passcode", "000000"))
PORT = int(CONFIG.get("port", 9657))


def load_env_file() -> dict:
    """Load local .env values without requiring external packages."""
    env_path = ROOT / ".env"
    values = {}
    if not env_path.exists():
        return values
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


ENV = load_env_file()
SUPABASE_URL = (ENV.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = (
    ENV.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or ENV.get("SUPABASE_ANON_KEY")
    or os.environ.get("SUPABASE_ANON_KEY")
    or ""
)
SUPABASE_BUCKET = ENV.get("SUPABASE_BUCKET") or os.environ.get("SUPABASE_BUCKET") or "place-photos"


def supabase_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def supabase_request(method: str, endpoint: str, payload=None, extra_headers=None, timeout: int = 10) -> dict:
    """Call Supabase REST/Storage API. Never raises to callers; local saving must keep working."""
    if not supabase_configured():
        return {"ok": False, "status": 0, "error": "Supabase غير مضبوط في ملف .env"}
    url = SUPABASE_URL + endpoint
    data = None
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": "Bearer " + SUPABASE_KEY,
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            try:
                body = json.loads(raw) if raw else None
            except Exception:
                body = raw
            return {"ok": 200 <= resp.status < 300, "status": resp.status, "data": body}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")[:600]
        return {"ok": False, "status": exc.code, "error": raw or exc.reason}
    except Exception as exc:
        return {"ok": False, "status": 0, "error": str(exc)}


def supabase_upsert(table: str, payload: dict, conflict: str = "local_id") -> dict:
    return supabase_request(
        "POST",
        f"/rest/v1/{table}?on_conflict={urllib.parse.quote(conflict)}",
        payload,
        {"Prefer": "resolution=merge-duplicates,return=representation"},
    )


def supabase_insert(table: str, payload: dict) -> dict:
    return supabase_request("POST", f"/rest/v1/{table}", payload, {"Prefer": "return=representation"})


def supabase_select(table: str, query: str = "select=*") -> dict:
    """Read rows from Supabase REST API."""
    return supabase_request("GET", f"/rest/v1/{table}?{query}", None)


# ─── دوال التصنيفات المخصصة (Supabase) ───


def _get_category_table(table: str) -> dict:
    """Get all category names from a Supabase table."""
    res = supabase_select(table, "select=*&order=name.asc")
    if res.get("ok") and isinstance(res.get("data"), list):
        return {"ok": True, "data": [r["name"] for r in res["data"]]}
    return {"ok": False, "data": [], "error": res.get("error")}


def _add_category(table: str, name: str) -> dict:
    """Add a category to Supabase."""
    name = md_escape(name)
    if not name:
        return {"ok": False, "error": "الاسم فارغ"}
    res = supabase_insert(table, {"name": name})
    return {"ok": res.get("ok"), "error": res.get("error")}


def _remove_category(table: str, name: str) -> dict:
    """Remove a category from Supabase by name."""
    safe = urllib.parse.quote(name)
    res = supabase_request("DELETE", f"/rest/v1/{table}?name=eq.{safe}")
    return {"ok": res.get("ok"), "error": res.get("error")}


def get_note_types() -> dict:
    return _get_category_table("note_types")


def add_note_type(name: str) -> dict:
    return _add_category("note_types", name)


def remove_note_type(name: str) -> dict:
    return _remove_category("note_types", name)


def get_moods() -> dict:
    return _get_category_table("moods")


def add_mood(name: str) -> dict:
    return _add_category("moods", name)


def remove_mood(name: str) -> dict:
    return _remove_category("moods", name)


def get_place_categories() -> dict:
    return _get_category_table("place_categories")


def add_place_category(name: str) -> dict:
    return _add_category("place_categories", name)


def remove_place_category(name: str) -> dict:
    return _remove_category("place_categories", name)


def get_link_types() -> dict:
    return _get_category_table("link_types")


def add_link_type(name: str) -> dict:
    return _add_category("link_types", name)


def remove_link_type(name: str) -> dict:
    return _remove_category("link_types", name)


TOPIC_MAP = {
    "النفس والمشاعر": "02 - المذكرات حسب الموضوع/النفس والمشاعر.md",
    "العائلة": "02 - المذكرات حسب الموضوع/العائلة.md",
    "العمل والدراسة": "02 - المذكرات حسب الموضوع/العمل والدراسة.md",
    "الأفكار والمشاريع": "02 - المذكرات حسب الموضوع/الأفكار والمشاريع.md",
    "العلاقات والناس": "02 - المذكرات حسب الموضوع/العلاقات والناس.md",
    "القرارات المهمة": "02 - المذكرات حسب الموضوع/القرارات المهمة.md",
    "الصحة والعادات": "02 - المذكرات حسب الموضوع/الصحة والعادات.md",
    "التأملات الدينية والفكرية": "02 - المذكرات حسب الموضوع/التأملات الدينية والفكرية.md",
}

LINK_KIND_DIR = {
    "YouTube": "07 - الروابط والمواقع/يوتيوب",
    "مقالة": "07 - الروابط والمواقع/مقالات",
    "موقع": "07 - الروابط والمواقع/مواقع",
    "PDF": "07 - الروابط والمواقع/PDF وكتب",
    "أداة": "07 - الروابط والمواقع/أدوات",
    "آخر": "07 - الروابط والمواقع",
}


def ensure_structure() -> None:
    folders = [
        "01 - اليوميات",
        "02 - المذكرات حسب الموضوع",
        "03 - الأشخاص",
        "04 - المشاريع والأهداف",
        "05 - المراجعات",
        "06 - أرشيف",
        "07 - الروابط والمواقع/يوتيوب",
        "07 - الروابط والمواقع/مقالات",
        "07 - الروابط والمواقع/مواقع",
        "07 - الروابط والمواقع/PDF وكتب",
        "07 - الروابط والمواقع/أدوات",
        "08 - الأماكن والمواقع الجغرافية/صور",
        "09 - المتتبعات",
        "قوالب",
    ]
    for folder in folders:
        (VAULT / folder).mkdir(parents=True, exist_ok=True)
    for topic, rel in TOPIC_MAP.items():
        p = VAULT / rel
        if not p.exists():
            p.write_text(f"# {topic}\n\n", encoding="utf-8")
    home = VAULT / "00 - الصفحة الرئيسية.md"
    if not home.exists():
        home.write_text("# الأرشيف الشخصي\n\n- [[01 - اليوميات]]\n- [[07 - الروابط والمواقع/index]]\n", encoding="utf-8")


def slugify_ar(text: str, fallback: str = "مذكرة") -> str:
    text = (text or fallback).strip()
    text = re.sub(r"[\\/:*?\"<>|#%{}$!`&@=+]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:80] or fallback


def md_escape(text: str) -> str:
    return (text or "").replace("\r\n", "\n").strip()


def looks_like_url(raw: str) -> bool:
    value = md_escape(raw).lower()
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", value) or re.match(r"^[\w.-]+\.[a-z]{2,}(/|$)", value))


def normalize_url(raw: str) -> str:
    url = md_escape(raw)
    if url and not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
        url = "https://" + url
    return url


def resolve_site_query(query: str) -> dict:
    """Accept a site name/description and return a best-effort URL + title.

    Uses a small built-in map for common sites, then DuckDuckGo HTML search.
    This keeps the PWA usable when the user writes: "المكتبة الشاملة" instead of a URL.
    """
    q = md_escape(query)
    if not q:
        return {"url": "", "title": ""}
    if looks_like_url(q):
        url = normalize_url(q)
        return {"url": url, "title": title_from_url(url)}

    key = q.lower().strip()
    known = {
        "يوتيوب": ("https://www.youtube.com/", "YouTube"),
        "youtube": ("https://www.youtube.com/", "YouTube"),
        "اوبسيديان": ("https://obsidian.md/", "Obsidian"),
        "obsidian": ("https://obsidian.md/", "Obsidian"),
        "زوتيرو": ("https://www.zotero.org/", "Zotero"),
        "zotero": ("https://www.zotero.org/", "Zotero"),
        "المكتبة الشاملة": ("https://shamela.ws/", "المكتبة الشاملة"),
        "shamela": ("https://shamela.ws/", "المكتبة الشاملة"),
        "github": ("https://github.com/", "GitHub"),
        "جيت هب": ("https://github.com/", "GitHub"),
        "google maps": ("https://maps.google.com/", "Google Maps"),
        "خرائط جوجل": ("https://maps.google.com/", "خرائط جوجل"),
    }
    if key in known:
        url, title = known[key]
        return {"url": url, "title": title}

    try:
        search_url = "https://duckduckgo.com/html/?q=" + urllib.parse.quote(q)
        req = urllib.request.Request(search_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=7) as resp:
            html = resp.read(400_000).decode("utf-8", errors="ignore")
        # DuckDuckGo result links often include uddg=<encoded target>.
        m = re.search(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.I | re.S)
        if m:
            href = m.group(1).replace("&amp;", "&")
            parsed = urllib.parse.urlparse(href)
            qs = urllib.parse.parse_qs(parsed.query)
            target = qs.get("uddg", [href])[0]
            title = re.sub(r"<.*?>", "", m.group(2))
            title = re.sub(r"\s+", " ", title).strip()
            return {"url": target, "title": title or title_from_url(target)}
    except Exception:
        pass

    # Fallback: if user wrote a single Latin domain-like word, try .com.
    if re.match(r"^[a-z0-9-]+$", key):
        url = f"https://{key}.com/"
        return {"url": url, "title": title_from_url(url)}
    return {"url": q, "title": q}


def site_image_url(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.replace("www.", "")
    if not host:
        return ""
    return "https://www.google.com/s2/favicons?domain=" + urllib.parse.quote(host) + "&sz=128"


def reverse_geocode(lat: float, lon: float) -> dict:
    """Coordinates to address using OpenStreetMap/Nominatim."""
    try:
        url = "https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=" + urllib.parse.quote(str(lat)) + "&lon=" + urllib.parse.quote(str(lon)) + "&zoom=18&addressdetails=1"
        req = urllib.request.Request(url, headers={"User-Agent": "MudhakkiratiPWA/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        return {"display_name": data.get("display_name", ""), "address": data.get("address", {})}
    except Exception:
        return {"display_name": "", "address": {}}


def place_title_from_address(address: dict, display_name: str = "") -> str:
    """Build a human place title from street + building number, not coordinates."""
    address = address or {}
    street = (
        address.get("road")
        or address.get("pedestrian")
        or address.get("footway")
        or address.get("path")
        or address.get("residential")
        or address.get("street")
        or ""
    )
    number = address.get("house_number") or address.get("building") or ""
    neighbourhood = (
        address.get("neighbourhood")
        or address.get("suburb")
        or address.get("quarter")
        or address.get("city_district")
        or ""
    )
    city = address.get("city") or address.get("town") or address.get("village") or ""
    parts = []
    if street and number:
        parts.append(f"{street} {number}")
    elif street:
        parts.append(street)
    elif number:
        parts.append(f"بناء {number}")
    if neighbourhood and neighbourhood not in parts:
        parts.append(neighbourhood)
    if city and city not in parts:
        parts.append(city)
    title = " - ".join(str(x).strip() for x in parts if str(x).strip())
    if title:
        return title
    # Last resort: use the beginning of the readable address, never raw lat/lon.
    if display_name:
        return display_name.split(",")[0].strip()
    return "مكان محفوظ"


def maps_url(lat: float, lon: float) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"


def save_data_url_image(data_url: str, stem: str) -> str:
    if not data_url or not data_url.startswith("data:image/"):
        return ""
    import base64
    header, b64 = data_url.split(",", 1)
    ext = header.split("/")[1].split(";")[0].lower()
    if ext == "jpeg":
        ext = "jpg"
    if ext not in {"jpg", "png", "webp", "gif"}:
        ext = "jpg"
    folder = VAULT / "08 - الأماكن والمواقع الجغرافية" / "صور"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{slugify_ar(stem, 'صورة')}.{ext}"
    counter = 2
    while path.exists():
        path = folder / f"{slugify_ar(stem, 'صورة')} ({counter}).{ext}"
        counter += 1
    path.write_bytes(base64.b64decode(b64))
    return rel_for(path)


def save_place(data: dict) -> dict:
    ensure_structure()
    now = datetime.now()
    date = data.get("date") or now.strftime("%Y-%m-%d")
    lat = float(data.get("lat") or 0)
    lon = float(data.get("lon") or 0)
    typed_name = md_escape(data.get("name", ""))
    notes = md_escape(data.get("notes", ""))
    status = md_escape(data.get("status", "للزيارة لاحقًا"))
    category = md_escape(data.get("category", "مكان"))
    rev = reverse_geocode(lat, lon) if lat and lon else {"display_name": "", "address": {}}
    address_title = place_title_from_address(rev.get("address", {}), rev.get("display_name", ""))
    # If the user typed a custom place name, keep it; otherwise name the saved place by street + building number.
    title = slugify_ar(data.get("title") or typed_name or address_title or f"مكان {date}", "مكان محفوظ")
    img_rel = save_data_url_image(data.get("image", ""), f"{date} - {title}")
    img_block = f"![[{img_rel}]]" if img_rel else "—"
    gmap = maps_url(lat, lon) if lat and lon else "—"
    category_tag = re.sub(r"\s+", "_", category)
    content = f"""# {title}

## صورة المكان
{img_block}

## رابط الخريطة
{gmap}

## اسم الحفظ
{address_title or title}

## الإحداثيات
- Latitude: {lat or '—'}
- Longitude: {lon or '—'}

## العنوان التقريبي
{rev.get('display_name') or '—'}

## الاسم الذي كتبته
{typed_name or '—'}

## التصنيف
{category}

## تاريخ الحفظ
{date} {now.strftime('%H:%M')}

## الحالة
{status}

## ملاحظاتي
{notes or '—'}

## وسوم
#مكان #لوكيشن #{category_tag}
"""
    folder = VAULT / "08 - الأماكن والمواقع الجغرافية"
    path = folder / f"{date} - {title}.md"
    counter = 2
    while path.exists():
        path = folder / f"{date} - {title} ({counter}).md"
        counter += 1
    path.write_text(content, encoding="utf-8")
    index = folder / "index.md"
    if not index.exists():
        index.write_text("# الأماكن والمواقع الجغرافية\n\n", encoding="utf-8")
    append(index, f"\n- {date} — [[{path.stem}]] — {gmap}\n")
    supabase = supabase_upsert("places", {
        "local_id": rel_for(path),
        "title": title,
        "typed_name": typed_name,
        "category": category,
        "status": status,
        "notes": notes,
        "lat": lat or None,
        "lon": lon or None,
        "address": rev.get("display_name", ""),
        "maps_url": gmap if gmap != "—" else None,
        "photo_path": img_rel or None,
        "obsidian_path": rel_for(path),
        "date": date,
        "metadata": {"source": "local_pwa", "address_parts": rev.get("address", {})},
    })
    return {"ok": True, "message": "تم حفظ المكان", "path": rel_for(path), "maps_url": gmap, "address": rev.get("display_name", ""), "supabase": supabase}


def trackers_dir() -> Path:
    d = VAULT / "09 - المتتبعات"
    d.mkdir(parents=True, exist_ok=True)
    return d


def tracker_json_path() -> Path:
    return trackers_dir() / "trackers.json"


def load_trackers() -> dict:
    path = tracker_json_path()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {"trackers": []}
    return {"trackers": []}


def write_trackers(data: dict) -> None:
    tracker_json_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def list_trackers() -> dict:
    return {"ok": True, **load_trackers()}


def upsert_tracker(data: dict) -> dict:
    store = load_trackers()
    name = md_escape(data.get("name", "")) or "متتبع جديد"
    unit = md_escape(data.get("unit", ""))
    kind = md_escape(data.get("kind", "رقم"))
    tid = data.get("id") or slugify_ar(name, "tracker")
    found = False
    for t in store["trackers"]:
        if t.get("id") == tid:
            t.update({"name": name, "unit": unit, "kind": kind})
            found = True
    if not found:
        store["trackers"].append({"id": tid, "name": name, "unit": unit, "kind": kind})
    write_trackers(store)
    md = trackers_dir() / f"{slugify_ar(name, 'متتبع')}.md"
    if not md.exists():
        md.write_text(f"# {name}\n\n## النوع\n{kind}\n\n## الوحدة\n{unit or '—'}\n\n## السجل\n\n", encoding="utf-8")
    supabase = supabase_upsert("trackers", {
        "local_id": tid,
        "name": name,
        "kind": kind,
        "unit": unit,
        "obsidian_path": rel_for(md),
        "metadata": {"source": "local_pwa"},
    })
    return {"ok": True, "message": "تم حفظ المتتبع", "tracker": {"id": tid, "name": name, "unit": unit, "kind": kind}, "supabase": supabase}


def add_tracker_entry(data: dict) -> dict:
    store = load_trackers()
    tid = data.get("id") or ""
    tracker = next((t for t in store.get("trackers", []) if t.get("id") == tid), None)
    if not tracker:
        return {"ok": False, "error": "المتتبع غير موجود"}
    date = data.get("date") or datetime.now().strftime("%Y-%m-%d")
    value = md_escape(data.get("value", ""))
    notes = md_escape(data.get("notes", ""))
    tracker.setdefault("entries", []).append({"date": date, "value": value, "notes": notes})
    write_trackers(store)
    md = trackers_dir() / f"{slugify_ar(tracker.get('name'), 'متتبع')}.md"
    append(md, f"- {date}: {value} {tracker.get('unit','')}" + (f" — {notes}" if notes else "") + "\n")
    supabase = supabase_insert("tracker_entries", {
        "tracker_local_id": tid,
        "value": value,
        "notes": notes,
        "date": date,
        "metadata": {"source": "local_pwa", "tracker_name": tracker.get("name", "")},
    })
    return {"ok": True, "message": "تم تسجيل القيمة", "tracker": tracker, "supabase": supabase}


def infer_link_kind(url: str) -> str:
    low = (url or "").lower()
    host = urllib.parse.urlparse(low).netloc.replace("www.", "")
    if "youtube.com" in host or "youtu.be" in host:
        return "YouTube"
    if low.split("?")[0].endswith(".pdf"):
        return "PDF"
    tool_hosts = ("github.com", "colab.research.google.com", "notion.so", "obsidian.md", "zotero.org")
    if any(h in host for h in tool_hosts):
        return "أداة"
    return "موقع"


def title_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.replace("www.", "")
    path_name = urllib.parse.unquote(Path(parsed.path.rstrip("/")).name or "")
    fallback = path_name or host or "رابط محفوظ"
    # محاولة خفيفة لجلب عنوان الصفحة. إذا فشلت، نستخدم اسم الموقع.
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            ctype = resp.headers.get("Content-Type", "")
            if "text/html" in ctype:
                html = resp.read(200_000).decode("utf-8", errors="ignore")
                m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
                if m:
                    title = re.sub(r"\s+", " ", m.group(1)).strip()
                    if title:
                        return title
    except Exception:
        pass
    return fallback


def rel_for(path: Path) -> str:
    try:
        return str(path.relative_to(VAULT))
    except ValueError:
        return str(path)


def append(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(text)


def save_note(data: dict) -> dict:
    ensure_structure()
    now = datetime.now()
    date = data.get("date") or now.strftime("%Y-%m-%d")
    year, month = date[:4], date[5:7]
    note_type = md_escape(data.get("note_type", "يومية"))
    mood = md_escape(data.get("mood", ""))
    cause = md_escape(data.get("cause", ""))
    body = md_escape(data.get("body", ""))
    action = md_escape(data.get("action", "حفظ فقط"))
    topics = data.get("topics") or []
    tags = data.get("tags") or []
    title = slugify_ar(data.get("title") or f"{note_type} - {mood or date}")

    daily = VAULT / "01 - اليوميات" / year / month / f"{date}.md"
    if not daily.exists():
        daily.parent.mkdir(parents=True, exist_ok=True)
        daily.write_text(f"# يومية {date}\n\n", encoding="utf-8")

    wikilinks = "\n".join(f"- [[{t}]]" for t in topics)
    tag_line = " ".join("#" + re.sub(r"\s+", "_", str(t).strip().lstrip("#")) for t in tags if str(t).strip())
    section = f"""

---

## {now.strftime('%H:%M')} - {title}

### النوع
{note_type}

### الحالة / الشعور
{mood or 'غير محدد'}

### السبب الأقرب
{cause or 'غير محدد'}

### النص الأصلي
{body or '—'}

### المطلوب من المذكرة
{action}

### روابط داخلية
{wikilinks or '—'}

### وسوم
{tag_line or '—'}
"""
    append(daily, section)

    for topic in topics:
        rel = TOPIC_MAP.get(topic)
        if rel:
            append(VAULT / rel, f"\n- {date} — [[{date}]]: {title}\n")

    supabase = supabase_upsert("notes", {
        "local_id": f"note:{date}:{now.strftime('%H%M%S%f')}",
        "title": title,
        "note_type": note_type,
        "mood": mood,
        "cause": cause,
        "body": body,
        "action": action,
        "topics": topics,
        "tags": tags,
        "obsidian_path": rel_for(daily),
        "date": date,
        "metadata": {"source": "local_pwa"},
    })
    return {"ok": True, "message": "تم حفظ المذكرة", "path": rel_for(daily), "absolute_path": str(daily), "supabase": supabase}


def save_link(data: dict) -> dict:
    ensure_structure()
    now = datetime.now()
    date = data.get("date") or now.strftime("%Y-%m-%d")
    raw_url_or_query = md_escape(data.get("url", ""))
    resolved = resolve_site_query(raw_url_or_query)
    url = normalize_url(resolved.get("url") or raw_url_or_query) if looks_like_url(resolved.get("url") or raw_url_or_query) else (resolved.get("url") or raw_url_or_query)
    kind = data.get("kind") or infer_link_kind(url)
    if kind in ("تلقائي", "Auto", ""):
        kind = infer_link_kind(url)
    title_source = data.get("title") or resolved.get("title") or title_from_url(url) or url or "رابط محفوظ"
    title = slugify_ar(title_source, "رابط محفوظ")
    reason = md_escape(data.get("reason", ""))
    status = md_escape(data.get("status", "جديد"))
    notes = md_escape(data.get("notes", ""))
    topics = data.get("topics") or []
    tags = data.get("tags") or []

    folder = VAULT / LINK_KIND_DIR.get(kind, LINK_KIND_DIR["آخر"])
    filename = f"{date} - {title}.md"
    path = folder / filename
    counter = 2
    while path.exists():
        path = folder / f"{date} - {title} ({counter}).md"
        counter += 1

    wikilinks = "\n".join(f"- [[{t}]]" for t in topics)
    tag_line = " ".join("#" + re.sub(r"\s+", "_", str(t).strip().lstrip("#")) for t in tags if str(t).strip())
    image = site_image_url(url)
    image_block = f"![صورة الموقع]({image})" if image else "—"
    content = f"""# {title}

## صورة الموقع
{image_block}

## الرابط
{url}

## الاسم أو الوصف الذي كتبته
{raw_url_or_query or '—'}

## النوع
{kind}

## تاريخ الحفظ
{date}

## سبب الحفظ
{reason or '—'}

## الحالة
{status}

## مرتبط بـ
{wikilinks or '—'}

## ملاحظاتي
{notes or '—'}

## وسوم
{tag_line or '—'}
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    append(VAULT / "07 - الروابط والمواقع" / "index.md", f"\n- {date} — [[{path.stem}]] — {url}\n")
    supabase = supabase_upsert("links", {
        "local_id": rel_for(path),
        "url": url,
        "title": title,
        "kind": kind,
        "reason": reason,
        "status": status,
        "notes": notes,
        "topics": topics,
        "tags": tags,
        "image_url": image or None,
        "obsidian_path": rel_for(path),
        "date": date,
        "metadata": {"source": "local_pwa", "raw_query": raw_url_or_query},
    })
    return {"ok": True, "message": "تم حفظ الرابط", "path": rel_for(path), "absolute_path": str(path), "supabase": supabase}



def write_if_missing(path: Path, content: str) -> bool:
    """Create a Markdown file only if it does not already exist."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return False
    path.write_text(content, encoding="utf-8")
    return True


def sync_links_from_supabase() -> int:
    rows = supabase_select("links", "select=*&order=created_at.desc&limit=500")
    if not rows.get("ok") or not isinstance(rows.get("data"), list):
        return 0
    count = 0
    ensure_structure()
    for r in rows["data"]:
        rel = r.get("obsidian_path") or r.get("local_id") or ""
        title = slugify_ar(r.get("title") or "رابط محفوظ", "رابط محفوظ")
        date = str(r.get("date") or datetime.now().strftime("%Y-%m-%d"))[:10]
        kind = r.get("kind") or "موقع"
        if not rel or rel.startswith("note:"):
            rel = str(Path(LINK_KIND_DIR.get(kind, LINK_KIND_DIR["آخر"])) / f"{date} - {title}.md")
        path = VAULT / rel
        tag_line = ' '.join('#' + re.sub(r"\s+", "_", str(t).strip().lstrip('#')) for t in (r.get('tags') or []) if str(t).strip()) or '—'
        topic_lines = chr(10).join('- [[' + str(t) + ']]' for t in (r.get('topics') or [])) or '—'
        image_block = ('![صورة الموقع](' + r.get('image_url') + ')') if r.get('image_url') else '—'
        content = f"""# {title}

<!-- supabase_id: {r.get('id','')} -->
<!-- local_id: {r.get('local_id','')} -->

## صورة الموقع
{image_block}

## الرابط
{r.get('url') or '—'}

## الاسم أو الوصف الذي كتبته
{(r.get('metadata') or {}).get('raw_query') or '—'}

## النوع
{kind}

## تاريخ الحفظ
{date}

## سبب الحفظ
{r.get('reason') or '—'}

## الحالة
{r.get('status') or '—'}

## مرتبط بـ
{topic_lines}

## ملاحظاتي
{r.get('notes') or '—'}

## وسوم
{tag_line}
"""
        if write_if_missing(path, content):
            append(VAULT / "07 - الروابط والمواقع" / "index.md", f"\n- {date} — [[{path.stem}]] — {r.get('url') or ''}\n")
            count += 1
    return count


def sync_places_from_supabase() -> int:
    rows = supabase_select("places", "select=*&order=created_at.desc&limit=500")
    if not rows.get("ok") or not isinstance(rows.get("data"), list):
        return 0
    count = 0
    ensure_structure()
    for r in rows["data"]:
        title = slugify_ar(r.get("title") or r.get("typed_name") or "مكان محفوظ", "مكان محفوظ")
        date = str(r.get("date") or datetime.now().strftime("%Y-%m-%d"))[:10]
        rel = r.get("obsidian_path") or r.get("local_id") or str(Path("08 - الأماكن والمواقع الجغرافية") / f"{date} - {title}.md")
        path = VAULT / rel
        lat, lon = r.get("lat"), r.get("lon")
        gmap = r.get("maps_url") or (maps_url(lat, lon) if lat and lon else "—")
        img_rel = r.get("photo_path") or ""
        content = f"""# {title}

<!-- supabase_id: {r.get('id','')} -->
<!-- local_id: {r.get('local_id','')} -->

## صورة المكان
{('![[%s]]' % img_rel) if img_rel else '—'}

## رابط الخريطة
{gmap}

## الإحداثيات
- Latitude: {lat or '—'}
- Longitude: {lon or '—'}

## العنوان التقريبي
{r.get('address') or '—'}

## الاسم الذي كتبته
{r.get('typed_name') or '—'}

## التصنيف
{r.get('category') or 'مكان'}

## تاريخ الحفظ
{date}

## الحالة
{r.get('status') or '—'}

## ملاحظاتي
{r.get('notes') or '—'}

## وسوم
#مكان #لوكيشن
"""
        if write_if_missing(path, content):
            append(VAULT / "08 - الأماكن والمواقع الجغرافية" / "index.md", f"\n- {date} — [[{path.stem}]] — {gmap}\n")
            count += 1
    return count


def sync_notes_from_supabase() -> int:
    rows = supabase_select("notes", "select=*&order=created_at.desc&limit=500")
    if not rows.get("ok") or not isinstance(rows.get("data"), list):
        return 0
    count = 0
    ensure_structure()
    for r in rows["data"]:
        local_id = r.get("local_id") or r.get("id") or ""
        if not local_id:
            continue
        date = str(r.get("date") or datetime.now().strftime("%Y-%m-%d"))[:10]
        daily = VAULT / "01 - اليوميات" / date[:4] / date[5:7] / f"{date}.md"
        daily.parent.mkdir(parents=True, exist_ok=True)
        if not daily.exists():
            daily.write_text(f"# يومية {date}\n\n", encoding="utf-8")
        existing = daily.read_text(encoding="utf-8", errors="ignore")
        marker = f"<!-- supabase_note: {local_id} -->"
        if marker in existing:
            continue
        title = slugify_ar(r.get("title") or "مذكرة", "مذكرة")
        tags = ' '.join('#'+re.sub(r'\s+', '_', str(t).strip().lstrip('#')) for t in (r.get('tags') or [])) or '—'
        topics = chr(10).join('- [['+str(t)+']]' for t in (r.get('topics') or [])) or '—'
        section = f"""

---
{marker}

## {datetime.now().strftime('%H:%M')} - {title}

### النوع
{r.get('note_type') or 'يومية'}

### الحالة / الشعور
{r.get('mood') or 'غير محدد'}

### السبب الأقرب
{r.get('cause') or 'غير محدد'}

### النص الأصلي
{r.get('body') or '—'}

### المطلوب من المذكرة
{r.get('action') or 'حفظ فقط'}

### روابط داخلية
{topics}

### وسوم
{tags}
"""
        append(daily, section)
        count += 1
    return count


def sync_trackers_from_supabase() -> int:
    rows = supabase_select("trackers", "select=*&order=created_at.desc&limit=500")
    if not rows.get("ok") or not isinstance(rows.get("data"), list):
        return 0
    store = load_trackers()
    changed = 0
    existing = {t.get("id"): t for t in store.get("trackers", [])}
    for r in rows["data"]:
        tid = r.get("local_id") or r.get("id")
        if not tid:
            continue
        if tid not in existing:
            t = {"id": tid, "name": r.get("name") or tid, "unit": r.get("unit") or "", "kind": r.get("kind") or "رقم", "entries": []}
            store.setdefault("trackers", []).append(t)
            existing[tid] = t
            md = trackers_dir() / f"{slugify_ar(t.get('name'), 'متتبع')}.md"
            if not md.exists():
                md.write_text(f"# {t.get('name')}\n\n## النوع\n{t.get('kind')}\n\n## الوحدة\n{t.get('unit') or '—'}\n\n## السجل\n\n", encoding="utf-8")
            changed += 1
    if changed:
        write_trackers(store)
    return changed


def sync_from_supabase() -> dict:
    if not supabase_configured():
        return {"ok": False, "error": "Supabase غير مضبوط"}
    result = {
        "links": sync_links_from_supabase(),
        "places": sync_places_from_supabase(),
        "notes": sync_notes_from_supabase(),
        "trackers": sync_trackers_from_supabase(),
    }
    return {"ok": True, "message": "تمت مزامنة قاعدة البيانات مع Obsidian", "synced": result}


def list_markdown_files() -> list[Path]:
    if not VAULT.exists():
        return []
    return [p for p in VAULT.rglob("*.md") if ".obsidian" not in p.parts]


def recent_items(limit: int = 12) -> list[dict]:
    items = []
    for p in list_markdown_files():
        st = p.stat()
        items.append({"path": rel_for(p), "title": p.stem, "mtime": st.st_mtime})
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items[:limit]


def status() -> dict:
    files = list_markdown_files()
    words = 0
    for p in files:
        try:
            words += len(p.read_text(encoding="utf-8", errors="ignore").split())
        except Exception:
            pass
    return {
        "ok": True,
        "vault": str(VAULT),
        "files": len(files),
        "words": words,
        "recent": recent_items(),
        "topics": list(TOPIC_MAP.keys()),
        "passcode_required": True,
        "supabase_configured": supabase_configured(),
        "supabase_url": SUPABASE_URL,
        "supabase_bucket": SUPABASE_BUCKET,
        "mobile_url": f"http://{local_ip()}:{PORT}",
        "local_url": f"http://127.0.0.1:{PORT}",
    }


def search(q: str) -> dict:
    q = (q or "").strip()
    results = []
    if not q:
        return {"ok": True, "results": recent_items(20)}
    needle = q.lower()
    for p in list_markdown_files():
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        low = txt.lower()
        idx = low.find(needle)
        if idx >= 0 or needle in p.stem.lower():
            start = max(0, idx - 120) if idx >= 0 else 0
            end = min(len(txt), idx + 220) if idx >= 0 else min(len(txt), 220)
            snippet = re.sub(r"\s+", " ", txt[start:end]).strip()
            results.append({"path": rel_for(p), "title": p.stem, "snippet": snippet})
    return {"ok": True, "results": results[:50]}


class Handler(BaseHTTPRequestHandler):
    server_version = "MudhakkiratiPWA/1.0"

    def _send(self, code=200, ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _json(self, obj, code=200):
        self._send(code)
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _html(self, text: str):
        self._send(200, "text/html; charset=utf-8")
        self.wfile.write(text.encode("utf-8"))

    def _auth(self) -> bool:
        if self.path.startswith("/api/auth") or self.path.startswith("/manifest") or self.path.startswith("/sw") or self.path.startswith("/icon"):
            return True
        token = self.headers.get("X-Passcode", "")
        return token == PASSCODE

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        return json.loads(raw or "{}")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/":
            self._html((STATIC / "index.html").read_text(encoding="utf-8"))
            return
        if path == "/manifest.webmanifest":
            self._send(200, "application/manifest+json; charset=utf-8")
            self.wfile.write((STATIC / "manifest.webmanifest").read_bytes())
            return
        if path == "/sw.js":
            self._send(200, "application/javascript; charset=utf-8")
            self.wfile.write((STATIC / "sw.js").read_bytes())
            return
        if path == "/icon.svg":
            self._send(200, "image/svg+xml; charset=utf-8")
            self.wfile.write((STATIC / "icon.svg").read_bytes())
            return
        if not self._auth():
            self._json({"ok": False, "error": "رمز الدخول غير صحيح"}, 401)
            return
        if path == "/api/status":
            self._json(status())
        elif path == "/api/search":
            qs = urllib.parse.parse_qs(parsed.query)
            self._json(search(qs.get("q", [""])[0]))
        elif path == "/api/resolve-link":
            qs = urllib.parse.parse_qs(parsed.query)
            q = qs.get("q", [""])[0]
            resolved = resolve_site_query(q)
            url = resolved.get("url") or q
            self._json({"ok": True, "url": url, "title": resolved.get("title") or title_from_url(url), "kind": infer_link_kind(url), "image": site_image_url(url)})
        elif path == "/api/trackers":
            self._json(list_trackers())
        elif path == "/api/sync-from-supabase":
            self._json(sync_from_supabase())
        elif path == "/api/open-url":
            qs = urllib.parse.parse_qs(parsed.query)
            rel = qs.get("path", [""])[0]
            target = VAULT / rel
            url = "obsidian://open?path=" + urllib.parse.quote(str(target))
            self._json({"ok": True, "url": url})
        else:
            self._json({"ok": False, "error": "Not found"}, 404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/api/auth":
            data = self._body()
            self._json({"ok": str(data.get("passcode", "")) == PASSCODE})
            return
        if not self._auth():
            self._json({"ok": False, "error": "رمز الدخول غير صحيح"}, 401)
            return
        try:
            data = self._body()
            if path == "/api/save-note":
                self._json(save_note(data))
            elif path == "/api/save-link":
                self._json(save_link(data))
            elif path == "/api/save-place":
                self._json(save_place(data))
            elif path == "/api/upsert-tracker":
                self._json(upsert_tracker(data))
            elif path == "/api/add-tracker-entry":
                self._json(add_tracker_entry(data))
            else:
                self._json({"ok": False, "error": "Not found"}, 404)
        except Exception as exc:
            self._json({"ok": False, "error": str(exc)}, 500)

    def log_message(self, fmt, *args):
        return


def local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main():
    ensure_structure()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("مذكرتي الذكية تعمل الآن")
    print(f"Local:   http://127.0.0.1:{PORT}")
    print(f"Mobile:  http://{local_ip()}:{PORT}")
    print(f"Vault:   {VAULT}")
    print(f"Passcode: {PASSCODE}")
    try:
        webbrowser.open(f"http://127.0.0.1:{PORT}")
    except Exception:
        pass
    server.serve_forever()


if __name__ == "__main__":
    main()
