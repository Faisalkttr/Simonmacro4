import streamlit as st
import pandas as pd

# --------------------------------------------------
# PAGE CONFIG
# --------------------------------------------------
st.set_page_config(page_title="Sovereign Execution Engine", layout="wide")
st.title("Sovereign Macro Execution Engine")
st.caption("Execution > Prediction | Survival First")

# --------------------------------------------------
# SIMULATED SIGNALS (Replace with your macro engine later)
# --------------------------------------------------
# For now we assume QT environment (you can connect your signals here)

liq_trend = -0.002
dxy_trend = 0.015
credit_trend = -0.01

# --------------------------------------------------
# STATE CLASSIFICATION
# --------------------------------------------------
def classify_state(liq, dxy, credit):
    if liq < 0 and dxy > 0:
        return "QT"
    elif liq < 0 and dxy > 0.02:
        return "FRACTURE"
    elif liq < 0 and credit > 0.05:
        return "SYSTEM_BREAK_EARLY"
    elif liq > 0 and credit > 0:
        return "SYSTEM_BREAK_DEPLOY"
    elif liq > 0:
        return "PIVOT"
    else:
        return "EXPANSION"

state = classify_state(liq_trend, dxy_trend, credit_trend)

# --------------------------------------------------
# CAPITAL ENGINE (WITH CASH TRACKING)
# --------------------------------------------------
st.subheader("💰 Capital Engine")

monthly_capital = 1000

if "cash_balance" not in st.session_state:
    st.session_state.cash_balance = 0

st.metric("Monthly Contribution", f"${monthly_capital}")
st.metric("Available Cash", f"${st.session_state.cash_balance:,.0f}")

# --------------------------------------------------
# EXECUTION LOGIC
# --------------------------------------------------
def get_execution(state, cash):

    plan = {}

    if state == "QT":
        plan = {
            "BTC": 300,
            "Gold": 200,
            "Infra": 150,
            "Energy": 50,
            "Materials": 50,
            "Cash_Add": 250
        }

    elif state == "FRACTURE":
        plan = {
            "BTC": 200,
            "Gold": 250,
            "Infra": 150,
            "Cash_Add": 400
        }

    elif state == "SYSTEM_BREAK_EARLY":
        plan = {
            "Cash_Add": 1000
        }

    elif state == "SYSTEM_BREAK_DEPLOY":
        deploy = int(cash * 0.3)

        plan = {
            "BTC": int(deploy * 0.4),
            "Energy": int(deploy * 0.2),
            "Materials": int(deploy * 0.15),
            "AI": int(deploy * 0.1),
            "Infra": int(deploy * 0.1),
            "Gold": int(deploy * 0.05),
            "Cash_Add": 1000 - deploy
        }

    elif state == "PIVOT":
        plan = {
            "BTC": 300,
            "Energy": 200,
            "Materials": 150,
            "AI": 150,
            "Infra": 100,
            "EM": 100
        }

    elif state == "EXPANSION":
        plan = {
            "AI": 250,
            "BTC": 250,
            "Energy": 200,
            "EM": 150,
            "Infra": 100,
            "Gold": 50
        }

    return plan

plan = get_execution(state, st.session_state.cash_balance)

# --------------------------------------------------
# SYSTEM STATE UI
# --------------------------------------------------
st.subheader("🧭 System State")

c1, c2, c3 = st.columns(3)

c1.metric("State", state)
c2.metric("Liquidity Trend", f"{liq_trend:.2%}")
c3.metric("DXY Trend", f"{dxy_trend:.2%}")

# --------------------------------------------------
# EXECUTION OUTPUT
# --------------------------------------------------
st.subheader("🧾 Monthly Execution")

for asset, amount in plan.items():
    if asset != "Cash_Add" and amount > 0:
        st.write(f"✅ Buy ${amount} → {asset}")

# --------------------------------------------------
# BUY LIST ENGINE (MULTI OPTIONS)
# --------------------------------------------------
st.subheader("📌 Buy List Options")

buy_lists = {
    "BTC": ["BTC (Cold Wallet)"],
    "Gold": ["FNV", "WPM", "Physical"],
    "Infra": ["ABB", "PWR", "NVT", "CWCO"],
    "Energy": ["XOM", "CCJ"],
    "Materials": ["FCX", "BHP", "NEM"],
    "AI": ["TSM", "ASML", "SNPS", "CDNS", "AVGO"],
    "EM": ["India", "GCC", "Japan Metals"]
}

for asset in plan:
    if asset in buy_lists:
        st.write(f"{asset}: {', '.join(buy_lists[asset])}")

# --------------------------------------------------
# CASH ENGINE UPDATE
# --------------------------------------------------
st.subheader("🏦 Cash Flow")

cash_add = plan.get("Cash_Add", 0)

new_cash = st.session_state.cash_balance + cash_add

st.write(f"Added to Cash: ${cash_add}")
st.write(f"New Cash Balance: ${new_cash}")

st.session_state.cash_balance = new_cash

# --------------------------------------------------
# TRIM ENGINE (ALERTS)
# --------------------------------------------------
st.subheader("⚠️ Trim Alerts")

# simple sentiment proxy (replace later)
sentiment = "NEUTRAL"

if sentiment == "EUPHORIA":
    st.warning("Trim BTC 20% → Move to Cash + Gold")
    st.warning("Trim AI 30% → Move to Cash")
else:
    st.info("No trim signals")
