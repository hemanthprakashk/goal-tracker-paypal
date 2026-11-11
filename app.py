"""
GOAL SAVER - PayPal AI Hackathon project
-----------------------------------------
Install :  pip install -r requirements.txt
Run     :  streamlit run app.py

Keys go in a .env file (see .env.example):
  PAYPAL_CLIENT_ID, PAYPAL_SECRET  -> developer.paypal.com (Sandbox app)
  GEMINI_API_KEY                   -> free key from aistudio.google.com
  APP_URL                          -> http://localhost:8501 (or your Render link)

HOW PAYPAL IS USED (the core of the app):
  1. User clicks "Save with PayPal"  -> we CREATE a PayPal sandbox order.
  2. User approves it on PayPal      -> PayPal sends them back to APP_URL.
  3. We CAPTURE the order            -> the money counts toward the goal.
  The progress bar and the success chance are driven by these real payments.
"""
import os
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()  # reads your secret keys from the local .env file (never uploaded to GitHub)

SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹",
           "AUD": "A$", "CAD": "C$", "JPY": "¥", "SGD": "S$"}
# Rough backup rates (units per 1 USD), used only if the live rate service is unreachable
FALLBACK_RATES = {"USD": 1, "EUR": 0.92, "GBP": 0.79, "INR": 83, "AUD": 1.5,
                  "CAD": 1.37, "JPY": 150, "SGD": 1.35}
PAYPAL_OK = {"USD", "EUR", "GBP", "AUD", "CAD", "JPY", "SGD"}  # PayPal cannot charge INR here
APP_URL = os.getenv("APP_URL", "http://localhost:8501")  # where PayPal sends the buyer back
PAYPAL = "https://api-m.sandbox.paypal.com"  # sandbox = fake money
WANTS = ["Food Delivery", "Shopping", "Entertainment", "Travel"]  # categories we may suggest cutting
DB = Path("contributions.json")  # our tiny "database" of captured PayPal payments


# ================= HELPER FUNCTIONS (must stay ABOVE the page code) =================
@st.cache_data(ttl=3600)
def get_rates():
    """Live exchange rates (units per 1 USD). Falls back to rough fixed rates."""
    try:
        data = requests.get("https://open.er-api.com/v6/latest/USD", timeout=5).json()
        return {c: data["rates"][c] for c in SYMBOLS}
    except Exception:
        return FALLBACK_RATES


def convert(amount, from_cur, to_cur, rates):
    """Change an amount from one currency to another."""
    return amount / rates[from_cur] * rates[to_cur]


def load_contributions():
    """Read all captured PayPal payments from the file."""
    return json.loads(DB.read_text()) if DB.exists() else []


def save_contribution(order_id, amount, currency):
    """Add one payment. Returns False if this order was already counted."""
    data = load_contributions()
    if any(c["order_id"] == order_id for c in data):
        return False
    data.append({"order_id": order_id, "amount": amount, "currency": currency,
                 "time": time.strftime("%Y-%m-%d %H:%M")})
    DB.write_text(json.dumps(data, indent=2))
    return True


def paypal_token():
    """Log in to PayPal with our Client ID + Secret and get a temporary access token."""
    r = requests.post(f"{PAYPAL}/v1/oauth2/token",
                      auth=(os.getenv("PAYPAL_CLIENT_ID"), os.getenv("PAYPAL_SECRET")),
                      data={"grant_type": "client_credentials"})
    r.raise_for_status()
    return r.json()["access_token"]


def create_order(amount, currency, note):
    """STEP 1: create a PayPal sandbox order. Returns the link where the user approves it."""
    body = {"intent": "CAPTURE",
            "purchase_units": [{"description": note,
                                "amount": {"currency_code": currency,
                                           "value": f"{amount:.0f}" if currency == "JPY" else f"{amount:.2f}"}}],
            "payment_source": {"paypal": {"experience_context": {
                "return_url": APP_URL, "cancel_url": APP_URL}}}}
    r = requests.post(f"{PAYPAL}/v2/checkout/orders", json=body,
                      headers={"Authorization": f"Bearer {paypal_token()}"})
    r.raise_for_status()
    return next(l["href"] for l in r.json()["links"] if l["rel"] in ("payer-action", "approve"))


