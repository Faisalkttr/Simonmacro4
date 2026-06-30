"""
Sovereign Macro Execution Engine
=================================
Execution > Prediction | Survival First

A rule-based, phase-gated capital deployment tool. The system does not
pick assets or predict markets — it classifies the current macro phase
from four liquidity-driven signals, then tells you exactly where this
month's capital (and, in a Pivot, your stored cash reserve) is supposed
to go, with hard-coded protection and trim rules so discipline doesn't
depend on willpower.

Design notes (read this if you're auditing the rebuild):
  - The 7-phase cycle (QT -> Fracture -> Crisis -> Pivot -> Expansion ->
    Euphoria -> Reset) comes from the Philosophy & Principles doc. The
    original code only modeled 6 states and had two of its branches
    unreachable (FRACTURE could never fire because QT's condition was a
    strict superset of it). That's fixed below with non-overlapping,
    explicitly ordered conditions.
  - Asset universe (sections/layers/tickers/target weights) is taken
    from the latest Allocations table, not the older, coarser buy
    lists. One real structural change worth knowing: in the old buy
    lists, FNV/WPM lived under "Gold" alongside physical gold. In the
    new Allocations table, FNV/WPM ("Monetary Royalties") moved under
    Energy & Commodity, and Gold is physical-only. That's preserved
    here deliberately, not a bug.
  - Per-state monthly dollar tables are reused from the original
    sovereign_execution_engine.md, with Energy + Materials summed into
    a single "Energy & Commodity" bucket so they map cleanly onto the
    new section structure. EUPHORIA had no dollar table in any source
    file (only a trim rule) — the figures used here are a reasonable
    extrapolation from the stated principle ("trim aggressively,
    convert gains to cash + gold") and are clearly flagged in the UI
    and editable in ASSET_UNIVERSE / STATE_MONTHLY_PLANS below.
  - No cross-session persistence: by request, the user re-enters
    current portfolio values each time the system is opened. This also
    sidesteps Streamlit Cloud's non-persistent filesystem. Because of
    this, the old "accumulated cash_balance" tracking is gone — during
    PIVOT, the engine deploys a configurable percentage of whatever
    Cash value you enter that session, which is simpler and removes an
    entire class of state bugs.
"""

import streamlit as st
import pandas as pd

# ----------------------------------------------------------------------
# PAGE CONFIG
# ----------------------------------------------------------------------
st.set_page_config(
    page_title="Sovereign Execution Engine",
    page_icon="\U0001F9ED",
    layout="wide",
)
st.title("Sovereign Macro Execution Engine")
st.caption("Execution > Prediction | Survival First")

