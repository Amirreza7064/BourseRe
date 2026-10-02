# -*- coding: utf-8 -*-
"""ربات غربالگر بورس ← ارسال گزارش به بله | داده‌ها: TSETMC"""

import os, time
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from pytse_client import Ticker, symbols_data

# ── تنظیمات ─────────────────────────────────
BALE_TOKEN   = os.environ["BALE_TOKEN"]       # از Secrets خوانده می‌شود
BALE_CHAT_ID = os.environ["BALE_CHAT_ID"]
API_URL = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage"

WATCHLIST = []             # مثال: ["فولاد", "فملی"] — خالی = اسکن کل بازار
MIN_TRADE_VALUE = 5e12     # حداقل میانگین ارزش معاملات ۲۰ روزه (ریال) = ۵۰۰ میلیارد تومان
MAX_PE = 15                # نمادهایی با P/E بالاتر حذف می‌شوند
TOP_N = 10                 # تعداد نماد برتر در گزارش
SLEEP = 0.35               # مکث بین درخواست‌ها (جلوگیری از بلاک شدن)

def send(text):
    for _ in range(3):
        try:
            r = requests.post(API_URL,
                json={"chat_id": BALE_CHAT_ID, "text": text}, timeout=30)
            if r.status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(3)
    print("❌ ارسال به بله ناموفق بود")

def phase1():
    """فیلتر اولیه سبک: نقدشوندگی + ارزندگی نسبت به صنعت"""
    candidates = []
    symbols = WATCHLIST or symbols_data.all_symbols()
    print(f"تعداد نمادها: {len(symbols)}")
    for i, sym in enumerate(symbols, 1):
        try:
            t = Ticker(sym)
            pe, gpe = t.p_e_ratio, t.group_p_e_ratio
            price, vol20 = t.real_time_price_value, t.volume_20_day
            if not (pe and gpe and price and vol20):
                continue
            if pe <= 0 or pe > MAX_PE or vol20 * price < MIN_TRADE_VALUE:
                continue
            candidates.append((t, gpe / pe))   # نسبت P/E صنعت به سهم (بزرگ‌تر = ارزان‌تر)
            print(f"[{i}] ✅ {sym} | PE={pe:.1f} صنعت={gpe:.1f}")
        except Exception as e:
            print(f"[{i}] ⛔ {sym}: {e}")
        time.sleep(SLEEP)
    return candidates

def phase2(candidates):
    """امتیازدهی نهایی: روند + ورود پول حقیقی"""
    scored = []
    for t, pe_score in candidates:
        try:
            time.sleep(SLEEP)
            hist = t.history.tail(20)
            if len(hist) < 15:
                continue
            trend = hist["adjClose"].iloc[-1] / hist["adjClose"].iloc[0] - 1

            time.sleep(SLEEP)
            ct = t.client_types.tail(5)
            if ct.empty:
                continue
            buy_per  = ct["individual_buy_vol"].sum()  / max(ct["individual_buy_count"].sum(), 1)
            sell_per = ct["individual_sell_vol"].sum() / max(ct["individual_sell_count"].sum(), 1)
            flow = min(buy_per / sell_per, 3) if sell_per > 0 else 3

            score  = min(pe_score, 2.5) * 2            # ارزندگی (سقف ۵ امتیاز)
            score += 2 if flow >= 1.2 else 0           # ورود پول حقیقی
            score += 1 if 0.02 <= trend <= 0.30 else 0 # رشد سالم (نه پامپ)

            scored.append({"sym": t.ticker, "name": t.title, "pe": pe,
                           "gpe": t.group_p_e_ratio, "trend": trend,
                           "flow": flow, "score": score})
        except Exception as e:
            print(f"⛔ {t.ticker}: {e}")
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:TOP_N]

def main():
    print("=== فاز ۱: فیلتر اولیه ===")
    cands = phase1()
    if not cands:
        send("امروز هیچ نمادی فیلترها را پاس نکرد.")
        return
    print(f"=== فاز ۲: امتیازدهی {len(cands)} نماد ===")
    rows = phase2(cands)
    now = datetime.now(ZoneInfo("Asia/Tehran"))
    lines = [f"📊 غربالگری بورس — {now.strftime('%Y-%m-%d %H:%M')}", ""]
    for i, r in enumerate(rows, 1):
        lines.append(
            f"{i}. {r['sym']} ({r['name']})\n"
            f"   P/E: {r['pe']:.1f} | صنعت: {r['gpe']:.1f} | "
            f"روند ۲۰ر: {r['trend']*100:+.1f}% | سرانه خرید/فروش: {r['flow']:.2f} | "
            f"امتیاز: {r['score']:.1f}"
        )
    lines += ["", "⚠️ خروجی فیلتر است، نه توصیه خرید."]
    send("\n".join(lines))
    print("✅ تمام شد")

if __name__ == "__main__":
    main()
