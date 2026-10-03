# -*- coding: utf-8 -*-
"""فایل: bot.py
بخش ۱: سرخطی بورس (شاخص‌ها + دلار/سکه/طلا + تیترهای بورس‌پرس)
بخش ۲: غربالگری رله‌ای از کانال عمومی filterBourseUniversity
اجرا: GitHub Actions → daily-scan"""

import os, re, html, time
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

BALE_TOKEN   = os.environ["BALE_TOKEN"]
BALE_CHAT_ID = os.environ["BALE_CHAT_ID"]
API_URL = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}

# ✅ کانال تنظیم‌شده — بعداً برای افزودن کانال دیگر فقط همین لیست را گسترش دهید
CHANNELS = ["filterBourseUniversity"]

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

# ───────── بخش ۱: سرخطی ─────────
def fetch_news(limit=12):
    try:
        r = requests.get("https://boursepress.ir/", headers=UA, timeout=20)
        seen, out = set(), []
        for l in map(clean, re.findall(r">([^<>]{25,140})</a>", r.text)):
            if len(l) >= 25 and re.search(r"[\u0600-\u06FF]", l) and l not in seen:
                seen.add(l); out.append(l)
        print(f"اخبار: {len(out)}")
        return out[:limit]
    except Exception as e:
        print("news err:", str(e)[:90]); return []

def fetch_market():
    cur = {}
    try: cur = requests.get("https://call.tgju.org/ajax.json", headers=UA, timeout=20).json().get("current", {})
    except Exception as e: print("tgju err:", str(e)[:90])
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
    else:
        L.append("• (شاخص‌ها در این اجرا خوانده نشد)")
    news = fetch_news()
    if news:
        L += ["", "📰 تیترهای بورس‌پرس:"]
        L += [f"{i}. {t}" for i, t in enumerate(news, 1)]
    L += ["", "ℹ️ خبر و داده است؛ توصیه خرید/فروش نیست."]
    return "\n".join(L)

# ───────── بخش ۲: غربالگری رله‌ای ─────────
STOP = set("""بورس فرابورس شاخص بازار نماد سهام سهم خرید فروش سود زیان ورود خروج پول هوشمند
سیگنال تحلیل تکنیکال بنیادی گزارش امروز فردا هفته ماه قیمت هدف حد ضرر سبد پیشنهاد توصیه
سرمایه گذاران معاملات حقوقی حقیقی نقدینگی تقاضا عرضه صف دلار سکه طلا اونس تتر ریال تورم
بانک مرکزی مجمع افزایش شفافیت گروه صنعتی تولید شرکت میلیارد میلیون ریالی درصد
فیلتر کانال عضویت لینک ادامه توضیحات آموزش دانلود عکس ویدیو مهم فوری دانشگاه
دیده بان جدول ستون ردیف کد نویسی فرمول دستور تعریف متغیر مقدار شرط خروجی""".split())

SEED = ["فولاد","فملی","شستا","شپنا","وبملت","خساپا","ذوب","کگل","فولام","بفغل","غپینو",
        "شپدروا","فجر","کچاد","کگهر","پارسان","حپترو","تپمو","وهور","شبندر","غشهد","فنورد","کاریزما"]

def extract_symbols(t):
    cands  = set(re.findall(r'«([^«»\n]{3,15})»', t))
    cands |= set(re.findall(r'#([\w\u0600-\u06FF]{3,15})', t))
    cands |= set(re.findall(r'(?:نماد|سهم)[:\s]+([\u0600-\u06FF]{3,15})', t))
    cands |= set(re.findall(r'\(([\u0600-\u06FF]{3,15})\)', t))
    cands |= set(s for s in SEED if s in t)
    out = set()
    for c in cands:
        c = c.strip(" :：،,.؛()«»")
        if len(c) < 3 or c in STOP or re.fullmatch(r"[\d.,%\-–]+", c): continue
        out.add(c)
    return out

def fetch_channel_posts(ch):
    """دو صفحهٔ آخر پست‌های کانال (~۴۰ پست). خروجی: (لیست پیام، پیام خطا)"""
    r = requests.get(f"https://t.me/s/{ch}", headers=UA, timeout=25)
    if r.status_code != 200:
        return None, f"⛔ {ch}: HTTP {r.status_code}"
    page = r.text
    msgs = re.findall(r'tgme_widget_message_text[^>]*>(.*?)</div>', page, re.S)
    if not msgs:
        msgs = re.findall(r'class="[^"]*message_text[^"]*"[^>]*>(.*?)</div>', page, re.S)
    if not msgs:
        print(f"--- dump {ch} ---"); print(page[:1200])
        return None, f"⚠️ {ch}: باز شد ولی پیام متنی پیدا نشد (لاگ را ببینید)"
    texts = list(msgs)
    # صفحهٔ دوم برای پوشش بیشتر
    ids = [int(i) for i in re.findall(r'data-post="[^"]*/(\d+)"', page)]
    if ids:
        try:
            r2 = requests.get(f"https://t.me/s/{ch}?before={min(ids)}", headers=UA, timeout=25)
            if r2.status_code == 200:
                texts += re.findall(r'tgme_widget_message_text[^>]*>(.*?)</div>', r2.text, re.S)
        except Exception:
            pass
    return texts, None

def relay_screen():
    counts, srcs, posts, diag, seen = {}, {}, [], [], set()
    for ch in CHANNELS:
        ch = ch.strip().lstrip("@")
        if not ch: continue
        try:
            msgs, err = fetch_channel_posts(ch)
            if err:
                diag.append(err); continue
            diag.append(f"📡 {ch}: {len(msgs)} پیام خوانده شد")
            ch_syms = set()
            for m in msgs:
                t = clean(m)
                if len(t) < 10 or t[:80] in seen: continue
                seen.add(t[:80]); posts.append((ch, t))
                for c in extract_symbols(t):
                    ch_syms.add(c)
                    counts[c] = counts.get(c, 0) + 1
                    srcs.setdefault(c, set()).add(ch)
            diag.append(f"✅ {ch}: {len(ch_syms)} نماد استخراج شد")
        except Exception as e:
            diag.append(f"⛔ {ch}: {str(e)[:60]}")
    return counts, srcs, posts, diag

def build_relay(counts, srcs, posts, diag):
    now = datetime.now(ZoneInfo("Asia/Tehran"))
    L = [f"🔬 غربالگری رله‌ای — {now.strftime('%Y-%m-%d %H:%M')}", "", "🧭 منابع:"]
    L += [f"  {d}" for d in diag] or ["  (کانالی تنظیم نشده!)"]
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    top = [(s, c) for s, c in ranked if c >= 2][:10] or ranked[:10]
    L.append("")
    if top:
        L.append("🔥 نمادهای پرتکرار در پست‌های فیلتر امروز:")
        L += [f"{i}. {s} — {c} بار" for i, (s, c) in enumerate(top, 1)]
    else:
        L.append("امروز نماد برجسته‌ای استخراج نشد.")
    L += ["", "📌 نمونه پست‌ها (برای کنترل کیفیت):"]
    for ch, t in sorted(posts, key=lambda x: -len(x[1]))[:3]:
        L.append(f"▪️ [{ch}] {t[:200]}…")
    L += ["", "⚠️ گردآوری خودکار از کانال عمومی است؛ توصیه خرید/فروش نیست."]
    return "\n".join(L)

if __name__ == "__main__":
    send(build_headline())
    c, s, p, d = relay_screen()
    send(build_relay(c, s, p, d))
    print("✅ پایان")
