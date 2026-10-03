# -*- coding: utf-8 -*-
"""فایل: bot.py — سرخطی بورس (صبح) + غربالگری روزانه (بعد بازار)
اجرا: GitHub Actions → daily-scan | حالت اجرا با متغیر RUN_MODE کنترل می‌شود"""

import os, re, html, time
import requests
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

BALE_TOKEN   = os.environ["BALE_TOKEN"]
BALE_CHAT_ID = os.environ["BALE_CHAT_ID"]
API_URL = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}

SOURCE = "filterBourseUniversity"   # منبع پست‌های فیلتری
TOP_N      = 25                     # چند نماد برتر در پیام غربالگری
NEWS_LIMIT = 10                     # چند تیتر در پیام صبح

RUN_MODE = os.environ.get("RUN_MODE", "both").strip().lower()   # morning | afternoon | both

# ── وایت‌لیست نمادهای واقعی — اگر نماد معتبری جا افتاد فقط همین‌جا اضافه‌اش کنید ──
KNOWN = set("""فولاد فملی فولام بفغل کگل ذوب فماک فنورد فپلا فسپا فنما فخوز فباهنر فبستم
فجام چدن کچاد کگهر کروی نوری کتو شپنا شبریز پارسان شپدیس شبندر شپلی فجر فاذر فکمند
غاذر دفارا دتمد کمند وبملت وبصادر وتجارت وپاسار وبساخت وبشهر وبکویر وامید وتوس
خبازر خبهمن خساپا خگستر خساز خودرو خکرمان غشهد غگل غپینو غنیش سفار سغرب سکرمان
دورو حپترو وهور شستا شگستر کاریزما طلا عیار کارد برکت""".split())

# این‌ها کلمهٔ عادی هم هستند؛ فقط داخل «» یا #هشتگ یا (پرانتز) پذیرفته می‌شوند
AMBIG = {"طلا", "عیار", "کارد", "برکت", "کاریزما", "فجر"}
KNOWN_BARE = KNOWN - AMBIG

def send(text):
    payload = {"chat_id": BALE_CHAT_ID, "text": text[:4000]}   # متن ساده
    for _ in range(4):
        try:
            r = requests.post(API_URL, json=payload, timeout=30)
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

def normalize(s):
    return (s or "").replace("ي", "ی").replace("ك", "ک").replace("أ", "ا") \
                    .replace("إ", "ا").replace("ة", "ه").replace("ؤ", "و")

def fmt(p):
    try: return f"{int(float(str(p).replace(',', ''))):,}"
    except Exception: return str(p)

# ───────── سرخطی (صبح) ─────────
def fetch_market():
    cur = {}
    try: cur = requests.get("https://call.tgju.org/ajax.json", headers=UA, timeout=20).json().get("current", {})
    except Exception: pass
    def px(*keys):
        for k in keys:
            v = cur.get(k)
            if v: return v.get("p"), v.get("dp")
        return None, None
    p, d = px("price_dollar_rl", "dollar_rl"); macro = [("دلار", p, d)]
    p, d = px("sekee");                        macro.append(("سکه امامی", p, d))
    p, d = px("gerami18", "geram18", "geram_18"); macro.append(("طلای ۱۸", p, d))
    idx = []
    for page_url in ("https://www.tgju.org/bourse", "https://www.tgju.org/"):
        try:
            r = requests.get(page_url, headers=UA, timeout=20)
            for name in ("شاخص کل", "شاخص هم‌وزن"):
                if not any(n == name for n, _, _ in idx):
                    m = re.search(name + r".{0,500}?([\d,]{7,})", r.text, re.S)
                    if m: idx.append((name, m.group(1), None))
            if idx: break
        except Exception: pass
    return idx + macro

def fetch_news(limit=NEWS_LIMIT):
    """خروجی: لیست (عنوان، لینک) از بورس‌پرس — لینک زیر هر تیتر قرار می‌گیرد"""
    try:
        r = requests.get("https://boursepress.ir/", headers=UA, timeout=20)
        out, seen = [], set()
        for href, raw in re.findall(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r.text, re.S):
            t = clean(raw)
            if len(t) < 25 or not re.search(r"[\u0600-\u06FF]", t): continue
            if href.startswith("/"): href = "https://boursepress.ir" + href
            if not href.startswith("http") or href in seen or t in seen: continue
            seen.add(href); seen.add(t)
            out.append((t, href))
            if len(out) >= limit: break
        print("اخبار:", len(out))
        return out
    except Exception as e:
        print("news err:", str(e)[:90]); return []

def build_headline():
    now = datetime.now(ZoneInfo("Asia/Tehran"))
    L = [f"🌅 سرخطی بورس — {now.strftime('%Y-%m-%d %H:%M')}", "", "📊 بازار:"]
    rows = [r for r in fetch_market() if r[1]]
    if rows:
        for name, p, dp in rows:
            d = f"  (+{dp}%)" if dp not in (None, "", "0", "0.0") else ""
            L.append(f"• {name}: {fmt(p)}{d}")
    else:
        L.append("• (نرخ‌ها در این اجرا خوانده نشد)")
    news = fetch_news()
    if news:
        L += ["", "📰 تیترها (لینک زیر هر تیتر):", ""]
        for i, (t, u) in enumerate(news, 1):
            L.append(f"{i}. {t}")
            L.append(f"   {u}")
    return "\n".join(L)

