# -*- coding: utf-8 -*-
"""فایل: bot.py — سرخطی + غربالگری واقعی دیتابورس + /c نماد (چارت) + /d نماد (سطوح)
منابع: databourse.ir (بازار/پول‌هوشمند/تاریخچه) + tgju + بورس‌پرس
حالت‌ها: morning | afternoon | both | poll | listen"""

import os, re, io, sys, html, math, time
import urllib.parse
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

BALE_TOKEN   = os.environ.get("BALE_TOKEN", "").strip()
BALE_CHAT_ID = os.environ.get("BALE_CHAT_ID", "").strip()
if not BALE_TOKEN or not BALE_CHAT_ID:
    sys.exit("⛔ BALE_TOKEN یا BALE_CHAT_ID در Secrets تنظیم نشده است")

BASE        = f"https://tapi.bale.ai/bot{BALE_TOKEN}"
API_URL     = f"{BASE}/sendMessage"
EDIT_URL    = f"{BASE}/editMessageText"
PHOTO_URL   = f"{BASE}/sendPhoto"
UPDATES_URL = f"{BASE}/getUpdates"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}

DB = "https://databourse.ir"          # منبع دادهٔ نمادها — باز از خارج از ایران

TOP_N      = 25
NEWS_LIMIT = 10
MAXLEN     = 3900
MIN_VALUE  = 2_000        # حداقل ارزش معاملات (میلیون ریال) ≈ ۲۰۰ میلیون تومان
SEND_RESULT_AS_NEW = True

RUN_MODE = os.environ.get("RUN_MODE", "both").strip().lower()   # morning|afternoon|both|poll|listen

# ───────── ارسال ─────────
def send_to(chat_id, text, msg_id=None):
    if msg_id:
        for _ in range(2):
            try:
                r = requests.post(EDIT_URL, json={"chat_id": chat_id, "message_id": msg_id,
                                                  "text": text[:4096]}, timeout=30)
                if r.status_code == 200: return True
                print("edit:", r.status_code, r.text[:120])
            except requests.RequestException as e:
                print("edit err:", str(e)[:90])
            time.sleep(2)
    for _ in range(3):
        try:
            r = requests.post(API_URL, json={"chat_id": chat_id, "text": text[:4096]}, timeout=30)
            if r.status_code == 200: return True
            print("send:", r.status_code, r.text[:120])
        except requests.RequestException as e:
            print("send err:", str(e)[:90])
        time.sleep(3)
    return False

def send(text): return send_to(BALE_CHAT_ID, text)

def send_photo(chat_id, buf, caption):
    for _ in range(3):
        try:
            r = requests.post(PHOTO_URL,
                data={"chat_id": chat_id, "caption": caption[:1000]},
                files={"photo": ("signal.jpg", buf.getvalue(), "image/jpeg")}, timeout=60)
            if r.status_code == 200: return True
            print("photo:", r.status_code, r.text[:150])
        except requests.RequestException as e:
            print("photo err:", str(e)[:90])
        time.sleep(3)
    return False

def send_ack(chat_id, text):
    try:
        r = requests.post(API_URL, json={"chat_id": chat_id, "text": text[:4096]}, timeout=30)
        if r.status_code == 200:
            return r.json().get("result", {}).get("message_id")
        print("ack:", r.status_code, r.text[:120])
    except requests.RequestException as e:
        print("ack err:", str(e)[:90])
    return None

# ───────── ابزار متن ─────────
def clean(s):
    s = html.unescape(s or "")
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"[ \t]+", " ", s).strip()

def one_line(s): return re.sub(r"\s+", " ", s).strip()

def normalize(s):
    return (s or "").replace("ي", "ی").replace("ك", "ک").replace("أ", "ا") \
                    .replace("إ", "ا").replace("ة", "ه").replace("ؤ", "و").replace("ـ", "")

def fmt(p):
    try: return f"{int(float(str(p).replace(',', ''))):,}"
    except Exception: return str(p)

def pct_suffix(dp):
    try: dv = float(str(dp))
    except (TypeError, ValueError): return ""
    if dv == 0: return ""
    return f"  ({'+' if dv > 0 else ''}{dv:g}%)"

