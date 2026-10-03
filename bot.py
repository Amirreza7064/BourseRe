# -*- coding: utf-8 -*-
"""فایل: bot.py — غربالگری بورس + سرخطی | اجرا: GitHub Actions → daily-scan"""

import os, re, html, time
import requests
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

BALE_TOKEN   = os.environ["BALE_TOKEN"]
BALE_CHAT_ID = os.environ["BALE_CHAT_ID"]
API_URL = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}

SOURCE = "filterBourseUniversity"   # منبع داده (فقط داخل کد، در پیام نمی‌آید)
TOP_N         = 25                  # چند نماد برتر ارسال شود
SEND_HEADLINE = True                # پیام سرخطی هم بیاید؟ False = فقط غربالگری

def send(text):
    text = text[:4000]
    for _ in range(3):
        try:
            r = requests.post(API_URL, json={"chat_id": BALE_CHAT_ID, "text": text}, timeout=30)
            if r.status_code == 200: return True
            print("send:", r.status_code, r.text[:120])
        except requests.RequestException as e:
            print("send err:", str(e)[:90])
        time.sleep(3)
    return False

def clean(s):
    s = html.unescape(s or "")
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"[ \t]+", " ", s).strip()

def fmt(p):
    try: return f"{int(float(str(p).replace(',', ''))):,}"
    except Exception: return str(p)

# ───────── سرخطی (بازار + اخبار) ─────────
def fetch_news(limit=12):
    try:
        r = requests.get("https://boursepress.ir/", headers=UA, timeout=20)
        seen, out = set(), []
        for l in map(clean, re.findall(r">([^<>]{25,140})</a>", r.text)):
            if len(l) >= 25 and re.search(r"[\u0600-\u06FF]", l) and l not in seen:
                seen.add(l); out.append(l)
        return out[:limit]
    except Exception:
        return []

def fetch_market():
    cur = {}
    try: cur = requests.get("https://call.tgju.org/ajax.json", headers=UA, timeout=20).json().get("current", {})
    except Exception: pass
    macro = [(n, cur.get(k, {}).get("p"), cur.get(k, {}).get("dp"))
             for k, n in (("price_dollar_rl","دلار"),("sekee","سکه امامی"),("gerami18","طلای ۱۸"))]
    idx = []
    try:
        r = requests.get("https://www.tgju.org/bourse", headers=UA, timeout=20)
        for name in ("شاخص کل", "شاخص هم‌وزن"):
            m = re.search(name + r".{0,400}?([\d,]{7,})", r.text, re.S)
            if m: idx.append((name, m.group(1), None))
    except Exception: pass
    return idx + macro

def build_headline():
    now = datetime.now(ZoneInfo("Asia/Tehran"))
    L = [f"🌅 سرخطی بورس — {now.strftime('%Y-%m-%d %H:%M')}", "", "📊 بازار:"]
    rows = [r for r in fetch_market() if r[1]]
    if rows:
        for name, p, dp in rows:
            d = f"  ({dp}%)" if dp not in (None, "", "0", "0.0") else ""
            L.append(f"• {name}: {fmt(p)}{d}")
    news = fetch_news()
    if news:
        L += ["", "📰 تیترها:"]
        L += [f"{i}. {t}" for i, t in enumerate(news, 1)]
    return "\n".join(L)

# ───────── غربالگری روزانه ─────────
STOP = set("""بورس فرابورس شاخص بازار نماد سهام سهم خرید فروش سود زیان ورود خروج پول هوشمند
سیگنال تحلیل تکنیکال بنیادی گزارش امروز فردا هفته ماه قیمت هدف حد ضرر سبد پیشنهاد توصیه
سرمایه معاملات حقوقی حقیقی نقدینگی تقاضا عرضه صف دلار سکه طلا اونس تتر ریال تورم
فیلتر کانال عضویت لینک ادامه توضیحات آموزش دانلود مهم فوری دانشگاه دیده بان جدول ستون
کد نویسی فرمول دستور تعریف متغیر مقدار شرط خروجی رفقا دوستان سلام صبح عصر شب""".split())

SEED = ["فولاد","فملی","شستا","شپنا","وبملت","خساپا","ذوب","کگل","فولام","بفغل","غپینو",
        "شپدروا","فجر","کچاد","کگهر","پارسان","حپترو","تپمو","وهور","شبندر","غشهد","فنورد"]

# پست‌های تبلیغاتی/غیرمرتبط با این کلمات کنار گذاشته می‌شوند
AD_WORDS = ["صرافی","کریپتو","بایننس","تتر","usdt","ترید","کارمزد","تبلیغ","اینستا",
            "واتساپ","واتس","لایسنس","ساپورت","پشتیبانی خرید"]

