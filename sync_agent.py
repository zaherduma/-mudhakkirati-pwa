#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
مزامن Obsidian التلقائي — مذكرتي الذكية
=========================================
يسحب العناصر الجديدة من Supabase ويكتبها داخل خزنة Obsidian المحلية.

يعمل تلقائياً كل 60 ثانية عندما يكون Mac متصلاً بالإنترنت.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

# ── المسارات ──────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
VAULT = (ROOT / ".." / ".." / "Documents" / "الأرشيف الشخصي").resolve()
ENV_PATH = ROOT / ".env"
CONFIG_PATH = ROOT / "config.json"
STATE_PATH = ROOT / "sync_state.json"

# ── الإعدادات ─────────────────────────────────────────────
SYNC_INTERVAL = 60  # ثانية بين كل دورة
SYNC_TABLES = ["places", "notes", "links", "tracker_entries"]


def load_env() -> dict:
    values = {}
    if not ENV_PATH.exists():
        print("⚠️  ملف .env غير موجود في:", ENV_PATH)
        return values
    for line in ENV_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


ENV = load_env()
SUPABASE_URL = (ENV.get("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = ENV.get("SUPABASE_SERVICE_ROLE_KEY") or ENV.get("SUPABASE_ANON_KEY") or ""


# ── حالة المزامنة ─────────────────────────────────────────
def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"last_sync_time": None, "synced_ids": []}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ── الاتصال بـ Supabase ───────────────────────────────────
def supabase_get(table: str, since_time: str | None = None) -> list[dict]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    params = ["select=*", "order=created_at.asc"]
    if since_time:
        params.append(f"created_at=gt.{urllib.parse.quote(since_time)}")
    url = f"{SUPABASE_URL}/rest/v1/{table}?{'&'.join(params)}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except Exception as exc:
        print(f"  ⚠️  فشل جلب {table}: {exc}")
        return []


# ── الكتابة في خزنة Obsidian ──────────────────────────────
def slugify(text: str, fallback: str = "عنوان") -> str:
    text = (text or fallback).strip()
    text = re.sub(r'[\\/:*?"<>|#%{}$!`&@=+]', " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:80] or fallback


def append(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(text)


def sync_place(row: dict) -> bool:
    try:
        date = (row.get("created_at") or datetime.now().isoformat())[:10]
        title = slugify(row.get("title") or f"مكان {date}")
        lat = row.get("lat") or 0
        lon = row.get("lon") or 0
        gmap = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
        address = row.get("address") or ""
        notes = row.get("notes") or ""
        category = row.get("category") or "مكان"
        status = row.get("status") or "للزيارة لاحقًا"
        cat_tag = re.sub(r'\s+', '_', category)
        folder = VAULT / "08 - الأماكن والمواقع الجغرافية"
        path = folder / f"{date} - {title}.md"
        if path.exists():
            print(f"  ⏭️  {path.name} موجود مسبقاً")
            return True
        content = f"""# {title}

## صورة المكان
—

## رابط الخريطة
{gmap}

## الإحداثيات
- Latitude: {lat}
- Longitude: {lon}

## العنوان التقريبي
{address or '—'}

## التصنيف
{category}

## تاريخ الحفظ
{date}

## الحالة
{status}

## ملاحظاتي
{notes or '—'}

## وسوم
#مكان #لوكيشن #{cat_tag}
"""
        path.write_text(content, encoding="utf-8")
        index = folder / "index.md"
        if not index.exists():
            index.write_text("# الأماكن والمواقع الجغرافية\n\n", encoding="utf-8")
        append(index, f"\n- {date} — [[{path.stem}]] — {gmap}\n")
        print(f"  ✓ {path.name}")
        return True
    except Exception as exc:
        print(f"  ✗ خطأ في المكان: {exc}")
        return False


def sync_note(row: dict) -> bool:
    try:
        date = (row.get("created_at") or datetime.now().isoformat())[:10]
        year, month = date[:4], date[5:7]
        title = slugify(row.get("title") or f"مذكرة {date}")
        note_type = row.get("note_type") or "يومية"
        mood = row.get("mood") or ""
        body = row.get("body") or ""
        topics = row.get("topics") or []
        tags = row.get("tags") or []
        daily = VAULT / "01 - اليوميات" / year / month / f"{date}.md"
        if not daily.exists():
            daily.parent.mkdir(parents=True, exist_ok=True)
            daily.write_text(f"# يومية {date}\n\n", encoding="utf-8")
        wikilinks = "\n".join(f"- [[{t}]]" for t in topics)
        tag_line = " ".join(f"#{re.sub(r'\s+', '_', str(t).strip().lstrip('#'))}" for t in tags if str(t).strip())
        section = f"""

---

## {datetime.now().strftime('%H:%M')} - {title}

### النوع
{note_type}

### الحالة / الشعور
{mood or 'غير محدد'}

### النص الأصلي
{body or '—'}

### روابط داخلية
{wikilinks or '—'}

### وسوم
{tag_line or '—'}
"""
        append(daily, section)
        print(f"  ✓ {title} → {daily.name}")
        return True
    except Exception as exc:
        print(f"  ✗ خطأ في المذكرة: {exc}")
        return False


def sync_link(row: dict) -> bool:
    try:
        date = (row.get("created_at") or datetime.now().isoformat())[:10]
        url = row.get("url") or ""
        title = slugify(row.get("title") or url or "رابط")
        kind = row.get("kind") or "موقع"
        notes = row.get("notes") or ""
        kind_dir = {
            "YouTube": "يوتيوب",
            "مقالة": "مقالات",
            "مقالات": "مقالات",
            "موقع": "مواقع",
            "PDF": "PDF وكتب",
            "أداة": "أدوات",
            "آخر": "مواقع",
        }
        sub = kind_dir.get(kind, "مواقع")
        folder = VAULT / "07 - الروابط والمواقع" / sub
        path = folder / f"{date} - {title}.md"
        if path.exists():
            return True
        content = f"""# {title}

## الرابط
{url}

## النوع
{kind}

## تاريخ الحفظ
{date}

## ملاحظاتي
{notes or '—'}
"""
        path.write_text(content, encoding="utf-8")
        append(VAULT / "07 - الروابط والمواقع" / "index.md", f"\n- {date} — [[{path.stem}]] — {url}\n")
        print(f"  ✓ {title}")
        return True
    except Exception as exc:
        print(f"  ✗ خطأ في الرابط: {exc}")
        return False


def sync_tracker_entry(row: dict) -> bool:
    try:
        date = row.get("date") or (row.get("created_at") or "")[:10]
        value = row.get("value") or ""
        notes = row.get("notes") or ""
        tracker_local_id = row.get("tracker_local_id") or "متتبع"
        tracker_file = VAULT / "09 - المتتبعات" / f"{slugify(tracker_local_id)}.md"
        if not tracker_file.exists():
            tracker_file.parent.mkdir(parents=True, exist_ok=True)
            tracker_file.write_text(f"# {tracker_local_id}\n\n## السجل\n\n", encoding="utf-8")
        append(tracker_file, f"- {date}: {value}" + (f" — {notes}" if notes else "") + "\n")
        print(f"  ✓ {tracker_local_id}: {value}")
        return True
    except Exception as exc:
        print(f"  ✗ خطأ في مدخلة المتتبع: {exc}")
        return False


SYNC_FUNCS = {
    "places": sync_place,
    "notes": sync_note,
    "links": sync_link,
    "tracker_entries": sync_tracker_entry,
}


# ── تحديث حالة المزامنة في Supabase ───────────────────────
def mark_synced(table: str, row_id: str) -> None:
    if not SUPABASE_KEY:
        return
    try:
        data = json.dumps({"synced_to_obsidian": True}).encode()
        url = f"{SUPABASE_URL}/rest/v1/{table}?id=eq.{urllib.parse.quote(row_id)}"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
        }
        req = urllib.request.Request(url, data=data, headers=headers, method="PATCH")
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception:
        pass


# ── دورة المزامنة الرئيسية ────────────────────────────────
def sync_cycle() -> int:
    state = load_state()
    last_time = state.get("last_sync_time")
    synced_ids = set(state.get("synced_ids", []))
    total = 0

    print(f"\n{'='*50}")
    print(f"دورة مزامنة — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"آخر مزامنة: {last_time or 'أول مرة'}")
    print(f"العناصر المزامنة سابقاً: {len(synced_ids)}")
    print(f"{'='*50}")

    for table in SYNC_TABLES:
        rows = supabase_get(table, last_time)
        if not rows:
            continue
        new_rows = [r for r in rows if r.get("id") not in synced_ids and not r.get("synced_to_obsidian")]
        if not new_rows:
            continue
        print(f"\n  {table}: {len(new_rows)} جديد")
        func = SYNC_FUNCS.get(table)
        for row in new_rows:
            if func and func(row):
                synced_ids.add(row.get("id", ""))
                mark_synced(table, row.get("id", ""))
                total += 1

    # حفظ الحالة
    state["last_sync_time"] = datetime.now().isoformat()
    state["synced_ids"] = list(synced_ids)[-5000:]  # ابق آخر 5000 id
    save_state(state)

    if total:
        print(f"\n✅ تمت مزامنة {total} عناصر جديدة مع Obsidian")
    else:
        print("\n✓ لا توجد عناصر جديدة")
    return total


# ── التشغيل ───────────────────────────────────────────────
def main():
    print("🔄 مزامن Obsidian التلقائي — مذكرتي الذكية")
    print(f"    الخزنة: {VAULT}")
    print(f"    الدورة كل {SYNC_INTERVAL} ثانية")
    if not SUPABASE_URL:
        print("    ⚠️  Supabase غير مضبوط — يرجى إضافة SUPABASE_URL و SUPABASE_SERVICE_ROLE_KEY في .env")
        sys.exit(1)
    print()

    # دورة أولى فورية
    sync_cycle()

    # حلقات كل 60 ثانية
    while True:
        time.sleep(SYNC_INTERVAL)
        try:
            sync_cycle()
        except KeyboardInterrupt:
            print("\n⏹️  تم إيقاف المزامن")
            break
        except Exception as exc:
            print(f"\n⚠️ خطأ في الدورة: {exc}")


if __name__ == "__main__":
    main()