# ───────── غربالگری (بعد بازار) ─────────
AD_WORDS = ["صرافی","کریپتو","بایننس","تتر","usdt","ترید","کارمزد","تبلیغ","اینستا",
            "واتساپ","واتس","لایسنس","ساپورت","پشتیبانی خرید"]

PATTERNS = [
    r'«([^«»\n]{2,15})»',
    r'#([\w\u0600-\u06FF]{2,15})',
    r'(?:نماد|سهم|سهام)\s*[:：]?\s*([\u0600-\u06FF][\u0600-\u06FF\d]{1,14})',
    r'\(([\u0600-\u06FF][\u0600-\u06FF\d]{1,14})\)',
]
BOUND = r'(?<![\u0600-\u06FF\d]){}(?![\u0600-\u06FF\d])'
KNOWN_ALL     = {normalize(s) for s in KNOWN}
KNOWN_BARE_N  = {normalize(s) for s in KNOWN_BARE}

def extract_symbols(t):
    t = normalize(t)
    out = set()
    for pat in PATTERNS:
        for c in re.findall(pat, t):
            c = c.strip(" :：،,.؛()«»!؟?\"'-–")
            if c in KNOWN_ALL: out.add(c)          # فقط نماد واقعی (وایت‌لیست)
    for s in KNOWN_BARE_N:                          # نماد شناخته‌شده به‌تنهایی با مرز کلمه
        if re.search(BOUND.format(re.escape(s)), t): out.add(s)
    return out

def parse_page(page):
    out, marks = [], list(re.finditer(r'data-post="[^"/]+/(\d+)"', page))
    for i, m in enumerate(marks):
        blk = page[m.start(): marks[i+1].start() if i+1 < len(marks) else len(page)]
        tm = re.search(r'<time[^>]*datetime="([^"]+)"', blk)
        tx = re.search(r'tgme_widget_message_text[^>]*>(.*?)</div>', blk, re.S)
        if tx:
            out.append({"id": int(m.group(1)), "dt": tm.group(1) if tm else None, "raw": tx.group(1)})
    return out

def fetch_posts(max_pages=3):
    seen, allp, before = set(), [], None
    for _ in range(max_pages):
        url = f"https://t.me/s/{SOURCE}" + (f"?before={before}" if before else "")
        try: r = requests.get(url, headers=UA, timeout=25)
        except Exception: break
        if r.status_code != 200: break
        page = parse_page(r.text)
        if not page: break
        new = [p for p in page if p["id"] not in seen]
        seen.update(p["id"] for p in new); allp += new
        mn = min(p["id"] for p in page)
        if before is not None and mn >= before: break
        before = mn; time.sleep(1)
    return allp

def post_date(iso):
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("Asia/Tehran")).date()
    except Exception:
        return None

def collect():
    """فقط پست‌های همان یک روز؛ خروجی: (رتبه‌بندی، تاریخ)"""
    posts = fetch_posts()
    if not posts: return None, None
    for p in posts: p["date"] = post_date(p["dt"])
    today = datetime.now(ZoneInfo("Asia/Tehran")).date()
    dated = [p for p in posts if p["date"]]
    if not dated: return None, None
    target = today if any(p["date"] == today for p in dated) else max(p["date"] for p in dated)
    score, seen_txt = {}, set()
    for p in (q for q in dated if q["date"] == target):
        t = clean(p["raw"])
        if len(t) < 10 or t[:80] in seen_txt: continue
        seen_txt.add(t[:80])
        low = t.lower()
        if any(a in low or a in t for a in AD_WORDS): continue
        for s in extract_symbols(t):
            score[s] = score.get(s, 0) + 1
    ranked = sorted(score.items(), key=lambda kv: -kv[1])[:TOP_N]
    return ranked, target

def build_screen(ranked, d):
    if ranked is None:
        return "⛔ دریافت اطلاعات امروز ناموفق بود؛ در اجرای بعدی خودکار تلاش می‌شود."
    if not ranked:
        return f"📋 امروز ({d.isoformat()}) پست فیلتری با نماد مشخص ثبت نشده است."
    L = ["🎯 غربالگری بورس — نمادهای منتخب", f"📅 {d.isoformat()}", ""]
    L += [f"{i}. {s}  ×{c}" for i, (s, c) in enumerate(ranked, 1)]
    L += ["", "🤖 خروجی خودکار است؛ توصیه خرید/فروش نیست."]
    return "\n".join(L)

# ───────── اجرا ─────────
if __name__ == "__main__":
    if RUN_MODE in ("morning", "both"):
        send(build_headline())
        print("🌅 سرخطی ارسال شد")
    if RUN_MODE in ("afternoon", "both"):
        ranked, d = collect()
        send(build_screen(ranked, d))
        print("🎯 غربالگری ارسال شد")
    print("✅ پایان")
