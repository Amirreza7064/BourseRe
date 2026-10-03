# -*- coding: utf-8 -*-
"""فایل: bot.py — سرخطی بورس (تیترهای لینک‌دار) + غربالگری روزانه
اجرا: GitHub Actions → daily-scan"""

import os, re, html, time
import requests
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

BALE_TOKEN   = os.environ["BALE_TOKEN"]
BALE_CHAT_ID = os.environ["BALE_CHAT_ID"]
API_URL = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}

SOURCE        = "filterBourseUniversity"
TOP_N         = 25      # چند نماد برتر ارسال شود
NEWS_LIMIT    = 10      # چند تیتر
SEND_HEADLINE = True    # False = فقط پیام غربالگری

def send(text, html_mode=False):
    payload = {"chat_id": BALE_CHAT_ID, "text": text[:4000]}
    if html_mode: payload["parse_mode"] = "HTML"
    for _ in range(4):
        try:
            r = requests.post(API_URL, json=payload, timeout=30)
            if r.status_code == 200: return True
            if r.status_code == 400 and "parse_mode" in payload:   # فالبک: بدون فرمت
                payload.pop("parse_mode"); continue
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

# ───────── سرخطی: بازار + تیترهای لینک‌دار ─────────
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

def fetch_news(limit=NEWS_LIMIT):
    """خروجی: لیست (عنوان، لینک) از صفحهٔ اصلی بورس‌پرس"""
    try:
        r = requests.get("https://boursepress.ir/", headers=UA, timeout=20)
        out, seen = [], set()
        for href, raw in re.findall(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r.text, re.S):
            t = clean(raw)
            if len(t) < 25 or not re.search(r"[\u0600-\u06FF]", t): continue
            if href.startswith("/"):   href = "https://boursepress.ir" + href
            if not href.startswith("http"): continue
            if href in seen or t in seen: continue
            seen.add(href); seen.add(t)
            out.append((t, href))
            if len(out) >= limit: break
        print("اخبار:", len(out))
        return out
    except Exception as e:
        print("news err:", str(e)[:90]); return []

def build_headline():
    now = datetime.now(ZoneInfo("Asia/Tehran"))
    L = [f"🌅 <b>سرخطی بورس</b> — {now.strftime('%Y-%m-%d %H:%M')}", "", "<b>📊 بازار:</b>"]
    rows = [r for r in fetch_market() if r[1]]
    if rows:
        for name, p, dp in rows:
            d = f"  ({dp}%)" if dp not in (None, "", "0", "0.0") else ""
            L.append(f"• <b>{name}</b>: {fmt(p)}{d}")
    news = fetch_news()
    if news:
        L += ["", "<b>📰 تیترها (برای باز شدن لمس کنید):</b>"]
        for i, (t, u) in enumerate(news, 1):
            L.append(f'{i}. <a href="{html.escape(u, quote=True)}">{html.escape(t)}</a>')
    return "\n".join(L)

# ───────── غربالگری روزانه ─────────
STOP = set("""بورس فرابورس شاخص بازار نماد سهام سهم خرید فروش سود زیان ورود خروج پول هوشمند
سیگنال تحلیل تکنیکال بنیادی گزارش امروز فردا هفته ماه قیمت هدف حد ضرر سبد پیشنهاد توصیه
سرمایه معاملات حقوقی حقیقی نقدینگی تقاضا عرضه صف دلار سکه طلا اونس تتر ریال تومان تورم
فیلتر کانال عضویت لینک ادامه توضیحات آموزش دانلود مهم فوری دانشگاه دیده بان جدول ستون
کد نویسی فرمول دستور تعریف متغیر مقدار شرط خروجی رفقا دوستان سلام صبح عصر شب بخیر
اطلاعیه انتشار تارنما استناد بند ماده مکرر دستورالعمل اجرایی نحوه انجام اوراق بهادار
تشخیص شرکت بنا ایران همراه کریپتو ارزدیجیتال صرافی ممنون خدایا انسان آدم جهان امن
یاد تنهایی شروع خلوت شنبه یکشنبه دوشنبه چهارشنبه پنجشنبه جمعه فروردین اردیبهشت خرداد
تیر مرداد شهریور مهر آبان آذر بهمن اسفند میلیون درصد افزایش کاهش تصمیم هیئت مدیره
تعریف سقف کف میانگین روند کندل حجم ارزش معامله بازگشایی نمادین معاملاتی بسته""".split())