EXPLICIT = re.compile(
    r'«([\u0600-\u06FF][\u0600-\u06FF\d]{2,14})»'          # «نماد»
    r'|#([\u0600-\u06FF][\u0600-\u06FF\d]{2,14})'          # #نماد
    r'|(?:نماد|سهم)\s*[:：]?\s*([\u0600-\u06FF][\u0600-\u06FF\d]{2,14})'  # نماد: X
    r'|\(([\u0600-\u06FF][\u0600-\u06FF\d]{2,14})\)'       # (نماد)
)
LETTER = re.compile(r'[\u0620-\u064A\u066E-\u06D5]')

def valid(sym):
    if not (3 <= len(sym) <= 15): return False
    if sym in STOP or not LETTER.search(sym): return False
    return not re.fullmatch(r"[\d.,%\-–\s\u06F0-\u06F9]+", sym)

def parse_page(page):
    out, marks = [], list(re.finditer(r'data-post="[^"/]+/(\d+)"', page))
    for i, m in enumerate(marks):
        blk = page[m.start(): marks[i+1].start() if i+1 < len(marks) else len(page)]
        tm  = re.search(r'<time[^>]*datetime="([^"]+)"', blk)
        tx  = re.search(r'tgme_widget_message_text[^>]*>(.*?)</div>', blk, re.S)
        if tx:
            out.append({"id": int(m.group(1)),
                        "dt": tm.group(1) if tm else None,
                        "raw": tx.group(1)})
    return out

def fetch_posts(max_pages=3):
    seen, allp, before = set(), [], None
    for _ in range(max_pages):
        url = f"https://t.me/s/{SOURCE}" + (f"?before={before}" if before else "")
        try:
            r = requests.get(url, headers=UA, timeout=25)
        except Exception:
            break
        if r.status_code != 200: break
        page = parse_page(r.text)
        if not page: break
        new = [p for p in page if p["id"] not in seen]
        seen.update(p["id"] for p in new)
        allp += new
        mn = min(p["id"] for p in page)
        if before is not None and mn >= before: break
        before = mn
        time.sleep(1)
    return allp

def post_date(iso):
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("Asia/Tehran")).date()
    except Exception:
        return None

def collect():
    """خروجی: (لیست رتبه‌بندی‌شده، تاریخ داده) — فقط پست‌های همان یک روز"""
    posts = fetch_posts()
    if not posts:
        return None, None
    for p in posts:
        p["date"] = post_date(p["dt"])
    today = datetime.now(ZoneInfo("Asia/Tehran")).date()
    dated = [p for p in posts if p["date"]]
    target = today if any(p["date"] == today for p in dated) else max(p["date"] for p in dated)
    day_posts = [p for p in dated if p["date"] == target]

    score, refs, seen_txt = {}, {}, set()
    for p in day_posts:
        t = clean(p["raw"])
        if len(t) < 10 or t[:80] in seen_txt: continue
        seen_txt.add(t[:80])
        low = t.lower()
        if any(a in low or a in t for a in AD_WORDS): continue
        syms = set()
        for g in EXPLICIT.findall(t):
            s = next((x for x in g if x), None)
            if s:
                s = s.strip(" :：،,.؛()«»-–")
                if valid(s): syms.add(s)
        for s in SEED:
            if s in t and s not in syms:
                syms.add(s)
        if not syms: continue
        for s in syms:
            score[s]  = score.get(s, 0) + 2
            refs[s]   = refs.get(s, 0) + 1
    ranked = sorted(score.items(), key=lambda kv: (-kv[1], -refs[kv[0]]))[:TOP_N]
    return ranked, target

def build_screen(ranked, d):
    if ranked is None:
        return "⛔ دریافت اطلاعات امروز ناموفق بود؛ در اجرای بعدی خودکار تلاش می‌شود."
    if not ranked:
        return f"📋 امروز ({d.isoformat()}) پست فیلتری با نماد مشخص ثبت نشده است."
    L = [f"🎯 غربالگری بورس — نمادهای منتخب", f"📅 {d.isoformat()}", ""]
    L += [f"{i}. {s}  ×{c}" for i, (s, c) in enumerate(ranked, 1)]
    L += ["", "🤖 خروجی خودکار است؛ توصیه خرید/فروش نیست."]
    return "\n".join(L)

if __name__ == "__main__":
    if SEND_HEADLINE:
        send(build_headline())
    ranked, d = collect()
    send(build_screen(ranked, d))
    print("✅ پایان")