def avg(xs): return sum(xs) / len(xs)

def to_num(s):
    s = str(s or "").replace(",", "").replace("%", "").strip()
    neg = s.startswith("-") or ("(" in s and ")" in s)
    m = re.search(r'-?\d+\.?\d*', s)
    if not m: return None
    v = float(m.group())
    return -v if neg and v > 0 else v

# ───────── سرخطی (tgju + بورس‌پرس) ─────────
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
            if href.startswith("//"):  href = "https:" + href
            elif href.startswith("/"): href = "https://boursepress.ir" + href
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

# ───────── دیتابورس: پارس جدول‌های SSR ─────────
def split_row(cells):
    """ردیف جدول → (نماد، اعداد ساده به‌ترتیب، درصدهای پرانتزی به‌ترتیب)
    marketwatch:  [نماد، آخرین، (درصد)، پایانی، (درصد)، تعداد، حجم، ارزش]
    smart-money:  [نماد، قدرت، آخرین، (درصد)، پایانی، (درصد)، تعداد، حجم، ارزش]"""
    if not cells: return None, [], []
    sym = normalize(cells[0].strip())
    if not (3 <= len(sym) <= 15) or not re.search(r'[\u0600-\u06FF]', sym):
        return None, [], []
    plain, paren = [], []
    for c in cells[1:]:
        c = c.strip()
        if "(" in c and ")" in c:
            v = to_num(c)
            if v is not None: paren.append(v)
        else:
            v = to_num(c)
            if v is not None: plain.append(v)
    return sym, plain, paren

def rows_of_first_table(html_text):
    tables = re.findall(r'<table[^>]*>(.*?)</table>', html_text, re.S)
    if not tables: return []
    return re.findall(r'<tr[^>]*>(.*?)</tr>', tables[0], re.S)

def cells_of(row_html):
    return [clean(c) for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row_html, re.S)]

def fetch_databourse_market():
    """کل بازار از /marketwatch → لیست دیکشنری نمادها"""
    out = []
    try:
        r = requests.get(f"{DB}/marketwatch", headers=UA, timeout=45)
        if r.status_code != 200:
            print("dbmw status:", r.status_code); return out
        for rr in rows_of_first_table(r.text):
            cells = cells_of(rr)
            sym, plain, paren = split_row(cells)
            if not sym or len(plain) < 5:
                continue
            out.append({"sym": sym, "last": plain[0], "close": plain[1],
                        "count": plain[2], "vol": plain[3], "val": plain[4],
                        "chg": paren[0] if paren else None})
        print(f"marketwatch: {len(out)} نماد")
    except Exception as e:
        print("dbmw err:", str(e)[:90])
    return out

def fetch_smart_money():
    """قدرت خریداران — صفحهٔ ۱ (SSR) + تلاش برای صفحات بعدی → دیکشنری نماد:عدد"""
    out = {}
    try:
        urls = [f"{DB}/filter/smart-money-inflow",
                f"{DB}/filter/smart-money-inflow?page=2",
                f"{DB}/filter/smart-money-inflow?page=3"]
        for url in urls:
            try:
                r = requests.get(url, headers=UA, timeout=40)
                if r.status_code != 200 or len(r.content) < 3000:
                    continue
                added = 0
                for rr in rows_of_first_table(r.text):
                    sym, plain, paren = split_row(cells_of(rr))
                    if not sym or len(plain) < 6: continue
                    power = plain[0]
                    if power is not None and power > 0 and sym not in out:
                        out[sym] = power; added += 1
                print(f"dbsm ...{url[-10:]}: +{added}")
            except Exception as e:
                print("dbsm page err:", str(e)[:80])
        print(f"smart-money total: {len(out)} نماد")
    except Exception as e:
        print("dbsm err:", str(e)[:90])
    return out