SUFFIX = re.compile(r"(ها|هایی|ترین|های)$")
LETTER = re.compile(r"[\u0620-\u064A\u066E-\u06D5]")

# نمادهای شناخته‌شده: پرانتز فقط برای اینها معتبر است + پیدا شدنشان امتیاز می‌دهد
KNOWN = set("""فولاد فملی فولام بفغل کگل ذوب فماک فنورد فپلا فسپا فایرا فنما فخوز فباهنر فبستم
شپنا پارسان پارس شپدروا پردیس پکرمان شپلی شستا شبریز شگستر وبملت وبصادر وتجارت وپاسار
وبساخت وبکویر وامید خساپا خبهمن خودرو کچاد کگهر کگاز غشهد غپینو غگل کاریزما فیروزا
هانیکو تنوین فجر خودرو شبندر""".split())

AD_WORDS = ["صرافی","کریپتو","بایننس","تتر","usdt","ترید","کارمزد","تبلیغ","اینستا",
            "واتساپ","واتس","لایسنس","ساپورت","پشتیبانی خرید"]

EXPLICIT = [
    r'«([^«»\n]{2,15})»',                                   # «نماد»
    r'#([\w\u0600-\u06FF]{2,15})',                          # #نماد
    r'(?:نماد|سهم|سهام)\s*[:：]?\s*([\u0600-\u06FF][\u0600-\u06FF\d]{2,14})',  # نماد: X
]
PAREN    = r'\(([\u0600-\u06FF][\u0600-\u06FF\d]{2,14})\)'  # (نماد) — فقط KNOWN
BOUND    = r'(?<![\u0600-\u06FF\d]){}(?![\u0600-\u06FF\d])'  # مرز کلمه برای KNOWN

def valid(s):
    if not (3 <= len(s) <= 10): return False
    if "\u200c" in s:           return False      # نماد نیم‌فاصله ندارد
    if s in STOP:               return False
    if SUFFIX.search(s):        return False      # سهام‌ها، ارزان‌ترین ...
    if not LETTER.search(s):    return False
    return not re.fullmatch(r"[\d.,%\-–\s\u06F0-\u06F9]+", s)

def extract_symbols(t):
    t = normalize(t)
    out = set()
    for pat in EXPLICIT:
        for s in re.findall(pat, t):
            s = s.strip(" :：،,.؛()«»!؟?\"'-–")
            if valid(s): out.add(s)
    for s in re.findall(PAREN, t):                 # پرانتز فقط برای نماد شناخته‌شده
        s = s.strip(" :：،,.؛()«»")
        if s in KNOWN: out.add(s)
    for s in KNOWN:                                # نماد شناخته‌شده با مرز کلمه
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
        if any(a in low or a in t for a in AD_WORDS): continue     # پست تبلیغاتی
        syms = extract_symbols(t)
        for s in syms: score[s] = score.get(s, 0) + 1
    ranked = sorted(score.items(), key=lambda kv: -kv[1])[:TOP_N]
    return ranked, target

def build_screen(ranked, d):
    if ranked is None:
        return "⛔ دریافت اطلاعات امروز ناموفق بود؛ در اجرای بعدی خودکار تلاش می‌شود."
    if not ranked:
        return f"📋 امروز ({d.isoformat()}) پست فیلتری با نماد مشخص ثبت نشده است."
    L = ["🎯 <b>غربالگری بورس — نمادهای منتخب</b>", f"📅 {d.isoformat()}", ""]
    L += [f"{i}. <b>{s}</b>  ×{c}" for i, (s, c) in enumerate(ranked, 1)]
    L += ["", "🤖 خروجی خودکار است؛ توصیه خرید/فروش نیست."]
    return "\n".join(L)

if __name__ == "__main__":
    if SEND_HEADLINE:
        send(build_headline(), html_mode=True)
    ranked, d = collect()
    send(build_screen(ranked, d), html_mode=True)
    print("✅ پایان")