# ----------------------------------------------------------------------
# ASSET UNIVERSE — sections, layers, tickers, target weights
# Source: Allocations table (latest version)
# ----------------------------------------------------------------------
ASSET_UNIVERSE = {
    "BTC": {
        "target_weight": 0.25,
        "layers": {
            "Cold Wallet": {
                "weight": 1.00,
                "tickers": ["BTC"],
                "protocol": "Continuous accumulation. Never fully removed.",
            },
        },
    },
    "Gold": {
        "target_weight": 0.10,
        "layers": {
            "Physical": {
                "weight": 1.00,
                "tickers": ["Physical Gold"],
                "protocol": "Hedge against instability. Strengthens during tightening.",
            },
        },
    },
    "Infra": {
        "target_weight": 0.15,
        "layers": {
            "Hard Assets": {
                "weight": 0.40,
                "tickers": ["TPL", "ADPORTS", "ICTEY"],
                "protocol": "Continuous monthly cash-flow deployment. Never pause.",
            },
            "Grid & Utilities": {
                "weight": 0.40,
                "tickers": ["ABBN", "SU", "NVT", "CEG", "PWR", "CWCO"],
                "protocol": "Capital deployed heavily during broad industrial pullbacks.",
            },
            "Tech-Adjacent": {
                "weight": 0.20,
                "tickers": ["VRT", "BE"],
                "protocol": "Accumulation strictly capped. Trim aggressively on euphoria.",
            },
        },
    },
    "Energy & Commodity": {
        "target_weight": 0.23,
        "layers": {
            "Monetary Royalties": {
                "weight": 0.40,
                "tickers": ["FNV", "WPM"],
                "protocol": "Continuous accumulation. Treat as an extension of physical gold.",
            },
            "Baseload Energy": {
                "weight": 0.40,
                "tickers": ["CCJ", "XOM (light only)"],
                "protocol": "Heavy accumulation during localized geopolitical/regulatory dips.",
            },
            "Industrial Materials": {
                "weight": 0.20,
                "tickers": ["FCX", "BHP", "NEM"],
                "protocol": "Strictly cyclical. Accumulate only when deep in Tier 1 pullbacks.",
            },
        },
    },
    "AI / Semis": {
        "target_weight": 0.10,
        "layers": {
            "Physical Monopolies": {
                "weight": 0.60,
                "tickers": ["TSM", "ASML", "SHECY", "Lasertec (6920.T)"],
                "protocol": "Core accumulation. Focus heavily on ASML/TSM pullbacks. "
                            "Lasertec: accumulate on broad Japanese index liquidations.",
            },
            "Architecture & Robotics": {
                "weight": 0.30,
                "tickers": ["AVGO", "CDNS", "QCOM", "FANUY", "Tokyo Electron (8035.T)", "SNPS"],
                "protocol": "Tactical accumulation. Prioritize FANUY to diversify out of pure "
                            "tech. Trim Tokyo Electron 10% on parabolic euphoria. Cap SNPS "
                            "tightly — buy strictly on -20% valuation resets.",
            },
            "Velocity Applications": {
                "weight": 0.10,
                "tickers": ["NOW", "PANW", "STX"],
                "protocol": "Capped at minimal weight. Zero tolerance for momentum chasing near highs.",
            },
        },
    },
    "EM": {
        "target_weight": 0.07,
        "layers": {
            "India": {
                "weight": 0.40,
                "tickers": ["ABB India", "Siemens India", "Hitachi Energy", "CG Power",
                            "PI Industries", "Sun Pharma", "HCLTech"],
                "protocol": "Accumulate on broad domestic index pullbacks.",
            },
            "GCC": {
                "weight": 0.40,
                "tickers": ["Aramco", "ADCONGAS", "ACWA Power", "STC"],
                "protocol": "Accumulate on regional / oil-price-driven dips.",
            },
            "Other Jurisdiction": {
                "weight": 0.20,
                "tickers": ["HIJP (Japan)", "TLK (Indonesia)", "Vale", "ISDE"],
                "protocol": "Diversification sleeve. Keep strictly capped.",
            },
        },
    },
    "Cash": {
        "target_weight": 0.10,
        "layers": {
            "Dry Powder": {
                "weight": 1.00,
                "tickers": ["Cash / T-Bills"],
                "protocol": "Tactical parking. Not idle — it is future opportunity stored.",
            },
        },
    },
}

SECTIONS = list(ASSET_UNIVERSE.keys())

# Protection rules (sovereign_execution_engine.md — non-negotiable)
FLOORS = {"BTC": 0.20, "Gold": 0.05, "Cash": 0.10}
CEILING = 0.35  # no single section above this, regardless of section

# ----------------------------------------------------------------------
# MONTHLY $ FLOW PER STATE (new monthly contribution, by section)
# Energy + Materials from the original doc are summed into
# "Energy & Commodity" to match the current section structure.
# EUPHORIA has no source-doc figures — flagged as an assumption.
# RESET is treated as a fresh QT cycle.
# ----------------------------------------------------------------------
STATE_MONTHLY_PLANS = {
    "QT": {"BTC": 300, "Gold": 200, "Infra": 150, "Energy & Commodity": 100,
           "AI / Semis": 0, "EM": 0, "Cash": 250},
    "FRACTURE": {"BTC": 200, "Gold": 250, "Infra": 150, "Energy & Commodity": 0,
                 "AI / Semis": 0, "EM": 0, "Cash": 400},
    "CRISIS": {"BTC": 0, "Gold": 0, "Infra": 0, "Energy & Commodity": 0,
               "AI / Semis": 0, "EM": 0, "Cash": 1000},
    "PIVOT": {"BTC": 300, "Gold": 0, "Infra": 100, "Energy & Commodity": 350,
              "AI / Semis": 150, "EM": 100, "Cash": 0},
    "EXPANSION": {"BTC": 250, "Gold": 50, "Infra": 100, "Energy & Commodity": 200,
                  "AI / Semis": 250, "EM": 150, "Cash": 0},
    "EUPHORIA": {"BTC": 100, "Gold": 300, "Infra": 100, "Energy & Commodity": 0,
                 "AI / Semis": 0, "EM": 0, "Cash": 500},
}
STATE_MONTHLY_PLANS["RESET"] = dict(STATE_MONTHLY_PLANS["QT"])