# ───────── غربالگری واقعی (تیون‌شده) ─────────
def collect():
    """خروجی: (رتبه‌بندی غنی، تاریخ)"""
    rows = fetch_databourse_market()
    if not rows:
        return None, None
    smart = fetch_smart_money()
    today = datetime.now(ZoneInfo("Asia/Tehran")).date()

    pool = []
    for p in rows:
        if p["count"] is None or p["count"] <= 0:        continue
        if p["val"]  is None or p["val"]  < MIN_VALUE:   continue
        if p["last"] is None or p["last"] <= 0:          continue
        p["sm"] = smart.get(p["sym"])
        pool.append(p)

    if not pool:
        return [], today

    vmax = max((p["val"] for p in pool), default=1) or 1

    def score(p):
        s = 0.0
        s += 30.0 * (math.log10(p["val"] + 10) / math.log10(vmax + 10))
        if p["chg"] is not None:
            if p["chg"] > 0:
                s += min(30.0, 15.0 + p["chg"] * 4)
            elif p["chg"] > -1.0:
                s += 7.0
        if p["sm"] is not None and p["sm"] >= 1.2:
            s += min(40.0, 15.0 + (p["sm"] - 1.2) * 60)
        return s

    pool.sort(key=score, reverse=True)
    ranked = [(p["sym"], round(score(p), 1), p["chg"], p["sm"]) for p in pool[:TOP_N]]
    return ranked, today

def build_screen(ranked, d):
    if ranked is None:
        return "⛔ دریافت دادهٔ بازار ناموفق بود؛ در اجرای بعدی خودکار تلاش می‌شود."
    if not ranked:
        return f"📋 امروز ({d.isoformat()}) نمادی فیلترها را پاس نکرد."
    L = ["🎯 غربالگری بورس — نمادهای منتخب", f"📅 {d.isoformat()}", "",
         "معیارها: نقدشوندگی + رشد قیمت + قدرت خریداران (ورود پول هوشمند)", ""]
    for i, item in enumerate(ranked, 1):
        sym, sc, chg, sm = item[0], item[1], item[2], item[3]
        parts = []
        if chg is not None: parts.append(f"قیمت {chg:+.1f}%")
        if sm is not None:  parts.append(f"قدرت خریدار {sm:.2f}")
        extra = f"  ({' | '.join(parts)})" if parts else ""
        L.append(f"{i}. {sym} — امتیاز {sc}{extra}")
    L += ["", "🔗 جزئیات هر نماد: databourse.ir/symbol/نام‌نماد",
          "🤖 خروجی خودکار است؛ توصیه خرید/فروش نیست."]
    return "\n".join(L)

# ───────── دیتابورس: تاریخچهٔ نماد (/c و /d) ─────────
def extract_js_arrays(html_text):
    arrays = {}
    for m in re.finditer(r'\b(?:let|var|const)\s+(\w+)\s*=\s*\[', html_text):
        name = m.group(1)
        i = m.end() - 1
        depth, j, in_str = 0, i, None
        while j < len(html_text):
            c = html_text[j]
            if in_str:
                if c == '\\': j += 2; continue
                if c == in_str: in_str = None
            else:
                if c in '"\'': in_str = c
                elif c == '[': depth += 1
                elif c == ']':
                    depth -= 1
                    if depth == 0: break
            j += 1
        raw = html_text[i:j+1]
        if len(raw) > 500:
            try:
                arr = __import__("json").loads(raw)
                if isinstance(arr, list) and arr and isinstance(arr[0], dict):
                    arrays[name] = arr
            except Exception:
                pass
    return arrays

def fetch_symbol(sym):
    enc = urllib.parse.quote(sym, safe='')
    try:
        r = requests.get(f"{DB}/symbol/{enc}", headers=UA, timeout=30)
    except requests.RequestException as e:
        print("db sym err:", str(e)[:90]); return None, None
    if r.status_code != 200 or len(r.content) < 5000:
        return None, None
    h = r.text
    company = None
    m = re.search(r'"name":\s*"[^"]+?\s*\(([^)]+)\)', h)
    if m: company = m.group(1).strip()
    return extract_js_arrays(h), company