def capture_order(order_id):
    """STEP 3: after the user approves, capture (collect) the money."""
    r = requests.post(f"{PAYPAL}/v2/checkout/orders/{order_id}/capture",
                      headers={"Authorization": f"Bearer {paypal_token()}",
                               "Content-Type": "application/json"})
    return r.json()


def ask_ai(summary):
    """Ask Google Gemini (free key) for friendly advice. Falls back to a simple tip with no key."""
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return "Add GEMINI_API_KEY to .env for AI advice. Tip: cut your biggest 'want' category first."
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    prompt = ("You are a friendly savings coach. In under 80 words, give practical advice. "
              "Not financial advice.\n" + summary)
    r = requests.post(url, headers={"x-goog-api-key": key},
                      json={"contents": [{"parts": [{"text": prompt}]}]})
    if r.status_code != 200:  # show the real reason instead of crashing
        return f"AI error {r.status_code}: {r.text[:300]}"
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def demo_data(rate):
    """Fake bank data so the app works without any upload."""
    rng = np.random.default_rng(1)
    base = {"Rent": 400, "Food": 150, "Food Delivery": 90,
            "Shopping": 110, "Entertainment": 60, "Travel": 50}
    rows = []
    for month in pd.period_range("2026-01", "2026-10", freq="M"):
        for cat, amt in base.items():
            rows.append({"month": str(month), "category": cat,
                         "amount": round(amt * rate * rng.uniform(0.8, 1.3), 2)})
    return pd.DataFrame(rows)


def get_price_history(item, rate):
    """Fake last 6 months of prices.
    TODO: replace this with a real Channel3 (or any shopping) API call."""
    rng = np.random.default_rng(sum(map(ord, item)))
    start = 300 + rng.integers(0, 500)
    return [(start + i * 8 + int(rng.integers(-12, 12))) * rate for i in range(6)]


# ================= PAGE =================
st.set_page_config(page_title="Goal Saver", page_icon="🎯")
st.title("🎯 Goal Saver: AI savings tracker")

# ---------- CURRENCY ----------
rates = get_rates()
CODE = st.sidebar.selectbox("🌍 Currency", list(SYMBOLS), index=0)
CUR = SYMBOLS[CODE]
rate = rates[CODE]  # how many units of this currency equal 1 USD

# ---------- Coming back from PayPal? Capture the payment ----------
order_id = st.query_params.get("token")
if order_id:
    try:
        result = capture_order(order_id)
        if result.get("status") == "COMPLETED":
            cap = result["purchase_units"][0]["payments"]["captures"][0]["amount"]
            if save_contribution(order_id, float(cap["value"]), cap["currency_code"]):
                st.success(f"✅ PayPal payment of {cap['value']} {cap['currency_code']} received "
                           f"and added to your goal!")
        else:
            st.warning("Payment was not completed (cancelled or not approved).")
    except Exception as e:
        st.error(f"Could not capture the payment: {e}")
    st.query_params.clear()  # so a page refresh does not capture again

# ---------- STEP 1: SPENDING DATA ----------
st.sidebar.header("Your money")
income = st.sidebar.number_input("Monthly income", value=int(1000 * rate))
file = st.sidebar.file_uploader("Bank statement CSV (date, category, amount)", type="csv",
                                 help=f"Amounts are assumed to be in {CODE}")

