"""
Bimbel Matematika Viral Monitor — WEB/BLOG ONLY
Monitors news articles + blog posts about math tutoring in Indonesia via Google News RSS.
Sends daily alert to Telegram at 08:00 WIB.

NOTE: Web/blog platforms do not expose public view counts, so the "viral >100 views"
threshold cannot be applied here. This monitor surfaces ALL new coverage matching
your keywords in the last 24 hours. Adjust KEYWORDS to control volume.
"""

import os
import json
import html
import time
import hashlib
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import feedparser
import requests
from dateutil import parser as date_parser

# =========================
# CONFIGURATION
# =========================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

# Keywords to monitor. Edit list ini kalau mau tambah/kurangi topik.
# Kalau alert kebanyakan → perketat (contoh: hapus keyword yang terlalu umum).
# Kalau alert 0 mulu → loosen (tambah keyword variasi).
KEYWORDS = [
    "bimbel matematika SMA",
    "bimbel UTBK matematika",
    "bimbel SIMAK UI",
    "bimbel SIMAK KKI UI",
    "bimbel IUP UGM",
    "bimbel ujian mandiri matematika",
    "Keza Privat",
    "Mantappu Academy",
    "les matematika viral",
    "bimbel matematika viral",
]

# Maximum artikel per keyword (biar Telegram gak overflow)
MAX_PER_KEYWORD = 10

# File untuk track item yang udah pernah dikirim (biar gak duplicate)
SEEN_FILE = "seen.json"


# =========================
# HELPERS
# =========================
def load_seen():
    try:
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_seen(seen_set):
    seen_list = list(seen_set)[-3000:]
    with open(SEEN_FILE, "w") as f:
        json.dump(seen_list, f)


def make_id(url):
    return hashlib.md5(url.encode()).hexdigest()


def hours_since(dt):
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).total_seconds() / 3600


# =========================
# GOOGLE NEWS RSS
# Sumber: mengindex ribuan situs berita + blog Indonesia
# =========================
def search_google_news(keyword):
    results = []
    try:
        url = (
            "https://news.google.com/rss/search"
            f"?q={quote_plus(keyword)}+when:1d"
            "&hl=id&gl=ID&ceid=ID:id"
        )
        feed = feedparser.parse(url)

        for entry in feed.entries[:MAX_PER_KEYWORD]:
            try:
                pub_dt = date_parser.parse(entry.published)
                if hours_since(pub_dt) > 24:
                    continue

                publisher = ""
                if hasattr(entry, "source") and hasattr(entry.source, "title"):
                    publisher = entry.source.title

                results.append({
                    "title": entry.title,
                    "url": entry.link,
                    "publisher": publisher,
                    "published": entry.published,
                    "keyword": keyword,
                })
            except Exception:
                continue
    except Exception as e:
        print(f"[Google News] Error for '{keyword}': {e}")

    return results


# =========================
# TELEGRAM
# =========================
def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram] Missing credentials, cannot send")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    # Telegram max message = 4096 chars
    if len(message) > 4000:
        message = message[:3990] + "\n\n... (truncated)"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"[Telegram] Send failed: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"[Telegram] Response: {e.response.text}")
        return False


def format_message(items):
    now_wib = datetime.now(timezone.utc) + timedelta(hours=7)
    header = (
        "📰 <b>Laporan Bimbel Matematika — Web/Blog</b>\n"
        f"🕗 {now_wib.strftime('%d %b %Y, %H:%M')} WIB\n"
        f"📊 Total artikel baru: {len(items)}\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
    )

    if not items:
        return header + (
            "Tidak ada artikel baru terdeteksi dalam 24 jam terakhir.\n\n"
            "<i>Kalau ini terjadi berhari-hari, coba loosen keywords di main.py.</i>"
        )

    # Group by keyword biar lebih rapi bacanya
    by_keyword = {}
    for item in items:
        by_keyword.setdefault(item["keyword"], []).append(item)

    body = ""
    for keyword, kw_items in by_keyword.items():
        body += f"🔍 <b>{html.escape(keyword)}</b> ({len(kw_items)})\n"
        for i, item in enumerate(kw_items, 1):
            title = html.escape(item["title"])
            publisher = html.escape(item.get("publisher", ""))
            body += f"  {i}. <a href=\"{item['url']}\">{title}</a>\n"
            if publisher:
                body += f"     📄 {publisher}\n"
        body += "\n"

    footer = (
        "━━━━━━━━━━━━━━━━━━\n"
        "<i>Note: web/blog tidak expose view count publik. "
        "Semua artikel baru dalam 24 jam ditampilkan tanpa filter viral. "
        "Assess relevansi manual.</i>"
    )

    return header + body + footer


# =========================
# MAIN
# =========================
def main():
    print(f"[{datetime.now(timezone.utc).isoformat()}] Starting web/blog monitor")
    print(f"Keywords: {len(KEYWORDS)}")

    seen = load_seen()
    print(f"Previously seen items: {len(seen)}")

    all_new = []

    for keyword in KEYWORDS:
        print(f"\n[Search] {keyword}")
        articles = search_google_news(keyword)

        new_count = 0
        for item in articles:
            item_id = make_id(item["url"])
            if item_id not in seen:
                seen.add(item_id)
                all_new.append(item)
                new_count += 1

        print(f"  Found: {len(articles)}, New: {new_count}")
        time.sleep(1)  # Politeness delay

    print(f"\nTotal new items: {len(all_new)}")

    message = format_message(all_new)
    print("\n--- Message preview ---")
    print(message[:800])
    print("--- End preview ---\n")

    if send_telegram(message):
        print("✓ Telegram alert sent")
        save_seen(seen)
        return 0
    else:
        print("✗ Telegram alert failed")
        return 1


if __name__ == "__main__":
    exit(main())