def pick_series(arrays):
    for name, arr in arrays.items():
        if arr and ("close" in arr[0] or "c" in arr[0]):
            return name, arr, True
    for name, arr in arrays.items():
        if arr and ("value" in arr[0] or "v" in arr[0]):
            return name, arr, False
    return None, None, False

def series_from(arr):
    pts = []
    for it in arr:
        d = str(it.get("date", "")).strip()
        ks = set(it.keys())
        try:
            if "close" in ks or "c" in ks:
                o  = float(it.get("open")  or it.get("o"))
                h_ = float(it.get("high")  or it.get("h"))
                l_ = float(it.get("low")   or it.get("l"))
                c_ = float(it.get("close") or it.get("c"))
                pts.append({"d": d, "o": o, "h": h_, "l": l_, "c": c_})
            elif "value" in ks or "v" in ks:
                pts.append({"d": d, "c": float(it.get("value", it.get("v")))})
        except (TypeError, ValueError):
            continue
    return pts

def rsi14(closes, n=14):
    if len(closes) < n + 1: return 50.0
    g = l = 0.0
    for i in range(1, n + 1):
        ch = closes[i] - closes[i-1]
        g += max(ch, 0); l += max(-ch, 0)
    ag, al = g / n, l / n
    for i in range(n + 1, len(closes)):
        ch = closes[i] - closes[i-1]
        ag = (ag * (n - 1) + max(ch, 0)) / n
        al = (al * (n - 1) + max(-ch, 0)) / n
    if al == 0: return 100.0
    return 100 - 100 / (1 + ag / al)