ASSUMED_STATES = {"EUPHORIA", "RESET"}

# Existing-cash redeployment weights during PIVOT (was "SYSTEM BREAK (DEPLOY)")
PIVOT_CASH_DEPLOY_WEIGHTS = {
    "BTC": 0.40, "Energy & Commodity": 0.35, "AI / Semis": 0.10,
    "Infra": 0.10, "Gold": 0.05, "EM": 0.00, "Cash": 0.00,
}

STATE_ORDER = ["QT", "FRACTURE", "CRISIS", "PIVOT", "EXPANSION", "EUPHORIA", "RESET"]
STATE_COLORS = {
    "QT": "#5b7fb4", "FRACTURE": "#d98c3a", "CRISIS": "#c0392b",
    "PIVOT": "#27ae60", "EXPANSION": "#2980b9", "EUPHORIA": "#e67e22", "RESET": "#7f8c8d",
}

# ----------------------------------------------------------------------
# STATE CLASSIFICATION
# Fixes the original bug: branches are mutually exclusive and ordered
# from most to least severe within each liquidity regime, so every
# condition is actually reachable.
# ----------------------------------------------------------------------
def classify_state(liquidity: float, yields: float, dxy: float, credit: float, t: dict):
    """
    liquidity, yields, dxy, credit are trend inputs (e.g. 3-month change,
    as a decimal: 0.02 = +2%). Returns (state, rationale).
    """
    if liquidity < 0:
        if credit > t["crisis_credit"]:
            return "CRISIS", (
                f"Liquidity contracting and credit spreads widening sharply "
                f"(> {t['crisis_credit']:.1%}) — classic panic / system-break signature."
            )
        elif dxy > t["fracture_dxy"]:
            return "FRACTURE", (
                f"Liquidity contracting and DXY rising sharply (> {t['fracture_dxy']:.1%}) "
                f"— tightening turning disorderly."
            )
        else:
            return "QT", "Liquidity contracting, no acute stress yet — standard tightening regime."
    else:
        if credit > t["pivot_credit"]:
            return "PIVOT", (
                f"Liquidity has turned positive while credit spreads remain elevated "
                f"(> {t['pivot_credit']:.1%}) — the early, most critical pivot window."
            )
        elif dxy < t["euphoria_dxy"] and yields < t["euphoria_yields"] and credit < t["euphoria_credit"]:
            return "EUPHORIA", (
                "Liquidity strongly positive with DXY, yields and credit spreads all "
                "falling / complacent — late-cycle euphoria conditions."
            )
        else:
            return "EXPANSION", "Liquidity positive, no euphoric extremes — normal risk-on expansion."


def trim_alert_for_gain(gain_pct: float) -> str:
    if gain_pct >= 0.80:
        return "Trim 20-30%"
    elif gain_pct >= 0.50:
        return "Trim 10-15%"
    return "—"


# ----------------------------------------------------------------------
# SIDEBAR — signals, thresholds, contribution, overrides
# ----------------------------------------------------------------------
with st.sidebar:
    st.header("Monthly Contribution")
    monthly_contribution = st.number_input(
        "New capital this month ($)", min_value=0, value=1000, step=50,
    )

    st.header("Macro Signals")
    st.caption("Enter trailing trend (e.g. 3-month change) for each, as a percentage.")
    liq_trend = st.number_input("Liquidity trend (%)", value=-0.2, step=0.1, format="%.2f") / 100
    yields_trend = st.number_input("Yields trend (%)", value=0.3, step=0.1, format="%.2f") / 100
    dxy_trend = st.number_input("DXY trend (%)", value=1.5, step=0.1, format="%.2f") / 100
    credit_trend = st.number_input("Credit spread trend (%)", value=-1.0, step=0.1, format="%.2f") / 100

    with st.expander("Advanced: classifier thresholds"):
        t = {
            "crisis_credit": st.number_input("Crisis credit-spread trigger (%)", value=5.0, step=0.5) / 100,
            "fracture_dxy": st.number_input("Fracture DXY trigger (%)", value=2.0, step=0.5) / 100,
            "pivot_credit": st.number_input("Pivot credit-spread trigger (%)", value=3.0, step=0.5) / 100,
            "euphoria_dxy": st.number_input("Euphoria DXY ceiling (%)", value=-1.0, step=0.5) / 100,
            "euphoria_yields": st.number_input("Euphoria yields ceiling (%)", value=-1.0, step=0.5) / 100,
            "euphoria_credit": st.number_input("Euphoria credit-spread ceiling (%)", value=0.0, step=0.5) / 100,
        }

    st.header("Manual Override")
    override = st.selectbox("Force a state (optional)", ["Auto (signal-based)"] + STATE_ORDER)

    st.header("Pivot Settings")
    pivot_deploy_pct = st.slider("% of current cash to deploy in Pivot", 0, 100, 30) / 100

