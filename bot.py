# -*- coding: utf-8 -*-
"""فایل: bot.py — سرخطی + غربالگری + پاسخ به دستورهای /a و /b
اجرا: GitHub Actions → daily-scan | حالت‌ها: morning / afternoon / both / poll"""

import os, re, sys, html, time
import requests
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

BALE_TOKEN   = os.environ.get("BALE_TOKEN", "").strip()
BALE_CHAT_ID = os.environ.get("BALE_CHAT_ID", "").strip()
if not BALE_TOKEN or not BALE_CHAT_ID:
    sys.exit("⛔ BALE_TOKEN یا BALE_CHAT_ID در Secrets تنظیم نشده است")

API_URL     = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage"
UPDATES_URL = f"https://tapi.bale.ai/bot{BALE_TOKEN}/getUpdates"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}

SOURCE     = "filterBourseUniversity"
TOP_N      = 25
NEWS_LIMIT = 10
MAXLEN     = 3900

RUN_MODE = os.environ.get("RUN_MODE", "both").strip().lower()   # morning | afternoon | both | poll

# ── وایت‌لیست نمادهای واقعی ──
KNOWN = set("""فولاد فملی فولام بفغل کگل ذوب فماک فنورد فپلا فسپا فنما فخوز فباهنر فبستم
فجام چدن کچاد کگهر کروی نوری کتو شپنا شبریز پارسان شپدیس شبندر شپلی فجر فاذر فکمند
غاذر دفارا دتمد کمند وبملت وبصادر وتجارت وپاسار وبساخت وبشهر وبکویر وامید وتوس
خبازر خبهمن خساپا خگستر خساز خودرو خکرمان غشهد غگل غپینو غنیش سفار سغرب سکرمان
دورو حپترو وهور شستا شگستر کاریزما طلا عیار کارد برکت""".split())
AMBIG = {"طلا", "عیار", "کارد", "برکت", "کاریزما", "فجر"}
KNOWN_BARE = KNOWN - AMBIG

def send(text):
    return send_to(BALE_CHAT_ID, text)

def send_to(chat_id, text):
    payload = {"chat_id": chat_id, "text": text[:4096]}
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

def one_line(s):
    return re.sub(r"\s+", " ", s).strip()

def normalize(s):
    return (s or "").replace("ي", "ی").replace("ك", "ک").replace("أ", "ا") \
                    .replace("إ", "ا").replace("ة", "ه").replace("ؤ", "و")

def fmt(p):
    try: return f"{int(float(str(p).replace(',', ''))):,}"
    except Exception: return str(p)

def pct_suffix(dp):
    try: dv = float(str(dp))
    except (TypeError, ValueError): return ""
    if dv == 0: return ""
    return f"  ({'+' if dv > 0 else ''}{dv:g}%)"

# ───────── سرخطی (صبح و دستور /a) ─────────
def fetch_market():
    cur = {}
    try:
        cur = requests.get("https://call.tgju.org/ajax.json", headers=UA, timeout=20).json().get("current", {}) or {}
    except Exception as e:
        print("tgju err:", str(e)[:90])

    def gfind(*frags):
        for k, v in cur.items():
            kl = k.lower()
            if isinstance(v, dict) and v.get("p") and all(f in kl for f in frags):
                return v
        return None

    rows = []
    def add(name, v):
        if v and v.get("p"): rows.append((name, v.get("p"), v.get("dp")))

    add("دلار",      cur.get("price_dollar_rl") or gfind("dollar") or gfind("usd"))
    add("سکه امامی", cur.get("sekee") or gfind("sekke") or gfind("seke"))
    add("طلای ۱۸",   gfind("geram") or gfind("tala_") or gfind("gold_"))

    idx = []
    for page_url in ("https://www.tgju.org/bourse", "https://www.tgju.org/"):
        try:
            r = requests.get(page_url, headers=UA, timeout=20)
            for name in ("شاخص کل", "شاخص هم‌وزن"):
                if not any(n == name for n, _, _ in idx):
                    m = re.search(name + r".{0,1500}?([\d,]{7,15})", r.text, re.S)
                    if m: idx.append((name, m.group(1), None))
            if len(idx) >= 2: break
        except Exception:
            pass
    if not idx:
        iv = gfind("indices") or gfind("index")
        if iv: idx.append(("شاخص کل", iv.get("p"), iv.get("dp")))
    return idx + rows