if file:
    df = pd.read_csv(file)
    df["month"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")
else:
    df = demo_data(rate)
    st.sidebar.info("Using demo data. Upload your own CSV to replace it.")

if st.sidebar.button("🗑️ Reset PayPal payments (testing)"):
    DB.unlink(missing_ok=True)
    st.rerun()

spend_per_month = df.groupby("month")["amount"].sum()
saved_per_month = income - spend_per_month  # what was left each month

# ---------- STEP 2: THE GOAL ----------
st.header("1. Your goal")
c1, c2 = st.columns(2)
goal_name = c1.text_input("What are you saving for?", "Smartphone")
goal_amount = c2.number_input("Goal amount", value=int(3000 * rate))
months = c1.number_input("In how many months?", min_value=1, value=6)
months_done = c2.number_input("Months already passed", min_value=0, value=1)
saved_before = st.number_input("Already saved before (outside PayPal)", value=0)

required = goal_amount / months  # money to save every month

# ---------- STEP 3: SAVE WITH PAYPAL ----------
st.header("2. Save toward your goal with PayPal")
amount = st.number_input("Amount to save now", min_value=1.0, value=float(round(required, 2)),
                         help="Default = your monthly target")
if CODE in PAYPAL_OK:
    charge_cur, charge_amt = CODE, amount
else:  # e.g. INR: charge the USD equivalent
    charge_cur, charge_amt = "USD", convert(amount, CODE, "USD", rates)
    st.caption(f"PayPal sandbox can't charge {CODE}, so you will pay about {charge_amt:,.2f} USD.")
if st.button(f"💸 Save {CUR}{amount:,.2f} with PayPal (sandbox)"):
    try:
        link = create_order(charge_amt, charge_cur, f"Savings for {goal_name}")
        st.markdown(f"[👉 Click here to approve the payment in PayPal]({link})")
    except Exception as e:
        st.error(f"Check your PayPal sandbox keys in .env. ({e})")

payments = load_contributions()
saved_so_far = saved_before + sum(
    convert(p["amount"], p.get("currency", "USD"), CODE, rates) for p in payments)  # driven by real PayPal payments
chance = (saved_per_month >= required).mean() * 100  # % of past months we beat the target

# ---------- STEP 4: PROGRESS + PROBABILITY ----------
st.header("3. How am I doing?")
st.write(f"You must save **{CUR}{required:,.0f} every month**.")
st.progress(min(saved_so_far / goal_amount, 1.0))
st.write(f"Saved {CUR}{saved_so_far:,.0f} of {CUR}{goal_amount:,.0f}")
if payments:
    st.dataframe(pd.DataFrame(payments), use_container_width=True)
st.metric("Chance of reaching the goal", f"{chance:.0f}%",
          help="Share of your past months where you saved at least the monthly target")

expected = required * months_done
behind = expected - saved_so_far
if behind <= 0:
    st.success("✅ You are on track. Keep going!")
else:
    st.warning(f"⚠️ You are {CUR}{behind:,.0f} behind schedule.")

    # ---------- STEP 5: SUGGEST WHAT TO CUT (ONLY IF USER APPROVES) ----------
    months_left = max(months - months_done, 1)
    extra_needed = behind / months_left  # extra saving needed each month
    avg_by_cat = df[df["category"].isin(WANTS)].groupby("category")["amount"].mean()
    top_cat = avg_by_cat.idxmax()  # the "want" where we spend the most
    cut = min(extra_needed, avg_by_cat[top_cat])
    st.info(f"💡 Suggestion: spend {CUR}{cut:,.0f} less per month on **{top_cat}** "
            f"to catch up in {months_left} months.")
    if st.button("✅ Approve this plan"):
        st.success(f"Plan approved! New {top_cat} budget: "
                   f"{CUR}{avg_by_cat[top_cat] - cut:,.0f}/month")

# ---------- STEP 6: PRICE TRACKER ----------
st.header("4. Price watcher")
prices = get_price_history(goal_name, rate)
slope, intercept = np.polyfit(range(6), prices, 1)  # simple straight-line trend
next_price = slope * 6 + intercept
st.line_chart(pd.DataFrame({"price": prices}))
if slope > 0:
    st.error(f"📈 Price is rising. Estimated next month: {CUR}{next_price:,.0f} (just an estimate)")
else:
    st.success(f"📉 Price is falling. Estimated next month: {CUR}{next_price:,.0f} (just an estimate)")
if saved_so_far >= prices[-1]:
    st.balloons()
    st.success(f"🎉 You have saved enough to buy the {goal_name} now!")

# ---------- STEP 7: AI ADVICE ----------
st.header("5. AI coach")
if st.button("Get AI advice"):
    info = (f"Goal: {goal_name} {goal_amount} in {months} months. Saved {saved_so_far}. "
            f"Must save {required:.0f}/month. Chance {chance:.0f}%. "
            f"Average monthly spend by category: {df.groupby('category')['amount'].mean().round(0).to_dict()}. "
            f"Price trend per month: {slope:.1f}.")
    st.write(ask_ai(info))

st.caption("Educational only. Not financial advice.")