# ----------------------------------------------------------------------
# STATE RESOLUTION
# ----------------------------------------------------------------------
auto_state, rationale = classify_state(liq_trend, yields_trend, dxy_trend, credit_trend, t)
if override != "Auto (signal-based)":
    state = override
    if state == auto_state:
        rationale = f"Manual override matches signal-based read. {rationale}"
    else:
        rationale = f"Manually overridden to {state}. Signals alone would read: {auto_state} ({rationale})"
else:
    state = auto_state

# ----------------------------------------------------------------------
# SYSTEM STATE DISPLAY
# ----------------------------------------------------------------------
st.subheader("System State")

badge_color = STATE_COLORS.get(state, "#888888")
st.markdown(
    f"<div style='display:inline-block;padding:6px 18px;border-radius:20px;"
    f"background:{badge_color};color:white;font-weight:600;font-size:1.1rem;'>{state}</div>",
    unsafe_allow_html=True,
)
st.write(rationale)
if state in ASSUMED_STATES:
    st.info(
        f"Note: {state} has no explicit dollar table in the source playbook. "
        f"The figures below are a reasonable extrapolation from the stated "
        f"principles (review/edit `STATE_MONTHLY_PLANS` in code if you disagree)."
    )

c1, c2, c3, c4 = st.columns(4)
c1.metric("Liquidity", f"{liq_trend:+.2%}")
c2.metric("Yields", f"{yields_trend:+.2%}")
c3.metric("DXY", f"{dxy_trend:+.2%}")
c4.metric("Credit Spreads", f"{credit_trend:+.2%}")

# ----------------------------------------------------------------------
# CURRENT PORTFOLIO INPUT
# ----------------------------------------------------------------------
st.subheader("Current Portfolio")
st.caption("Re-enter current values each session — figures are not saved between visits.")

portfolio_values = {}
portfolio_cost_basis = {}

cols = st.columns(len(SECTIONS))
for col, section in zip(cols, SECTIONS):
    with col:
        portfolio_values[section] = st.number_input(
            f"{section} — value ($)", min_value=0.0, value=0.0, step=50.0, key=f"val_{section}"
        )
        portfolio_cost_basis[section] = st.number_input(
            f"{section} — cost basis ($, optional)", min_value=0.0, value=0.0, step=50.0,
            key=f"cb_{section}", help="Used only for the gain-based trim check below."
        )

total_value = sum(portfolio_values.values())

# ----------------------------------------------------------------------
# PROTECTION & TARGET CHECK
# ----------------------------------------------------------------------
st.subheader("Protection & Target Check")

if total_value <= 0:
    st.info("Enter current portfolio values above to see weight checks.")
else:
    rows = []
    for section in SECTIONS:
        weight = portfolio_values[section] / total_value
        target = ASSET_UNIVERSE[section]["target_weight"]
        floor = FLOORS.get(section)
        flags = []
        if floor is not None and weight < floor:
            flags.append(f"below {floor:.0%} floor")
        if weight > CEILING:
            flags.append(f"over {CEILING:.0%} ceiling")
        status = "OK" if not flags else " / ".join(flags)
        rows.append({
            "Section": section,
            "Current %": weight,
            "Target %": target,
            "Floor": floor if floor is not None else float("nan"),
            "Status": status,
        })

    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        column_config={
            "Current %": st.column_config.ProgressColumn("Current %", min_value=0, max_value=0.40, format="%.1f%%"),
            "Target %": st.column_config.NumberColumn("Target %", format="%.1f%%"),
            "Floor": st.column_config.NumberColumn("Floor", format="%.1f%%"),
        },
        hide_index=True,
        use_container_width=True,
    )