def _plot(pts, sym, company, ohlc):
    n = len(pts)
    closes = [p["c"] for p in pts]
    ma20 = [avg(closes[i-19:i+1]) if i >= 19 else None for i in range(n)]
    ma50 = [avg(closes[i-49:i+1]) if i >= 49 else None for i in range(n)]
    sup, res = min(closes[-60:]), max(closes[-60:])
    chg = (closes[-1] / closes[-2] - 1) * 100

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    fig, ax = plt.subplots(figsize=(11, 6))
    xs = list(range(n))
    if ohlc:
        for i, p in enumerate(pts):
            col = "#26a69a" if p["c"] >= p["o"] else "#ef5350"
            ax.plot([i, i], [p["l"], p["h"]], color=col, lw=0.8, zorder=1)
            ax.add_patch(Rectangle((i - 0.35, min(p["o"], p["c"])), 0.7,
                                   max(abs(p["c"] - p["o"]), 1e-9),
                                   facecolor=col, edgecolor=col, zorder=2))
    else:
        ax.plot(xs, closes, color="#1e88e5", lw=1.4, label="قیمت پایانی")
    ax.plot(xs, ma20, label="MA20", color="#f0a30a", lw=1.2)
    ax.plot(xs, ma50, label="MA50", color="#3f51b5", lw=1.2)
    ax.axhline(res, color="#ef5350", ls="--", lw=0.9)
    ax.axhline(sup, color="#26a69a", ls="--", lw=0.9)
    ticks = list(range(0, n, max(1, n // 8)))
    ax.set_xticks(ticks)
    ax.set_xticklabels([pts[i]["d"][5:10] for i in ticks], fontsize=8)
    ax.legend(loc="upper left", fontsize=8); ax.grid(alpha=0.25)
    ax.set_title("Price / MA20 / MA50 / 60d High-Low", fontsize=9)
    buf = io.BytesIO()
    fig.savefig(buf, format="jpeg", dpi=110, bbox_inches="tight")
    plt.close(fig); buf.seek(0)

    ttl = f"{sym} ({company})" if company else sym
    cap = (f"📈 سیگنال «{ttl}»\n"
           f"• آخرین قیمت: {fmt(closes[-1])} ({chg:+.1f}%)\n"
           f"• MA20: {fmt(ma20[-1] or closes[-1])} | MA50: {fmt(ma50[-1] or closes[-1])}\n"
           f"• سقف/کف ۶۰ روزه: {fmt(res)} / {fmt(sup)}\n"
           f"🤖 نمودار تحلیلی است؛ توصیه خرید/فروش نیست.")
    return buf, cap

def build_chart(sym):
    arrays, company = fetch_symbol(sym)
    if arrays is None:
        return None, f"❓ نماد «{sym}» در دیتابورس پیدا نشد (املای نماد را چک کنید)."
    _, arr, ohlc = pick_series(arrays)
    if not arr:
        return None, f"⛔ دادهٔ تاریخی برای «{sym}» ثبت نشده است."
    pts = series_from(arr)
    if len(pts) < 30:
        return None, "⛔ دادهٔ کافی برای این نماد نیست."
    return _plot(pts, sym, company, ohlc)

def build_levels(sym):
    arrays, company = fetch_symbol(sym)
    if arrays is None:
        return f"❓ نماد «{sym}» در دیتابورس پیدا نشد (املای نماد را چک کنید)."
    _, arr, _ = pick_series(arrays)
    if not arr:
        return f"⛔ دادهٔ تاریخی برای «{sym}» ثبت نشده است."
    pts = series_from(arr)
    if len(pts) < 50:
        return "⛔ دادهٔ کافی برای این نماد نیست."
    closes = [p["c"] for p in pts]
    last = closes[-1]
    sup, res = min(closes[-60:]), max(closes[-60:])
    ma20, ma50 = avg(closes[-20:]), avg(closes[-50:])
    r = rsi14(closes)
    rsi_note = ("اشباع خرید — احتیاط از ادامهٔ رشد" if r >= 70
                else "اشباع فروش — پتانسیل بازگشت" if r <= 30 else "محدودهٔ متعادل")
    ttl = f"{sym} ({company})" if company else sym
    return "\n".join([
        f"🧭 سطوح فنی «{ttl}»", "",
        f"• آخرین قیمت: {fmt(last)}",
        f"• حمایت ۶۰ روزه: {fmt(sup)}  ({sup/last*100-100:+.1f}%)",
        f"• مقاومت ۶۰ روزه: {fmt(res)}  ({res/last*100-100:+.1f}%)",
        f"• MA20: {fmt(ma20)} | MA50: {fmt(ma50)}",
        f"• RSI14: {r:.0f} — {rsi_note}", "",
        "🎯 نواحی پیشنهادی بر پایهٔ همین سطوح:",
        f"• ورود تدریجی: نزدیک {fmt(sup)} یا برخورد به MA20 در روند صعودی",
        f"• خروج/سودگیری: نزدیک {fmt(res)} یا شکست رو به پایین MA50", "",
        "⚠️ سطوح کلاسیک تکنیکال است؛ تضمین نیست و توصیه خرید/فروش نیست.",
        "منبع داده: دیتابورس"])

# ───────── دستورها ─────────
CMD_MAP = {"a": "news", "b": "screen", "c": "chart", "d": "levels"}
USAGE = ("🤖 دستورها:\n"
         "/a — سرخطی و اخبار\n"
         "/b — غربالگری نمادهای منتخب\n"
         "/c نماد — سیگنال نموداری (مثال: /c فولاد)\n"
         "/d نماد — سطوح ورود و خروج (مثال: /d فملی)")

def parse_cmd(text):
    t = text.strip()
    if t == "/اخبار": return "news", ""
    if t == "/غربال": return "screen", ""
    if t in ("/help", "/start"): return "help", ""
    m = re.match(r"^/([a-dA-D])(?:\s+(.+))?$", t)
    if m:
        arg = (m.group(2) or "").strip().strip("«»'\"،, ")
        return CMD_MAP.get(m.group(1).lower()), arg
    return None, ""

def handle_update(u):
    msg  = u.get("message") or {}
    chat = (msg.get("chat") or {}).get("id")
    text = (msg.get("text") or "").strip()
    if not chat or str(chat) != str(BALE_CHAT_ID): return False
    cmd, arg = parse_cmd(text)
    if not cmd: return False
    if cmd == "help":
        send_to(chat, USAGE); return True
    ack_text = {"news": "🔎 در حال دریافت اخبار و جمع‌آوری داده‌های بورسی...",
                "screen": "📈 درحال تحلیل بازار بورسی...",
                "chart": f"📊 در حال ساخت سیگنال «{arg}»...",
                "levels": f"🧭 در حال محاسبهٔ سطوح «{arg}»..."}.get(cmd, "⏳ در حال پردازش...")
    ack_id = send_ack(chat, ack_text)
    try:
        if cmd == "news":
            result = build_headline()
        elif cmd == "screen":
            ranked, d = collect()
            result = build_screen(ranked, d)
        elif cmd in ("chart", "levels"):
            if not arg:
                send_to(chat, "❓ اسم نماد را جلوی دستور بنویسید. مثال: /c فولاد", msg_id=ack_id)
                return True
            if cmd == "chart":
                buf, caption = build_chart(arg)
                if buf is None:
                    send_to(chat, caption, msg_id=ack_id); return True
                ok = send_photo(chat, buf, caption)
                send_to(chat, "✅ سیگنال آماده و ارسال شد." if ok else "⚠️ ارسال تصویر ناموفق؛ نسخهٔ متنی:",
                        msg_id=ack_id)
                if not ok: send_to(chat, caption)
                return True
            result = build_levels(arg)
        else:
            return False
        if ack_id: send_to(chat, result, msg_id=ack_id)
        else:      send_to(chat, result)
        if SEND_RESULT_AS_NEW and ack_id and cmd in ("news", "screen"):
            send_to(chat, "📩 " + result.splitlines()[0])
        return True
    except Exception as e:
        print("cmd err:", str(e)[:150])
        body = "⛔ خطا در اجرا؛ لطفاً دوباره امتحان کنید."
        if ack_id: send_to(chat, body, msg_id=ack_id)
        else:      send_to(chat, body)
        return False

def get_updates(offset=None, timeout=0):
    params = {"timeout": timeout}
    if offset: params["offset"] = offset
    try:
        r = requests.get(UPDATES_URL, params=params, headers=UA, timeout=max(70, timeout + 20))
        if r.status_code == 200:
            return r.json().get("result", []) or []
        print("getUpdates:", r.status_code, r.text[:120])
    except requests.RequestException as e:
        print("getUpdates err:", str(e)[:90])
    return []

def poll_and_respond():
    updates = get_updates()
    if not updates:
        print("دستور جدیدی نیست"); return
    last = max(u.get("update_id", 0) for u in updates)
    get_updates(offset=last + 1)              # تأیید فوری → بدون پاسخ تکراری
    done = 0
    for u in updates:
        if done >= 6: break
        if handle_update(u): done += 1
    print(f"دستورها: {done}")

def listen():
    print("🎧 شنودگر فعال شد — گوش می‌دهم...")
    offset = None
    while True:
        try:
            updates = get_updates(offset=offset, timeout=50)
            if updates:
                last = max(u.get("update_id", 0) for u in updates)
                get_updates(offset=last + 1, timeout=0)   # تأیید فوری
                offset = last + 1
                for u in updates:
                    try: handle_update(u)
                    except Exception as e: print("handle err:", str(e)[:150])
            else:
                time.sleep(1)
        except Exception as e:
            print("listen err:", str(e)[:120]); time.sleep(5)

# ───────── اجرا ─────────
if __name__ == "__main__":
    if RUN_MODE == "listen":
        listen()
    elif RUN_MODE == "poll":
        poll_and_respond()
    else:
        if RUN_MODE in ("morning", "both"):
            try:
                send(build_headline()); print("🌅 سرخطی ارسال شد")
            except Exception as e:
                print("headline err:", str(e)[:200])
                send("⛔ خطا در ساخت سرخطی؛ در اجرای بعدی تلاش می‌شود.")
        if RUN_MODE in ("afternoon", "both"):
            try:
                ranked, d = collect()
                send(build_screen(ranked, d)); print("🎯 غربالگری ارسال شد")
            except Exception as e:
                print("screen err:", str(e)[:200])
                send("⛔ خطای غیرمنتظره در غربالگری؛ در اجرای بعدی تلاش می‌شود.")
    print("✅ پایان")
