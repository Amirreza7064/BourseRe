# -*- coding: utf-8 -*-
"""ربات غربالگر بورس v2 — ضد بلاک: کل بازار در یک درخواست"""

import os, time, json, random
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

BALE_TOKEN   = os.environ["BALE_TOKEN"]
BALE_CHAT_ID = os.environ["BALE_CHAT_ID"]
API_URL = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage"

MIN_TODAY_VALUE = 20e9   # حداقل ارزش معاملات امروز (ریال) ≈ ۲ میلیارد تومان
MAX_PE = 15.0
TOP_N  = 12
DEEP_N = 25              # تعدادی که برایشان روند و ورود پول بررسی می‌شود

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Referer": "https://www.tsetmc.com/",
}

def send(text):
    for _ in range(3):
        try:
            r = requests.post(API_URL, json={"chat_id": BALE_CHAT_ID, "text": text}, timeout=30)
            if r.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(3)
    return False

# ───── منبع داده: کل بازار در یک درخواست (API دیده‌بان بازار) ─────
MARKET_URLS = [
    "https://cdn.tsetmc.com/api/MarketWatch/GetMarketWatch",
    "https://cdn.tsetmc.com/api/MarketWatch/GetMarketWatchInit/0",
]

def fetch_market():
    for url in MARKET_URLS:
        for attempt in (1, 2):
            try:
                print(f"GET {url} (تلاش {attempt})")
                r = requests.get(url, headers=HEADERS, timeout=40)
                r.raise_for_status()
                print(f"✅ پاسخ سالم — حجم: {len(r.content)//1024} کیلوبایت")
                return r
            except Exception as e:
                print(f"⛔ {str(e)[:120]}")
                time.sleep(8)
    return None

def parse_market(resp):
    data = json.loads(resp.text)
    items = (((data.get("data") or {}).get("marketWatchList"))
             or data.get("marketWatchList"))
    if not items:
        raise ValueError("ساختار ناشناخته: " + resp.text[:300])
    print("نمونه ردیف: " + json.dumps(items[0], ensure_ascii=False)[:500])

    rows = []
    for it in items:
        sym   = it.get("lVal18AFC") or ""
        name  = it.get("lVal30") or ""
        price = float(it.get("priceLast") or it.get("pClosing") or 0)
        eps   = float(it.get("eps") or 0)
        vol   = float(it.get("qTotTran5J") or 0)
        value = float(it.get("qTotCap") or 0) or vol * price
        pe    = float(it.get("pE") or it.get("pe") or 0)
        if not pe and eps > 0 and price > 0:
            pe = price / eps
        rows.append({"sym": sym, "name": name, "price": price, "pe": pe, "value": value})
    return rows

def screen(rows):
    pool = [r for r in rows
            if r["sym"] and r["price"] > 0 and r["value"] >= MIN_TODAY_VALUE
            and r["pe"] > 0 and r["pe"] <= MAX_PE]
    print(f"پاس‌کرده از فیلتر اولیه: {len(pool)} نماد")
    pool.sort(key=lambda r: (1 / r["pe"]) * (r["value"] ** 0.25), reverse=True)
    return pool[:DEEP_N]

def deep_dive(shortlist):
    out = []
    for i, r in enumerate(shortlist, 1):
        rec = dict(r); rec["trend"] = None; rec["flow"] = None
        try:
            from pytse_client import Ticker
            t = Ticker(r["sym"])
            h = t.history.tail(20)
            if len(h) >= 15:
                rec["trend"] = h["adjClose"].iloc[-1] / h["adjClose"].iloc[0] - 1
            ct = t.client_types.tail(5)
            if len(ct):
                bp = ct["individual_buy_vol"].sum() / max(ct["individual_buy_count"].sum(), 1)
                sp = ct["individual_sell_vol"].sum() / max(ct["individual_sell_count"].sum(), 1)
                rec["flow"] = min(bp / sp, 3) if sp > 0 else 3
        except Exception as e:
            print(f"[{i}] {r['sym']}: {str(e)[:80]}")
        out.append(rec)
        print(f"[{i}] {r['sym']} ✅")
        time.sleep(random.uniform(1.0, 1.8))
    return out

def build_report(recs):
    def score(r):
        s = min(2.5, 12.0 / r["pe"]) * 2 if r["pe"] else 0
        s += 2 if (r["flow"] or 0) >= 1.2 else 0
        s += 1 if (r["trend"] is not None and 0 <= r["trend"] <= 0.30) else 0
        return s
    recs.sort(key=score, reverse=True)
    now = datetime.now(ZoneInfo("Asia/Tehran"))
    lines = [f"📊 غربالگری بورس v2 — {now.strftime('%Y-%m-%d %H:%M')}", ""]
    for i, r in enumerate(recs[:TOP_N], 1):
        trend = f"{r['trend']*100:+.1f}%" if r["trend"] is not None else "—"
        flow  = f"{r['flow']:.2f}"       if r["flow"]  is not None else "—"
        lines.append(
            f"{i}. {r['sym']} ({r['name']})\n"
            f"   P/E: {r['pe']:.1f} | ارزش معاملات: {r['value']/1e9:.0f} میلیارد ریال | "
            f"روند ۲۰ر: {trend} | ورود پول: {flow} | امتیاز: {score(r):.1f}"
        )
    lines += ["", "⚠️ خروجی فیلتر است، نه توصیه خرید."]
    return "\n".join(lines)

def main():
    resp = fetch_market()
    if resp is None:
        send("⛔ دسترسی به TSETMC برقرار نشد؛ در اجرای بعدی خودکار دوباره تلاش می‌شود.")
        return
    try:
        rows = parse_market(resp)
    except Exception as e:
        send("⚠️ ساختار داده TSETMC تغییر کرده است:\n" + str(e)[:1200])
        raise
    pool = screen(rows)
    if not pool:
        send("امروز هیچ نمادی فیلترها را پاس نکرد.")
        return
    send(build_report(deep_dive(pool)))
    print("✅ تمام")

if __name__ == "__main__":
    main()