def fetch_news(limit=NEWS_LIMIT):
    try:
        r = requests.get("https://boursepress.ir/", headers=UA, timeout=20)
        out, seen = [], set()
        for href, raw in re.findall(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r.text, re.S):
            t = one_line(clean(raw))
            href = html.unescape(href or "").strip()
            if href.startswith("//"):     href = "https:" + href
            elif href.startswith("/"):    href = "https://boursepress.ir" + href
            if len(t) < 25 or not re.search(r"[\u0600-\u06FF]", t): continue
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
            L.append(f"• {name}: {fmt(p)}{pct_suffix(dp)}")
    else:
        L.append("• (نرخ‌ها در این اجرا خوانده نشد)")

    body = "\n".join(L)
    news = fetch_news()
    if news:
        block = "\n\n📰 تیترها (لینک زیر هر تیتر):\n"
        items = []
        for i, (t, u) in enumerate(news, 1):
            item = f"{i}. {t}\n   {u}"
            if len(body) + len(block) + len(item) + 1 > MAXLEN: break
            items.append(item)
        if items:
            body += block + "\n".join(items)
    return body

# ───────── غربالگری (عصر و دستور /b) ─────────
AD_WORDS = ["صرافی","کریپتو","بایننس","تتر","usdt","ترید","کارمزد","تبلیغ","اینستا",
            "واتساپ","واتس","لایسنس","ساپورت","پشتیبانی خرید"]

PATTERNS = [
    r'«([^«»\n]{2,15})»',
    r'#([\w\u0600-\u06FF]{2,15})',
    r'(?:نماد|سهم|سهام)\s*[:：]?\s*([\u0600-\u06FF][\u0600-\u06FF\d]{1,14})',
    r'\(([\u0600-\u06FF][\u0600-\u06FF\d]{1,14})\)',
]
BOUND = r'(?<![\u0600-\u06FF\d]){}(?![\u0600-\u06FF\d])'
KNOWN_ALL    = {normalize(s) for s in KNOWN}
KNOWN_BARE_N = {normalize(s) for s in KNOWN_BARE}

def extract_symbols(t):
    t = normalize(t)
    out = set()
    for pat in PATTERNS:
        for c in re.findall(pat, t):
            c = c.strip(" :：،,.؛()«»!؟?\"'-–")
            if c in KNOWN_ALL: out.add(c)
    for s in KNOWN_BARE_N:
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

# ───────── دستورهای /a و /b (حالت poll) ─────────
CMD_ALIASES = {
    "/a": "news", "/A": "news", "/اخبار": "news",
    "/b": "screen", "/B": "screen", "/غربال": "screen",
}

def get_updates(offset=None, timeout=0):
    params = {"timeout": timeout}
    if offset: params["offset"] = offset
    try:
        r = requests.get(UPDATES_URL, params=params, headers=UA, timeout=60)
        if r.status_code == 200:
            return r.json().get("result", []) or []
        print("getUpdates:", r.status_code, r.text[:120])
    except requests.RequestException as e:
        print("getUpdates err:", str(e)[:90])
    return []

def poll_and_respond():
    updates = get_updates()
    if not updates:
        print("دستور جدیدی نیست")
        return
    max_id, replied, done = 0, 0, 0
    for u in updates:
        uid = u.get("update_id", 0)
        if uid > max_id: max_id = uid
        msg  = u.get("message") or {}
        chat = (msg.get("chat") or {}).get("id")
        text = (msg.get("text") or "").strip()
        if str(chat) != str(BALE_CHAT_ID):   # فقط صاحب ربات
            continue
        cmd = CMD_ALIASES.get(text)
        if not cmd:
            continue
        done += 1
        if done > 6: break                    # سقف ایمنی در هر اجرا
        try:
            if cmd == "news":
                send_to(chat, build_headline())
                print("⚡ /a اجرا شد")
            else:
                ranked, d = collect()
                send_to(chat, build_screen(ranked, d))
                print("⚡ /b اجرا شد")
            replied += 1
        except Exception as e:
            print("cmd err:", str(e)[:150])
            send_to(chat, "⛔ خطا در اجرا؛ لطفاً دوباره امتحان کنید.")
    if max_id:
        get_updates(offset=max_id + 1)        # تأیید: همان‌ها دوباره پردازش نشوند
    print(f"دستورها: {done} | پاسخ داده شد: {replied}")

# ───────── اجرا ─────────
if __name__ == "__main__":
    if RUN_MODE == "poll":
        poll_and_respond()
    else:
        if RUN_MODE in ("morning", "both"):
            try:
                send(build_headline())
                print("🌅 سرخطی ارسال شد")
            except Exception as e:
                print("headline err:", str(e)[:200])
                send("⛔ خطا در ساخت سرخطی؛ در اجرای بعدی تلاش می‌شود.")
        if RUN_MODE in ("afternoon", "both"):
            try:
                ranked, d = collect()
                send(build_screen(ranked, d))
                print("🎯 غربالگری ارسال شد")
            except Exception as e:
                print("screen err:", str(e)[:200])
                send("⛔ خطای غیرمنتظره در غربالگری؛ در اجرای بعدی تلاش می‌شود.")
    print("✅ پایان")
