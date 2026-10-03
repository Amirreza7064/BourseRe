# -*- coding: utf-8 -*-
"""ربات سرخطی بورس → بله | منابع: بورس‌پرس (اخبار) + TGJU (شاخص‌ها) | اجرا: GitHub Actions"""

import os, re, html, time
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

BALE_TOKEN   = os.environ["BALE_TOKEN"]
BALE_CHAT_ID = os.environ["BALE_CHAT_ID"]
API_URL = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}

def send(text):
    text = text[:4000]   # محدودیت طول پیام
    for _ in range(3):
        try:
            r = requests.post(API_URL, json={"chat_id": BALE_CHAT_ID, "text": text}, timeout=30)
            if r.status_code == 200:
                return True
            print("send:", r.status_code, r.text[:150])
        except requests.RequestException as e:
            print("send err:", str(e)[:100])
        time.sleep(3)
    return False

def clean(s):
    s = html.unescape(s or "")
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", s).strip()

def fmt(p):
    try:
        return f"{int(float(str(p).replace(',', ''))):,}"
    except Exception:
        return str(p)

# ─── ۱) تیترها از بورس‌پرس ───
def fetch_news(limit=14):
    for url in ("https://boursepress.ir/rss", "https://boursepress.ir/feed",
                "https://boursepress.ir/rss.xml", "https://boursepress.ir/feed/"):
        try:
            r = requests.get(url, headers=UA, timeout=20)
            print("RSS", url, r.status_code, len(r.content))
            if r.status_code != 200 or len(r.content) < 200:
                continue
            items = re.findall(r"<item>(.*?)</item>", r.text, re.S) or \
                    re.findall(r"<entry>(.*?)</entry>", r.text, re.S)
            titles = []
            for it in items:
                m = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
                t = clean(m.group(1)) if m else ""
                if len(t) >= 18:
                    titles.append(t)
            if titles:
                print(f"اخبار از RSS ({len(titles)})")
                return titles[:limit]
        except Exception as e:
            print("rss err:", str(e)[:90])
    # فالبک: تیترهای صفحهٔ اصلی
    try:
        r = requests.get("https://boursepress.ir/", headers=UA, timeout=20)
        seen, out = set(), []
        for l in map(clean, re.findall(r">([^<>]{25,140})</a>", r.text)):
            if len(l) >= 25 and re.search(r"[\u0600-\u06FF]", l) and l not in seen:
                seen.add(l); out.append(l)
        print(f"اخبار از HTML ({len(out)})")
        return out[:limit]
    except Exception as e:
        print("html err:", str(e)[:90])
    return []

# ─── ۲) شاخص‌ها و ارز/طلا از TGJU ───
def fetch_market():
    cur = {}
    try:
        r = requests.get("https://call.tgju.org/ajax.json", headers=UA, timeout=20)
        cur = r.json().get("current", {})
    except Exception as e:
        print("tgju err:", str(e)[:100])

    idx = []
    for k, v in cur.items():
        if k.startswith("indices") or "index" in k.lower():
            name = "شاخص کل" if "32097828338996571" in k else k
            idx.append((name, v.get("p"), v.get("dp")))
    if not idx:   # فالبک: صفحهٔ بورس TGJU
        try:
            r = requests.get("https://www.tgju.org/bourse", headers=UA, timeout=20)
            m = re.search(r"شاخص کل.{0,400}?([\d,]{7,})", r.text, re.S)
            if m: idx.append(("شاخص کل", m.group(1), None))
        except Exception:
            pass
    macro = [(n, cur.get(k, {}).get("p"), cur.get(k, {}).get("dp"))
             for k, n in (("price_dollar_rl", "دلار"), ("sekee", "سکه امامی"), ("gerami18", "طلای ۱۸"))]
    return idx, macro

def build():
    now = datetime.now(ZoneInfo("Asia/Tehran"))
    lines = [f"🌅 سرخطی بورس — {now.strftime('%Y-%m-%d %H:%M')}", ""]
    idx, macro = fetch_market()
    rows = [r for r in (idx + macro) if r[1]]
    if rows:
        lines.append("📊 بازار:")
        for name, p, dp in rows:
            d = f"  ({dp}%)" if dp not in (None, "", "0", "0.0") else ""
            lines.append(f"• {name}: {fmt(p)}{d}")
        lines.append("")
    news = fetch_news()
    if news:
        lines.append("📰 تیترهای بورس‌پرس:")
        for i, t in enumerate(news, 1):
            lines.append(f"{i}. {t}")
    if len(lines) <= 2:
        lines.append("هیچ منبعی پاسخ نداد؛ در اجرای بعدی خودکار دوباره تلاش می‌شود.")
    lines += ["", "ℹ️ صرفاً خبر و داده است؛ توصیه خرید/فروش نیست."]
    return "\n".join(lines)

if __name__ == "__main__":
    print(send(build()) and "✅ ارسال شد" or "❌ ارسال ناموفق")