# ----------------------------------------------------------------------
# TRIM ALERTS
# ----------------------------------------------------------------------
st.subheader("Trim Alerts")

alerts = []
for section in SECTIONS:
    cb = portfolio_cost_basis[section]
    val = portfolio_values[section]
    if cb > 0:
        gain = (val - cb) / cb
        signal = trim_alert_for_gain(gain)
        if signal != "—":
            alerts.append(f"{section}: up {gain:+.0%} — {signal}")

if state == "EUPHORIA":
    alerts.append("BTC: Euphoria rule — trim 20% regardless of cost basis")
    alerts.append("AI / Semis: Euphoria rule — trim 30% regardless of cost basis")

if alerts:
    for a in alerts:
        st.warning(a)
else:
    st.info("No trim signals.")

# ----------------------------------------------------------------------
# MONTHLY EXECUTION PLAN
# ----------------------------------------------------------------------
st.subheader("Monthly Execution Plan")
st.caption(f"New contribution: ${monthly_contribution:,.0f}  |  State: {state}")

monthly_plan = STATE_MONTHLY_PLANS[state]
# Scale the plan if the user's monthly contribution differs from the $1000 baseline
scale = monthly_contribution / 1000 if monthly_contribution else 0
scaled_plan = {k: v * scale for k, v in monthly_plan.items()}

any_new_money = False
for section, amount in scaled_plan.items():
    if amount <= 0:
        continue
    any_new_money = True
    with st.expander(f"{section} — ${amount:,.0f}", expanded=False):
        for layer_name, layer in ASSET_UNIVERSE[section]["layers"].items():
            layer_amount = amount * layer["weight"]
            st.write(f"**{layer_name}** — ${layer_amount:,.0f}")
            st.write(f"Tickers: {', '.join(layer['tickers'])}")
            if layer["protocol"]:
                st.caption(layer["protocol"])
if not any_new_money:
    st.info("No new-money deployment this state — capital is being routed entirely to Cash.")

# ----------------------------------------------------------------------
# PIVOT: EXISTING CASH REDEPLOYMENT
# ----------------------------------------------------------------------
if state == "PIVOT":
    st.subheader("Pivot: Existing Cash Redeployment")
    cash_on_hand = portfolio_values["Cash"]
    deploy_amount = cash_on_hand * pivot_deploy_pct
    st.write(
        f"Deploying {pivot_deploy_pct:.0%} of current Cash (${cash_on_hand:,.0f}) "
        f"= **${deploy_amount:,.0f}**, in addition to this month's new contribution above."
    )
    if deploy_amount <= 0:
        st.info("Enter a Cash value above to see the redeployment breakdown.")
    else:
        for section, weight in PIVOT_CASH_DEPLOY_WEIGHTS.items():
            sect_amount = deploy_amount * weight
            if sect_amount <= 0:
                continue
            with st.expander(f"{section} — ${sect_amount:,.0f}", expanded=False):
                for layer_name, layer in ASSET_UNIVERSE[section]["layers"].items():
                    layer_amount = sect_amount * layer["weight"]
                    st.write(f"**{layer_name}** — ${layer_amount:,.0f}")
                    st.write(f"Tickers: {', '.join(layer['tickers'])}")

# ----------------------------------------------------------------------
# FULL BUY LIST REFERENCE
# ----------------------------------------------------------------------
with st.expander("Full Buy List Reference (all sections, all states)"):
    for section, data in ASSET_UNIVERSE.items():
        st.markdown(f"**{section}** — target {data['target_weight']:.0%}")
        for layer_name, layer in data["layers"].items():
            st.write(f"- {layer_name} ({layer['weight']:.0%}): {', '.join(layer['tickers'])}")
            if layer["protocol"]:
                st.caption(f"  {layer['protocol']}")

st.divider()
st.caption(
    "Execution Rule: Open system → Execute → Close system. No thinking. No override "
    "(unless the Manual Override above was deliberately used)."
)
