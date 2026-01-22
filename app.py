import math
import re
from datetime import datetime

import streamlit as st

# =============================
# BRAND (LOCKED) — v1
# =============================
APP_NAME = "Resale Listing Builder"
TAGLINE = "List faster. Price smarter. Profit confidently."
ACCENT = "#7c3aed"
LOGO_PATH = "logo.svg"  # keep in repo root

# Locked default assumptions (users can still edit the numbers in the tool)
DEFAULT_EBAY_FEE_PCT = 13.25
DEFAULT_PROCESSING_PCT = 2.90
DEFAULT_PROCESSING_FIXED = 0.30
DEFAULT_PACKAGING_COST = 1.50
DEFAULT_SHIP_METHOD = "Ground (est.)"

st.set_page_config(page_title=APP_NAME, page_icon="🧾", layout="wide")

# =============================
# Style
# =============================
st.markdown(
    f"""
    <style>
      :root {{ --accent: {ACCENT}; }}

      .rb-wrap {{ padding-top: 6px; }}
      .rb-header {{
        display:flex; align-items:center; gap:16px;
        padding: 12px 14px;
        border-radius: 16px;
        border: 1px solid rgba(255,255,255,.08);
        background: rgba(255,255,255,.03);
      }}
      .rb-title {{ font-size: 1.7rem; font-weight: 900; margin: 0; line-height: 1.1; }}
      .rb-sub {{ opacity: .76; margin-top: 4px; font-size: 0.98rem; }}
      .rb-divider {{ margin: 14px 0 18px 0; height: 1px; background: rgba(255,255,255,.08); }}
      .rb-hint {{ opacity:.75; font-size: .92rem; }}

      .pill {{
        display:inline-block; padding:6px 10px; border-radius:999px;
        border:1px solid rgba(255,255,255,.10);
        background: rgba(255,255,255,.05);
        font-size:.88rem; opacity:.95;
      }}
      .pill.good {{ border-color: rgba(34,197,94,.35); background: rgba(34,197,94,.12); }}
      .pill.mid  {{ border-color: rgba(245,158,11,.35); background: rgba(245,158,11,.12); }}
      .pill.bad  {{ border-color: rgba(239,68,68,.35); background: rgba(239,68,68,.12); }}

      .card {{
        border-radius: 16px;
        border: 1px solid rgba(255,255,255,.08);
        background: rgba(255,255,255,.03);
        padding: 12px 14px;
      }}
      .card h4 {{ margin:0 0 6px 0; }}
      .muted {{ opacity:.75; }}
      a, a:visited {{ color: var(--accent) !important; }}
      code {{ white-space: pre-wrap !important; }}
    </style>
    """,
    unsafe_allow_html=True
)

# =============================
# Helpers
# =============================
def clean_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def title_case_smart(text: str) -> str:
    if not text:
        return ""
    words = clean_spaces(text).split(" ")
    small = {"a","an","and","as","at","but","by","for","if","in","nor","of","on","or","per","so","the","to","up","via","with","yet"}
    out = []
    for i, w in enumerate(words):
        lw = w.lower()
        if i in (0, len(words)-1) or lw not in small:
            out.append(w[:1].upper() + w[1:])
        else:
            out.append(lw)
    return " ".join(out)

def shipping_estimate(weight_lb: float, shipping_method: str, packaging_cost: float):
    w = max(0.0, float(weight_lb or 0.0))
    if shipping_method == "Local pickup":
        ship = 0.0
    elif shipping_method == "USPS Priority (est.)":
        ship = 8.50 + 1.25 * w
    else:  # Ground
        ship = 6.75 + 1.05 * w

    ship = math.ceil(ship * 4) / 4.0
    return max(0.0, ship + max(0.0, packaging_cost or 0.0))

def fees_estimate(sale_price: float, ebay_final_value_pct: float, payment_processing_pct: float, payment_processing_fixed: float):
    p = max(0.0, float(sale_price or 0.0))
    ebay_fee = p * (max(0.0, ebay_final_value_pct) / 100.0)
    pay_fee = p * (max(0.0, payment_processing_pct) / 100.0) + max(0.0, payment_processing_fixed)
    return ebay_fee, pay_fee

def profit_estimate(sale_price, cogs, ship_cost, ebay_pct, proc_pct, proc_fixed):
    ebay_fee, pay_fee = fees_estimate(sale_price, ebay_pct, proc_pct, proc_fixed)
    profit = float(sale_price or 0) - float(cogs or 0) - float(ship_cost or 0) - ebay_fee - pay_fee
    margin = (profit / sale_price * 100.0) if sale_price and sale_price > 0 else 0.0
    return profit, margin, ebay_fee, pay_fee

def profit_status(profit: float, margin_pct: float):
    """
    Simple & intuitive:
      Good: profit >= $20 OR margin >= 25%
      Thin: profit >= $5  OR margin >= 10%
      Bad: otherwise
    """
    if profit >= 20 or margin_pct >= 25:
        return ("GOOD", "good")
    if profit >= 5 or margin_pct >= 10:
        return ("THIN", "mid")
    return ("BAD", "bad")

def break_even_sale_price(cogs, ship_cost, ebay_pct, proc_pct, proc_fixed):
    """
    Solve for P where:
      P - cogs - ship - (P*ebay%) - (P*proc% + proc_fixed) = 0
    => P*(1 - ebay - proc) = cogs + ship + proc_fixed
    """
    cogs = float(cogs or 0)
    ship_cost = float(ship_cost or 0)
    ebay = max(0.0, float(ebay_pct or 0)) / 100.0
    proc = max(0.0, float(proc_pct or 0)) / 100.0
    fixed = max(0.0, float(proc_fixed or 0))

    denom = 1.0 - ebay - proc
    if denom <= 0:
        return None
    return (cogs + ship_cost + fixed) / denom

def keyword_pack(brand, item, model, key_features):
    base = []
    for x in [brand, item, model]:
        x = clean_spaces(x)
        if x:
            base.append(x)
    feats = [clean_spaces(f) for f in key_features if clean_spaces(f)]

    all_words = []
    for phrase in base + feats:
        all_words.append(phrase)
        all_words += phrase.split(" ")

    seen = set()
    out = []
    for w in all_words:
        w = clean_spaces(w)
        if not w:
            continue
        lw = w.lower()
        if lw in seen:
            continue
        if len(lw) < 3:
            continue
        seen.add(lw)
        out.append(w)
    return out[:30]

def generate_title(brand, item, model, key_features, condition, platform="ebay"):
    parts = []
    if brand: parts.append(brand)
    if item: parts.append(item)
    if model: parts.append(model)

    feat = [clean_spaces(f) for f in key_features if clean_spaces(f)]
    cond_snip = ""
    if condition:
        c = condition.lower()
        if "new" in c and "open" not in c:
            cond_snip = "New"
        elif "open" in c:
            cond_snip = "Open Box"
        elif "used" in c:
            cond_snip = "Used"
        elif "parts" in c or "repair" in c:
            cond_snip = "For Parts/Repair"
        else:
            cond_snip = title_case_smart(condition)

    max_len = 80 if platform == "ebay" else 100
    base = " ".join([p for p in parts if p])
    candidate = base

    for f in feat[:2]:
        trial = clean_spaces(f"{candidate} {f}")
        if len(trial) <= max_len:
            candidate = trial

    if cond_snip:
        trial = clean_spaces(f"{candidate} {cond_snip}")
        if len(trial) <= max_len:
            candidate = trial

    if len(candidate) > max_len:
        candidate = candidate[:max_len].rstrip()

    return title_case_smart(candidate)

def build_description(
    brand, item, model, key_features, condition,
    flaws, whats_included, measurements, notes,
    platform: str
):
    bullets = []
    if brand or item or model:
        bullets.append(f"Item: {clean_spaces(' '.join([x for x in [brand, item, model] if x]))}")
    if condition:
        bullets.append(f"Condition: {condition}")

    feats = [clean_spaces(f) for f in key_features if clean_spaces(f)]
    if feats:
        bullets.append("Key Features: " + "; ".join(feats))

    if measurements:
        bullets.append(f"Measurements: {measurements}")
    if whats_included:
        bullets.append(f"Included: {whats_included}")
    if flaws:
        bullets.append(f"Known Issues/Flaws: {flaws}")
    if notes:
        bullets.append(f"Notes: {notes}")

    protection = []
    if condition and ("parts" in condition.lower() or "repair" in condition.lower()):
        protection.append("⚠️ Sold AS-IS for parts/repair. No guarantees. Not fully tested unless stated.")
        protection.append("⚠️ Buyer is responsible for ensuring compatibility / fit / function.")

    if platform == "fb":
        intro = "Available for pickup or shipping. Details below:"
        outro = "Message me if you want it (include your ZIP for a shipping quote) or to arrange pickup."
    else:
        intro = "Please review the details below before purchasing:"
        outro = "Fast handling. Please message with any questions before buying."

    lines = [intro, ""]
    for p in protection:
        lines.append(p)
    if protection:
        lines.append("")

    for b in bullets:
        lines.append(f"• {b}")

    lines += ["", outro]
    return "\n".join(lines)

# =============================
# Header
# =============================
st.markdown("<div class='rb-wrap'>", unsafe_allow_html=True)

hcol1, hcol2 = st.columns([0.20, 0.80], vertical_alignment="center")
with hcol1:
    try:
        st.image(LOGO_PATH, width=140)
    except Exception:
        st.markdown(
            "<div style='width:140px;height:140px;border-radius:20px;border:1px solid rgba(255,255,255,.10);"
            "background:rgba(255,255,255,.03);display:flex;align-items:center;justify-content:center;'>"
            "<div style='width:12px;height:12px;border-radius:999px;background:var(--accent);box-shadow:0 0 20px var(--accent);'></div>"
            "</div>",
            unsafe_allow_html=True
        )

with hcol2:
    st.markdown(f"<div class='rb-title'>{APP_NAME}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='rb-sub'>{TAGLINE}</div>", unsafe_allow_html=True)
    st.markdown("<div class='rb-hint'>Tip: choose <b>For Parts/Repair</b> for broken items → auto-add protection text.</div>", unsafe_allow_html=True)

st.markdown("<div class='rb-divider'></div>", unsafe_allow_html=True)

# =============================
# Main App Tabs (Customer-facing)
# =============================
tab_builder, tab_flip, tab_help = st.tabs(["🧾 Listing Builder", "✅ Flip Checker", "ℹ️ How it works"])

# =============================
# TAB 1 — Listing Builder
# =============================
with tab_builder:
    top_actions = st.columns([0.75, 0.25])
    with top_actions[1]:
        if st.button("Reset form", use_container_width=True):
            for k in list(st.session_state.keys()):
                if k.startswith("rb_"):
                    del st.session_state[k]
            st.rerun()

    left, right = st.columns([1.1, 0.9], gap="large")

    with left:
        st.subheader("1) Item info")
        a, b = st.columns(2)
        with a:
            brand = st.text_input("Brand", placeholder="Apple, DeWalt, Nike, etc.", key="rb_brand")
            item = st.text_input("Item", placeholder="MacBook Pro, Drill, Sneakers, etc.", key="rb_item")
            model = st.text_input("Model / Part # (optional)", placeholder="A1990, DCD791, etc.", key="rb_model")
        with b:
            condition = st.selectbox(
                "Condition",
                ["New", "Open Box", "Used - Good", "Used - Fair", "For Parts/Repair"],
                index=2,
                key="rb_condition"
            )
            category = st.text_input("Category (optional)", placeholder="Electronics, Tools, Home, etc.", key="rb_category")
            quantity = st.number_input("Quantity", min_value=1, max_value=999, value=1, step=1, key="rb_qty")

        st.subheader("2) Features & notes")
        feat_text = st.text_area(
            "Key features (one per line)",
            placeholder="Example:\n16GB RAM\n512GB SSD\nIncludes charger\nTested & works",
            height=140,
            key="rb_feats"
        )
        key_features = [f for f in feat_text.split("\n") if clean_spaces(f)]

        flaws = st.text_input("Known flaws / issues (optional)", placeholder="Small rip, screen crack, missing remote, etc.", key="rb_flaws")
        whats_included = st.text_input("What's included (optional)", placeholder="Charger, box, manuals, accessories, etc.", key="rb_included")
        measurements = st.text_input("Measurements (optional)", placeholder='13" laptop, 10x8x6 in, etc.', key="rb_meas")
        notes = st.text_area("Extra notes (optional)", placeholder="Testing details, pickup info, smoke-free home, etc.", height=90, key="rb_notes")

    with right:
        st.subheader("3) Money math")
        c1, c2 = st.columns(2)
        with c1:
            cogs = st.number_input("Your cost (COGS) $", min_value=0.0, value=10.0, step=0.50, key="rb_cogs")
            target_price = st.number_input("Target sale price $", min_value=0.0, value=49.99, step=1.00, key="rb_target")
            weight_lb = st.number_input("Estimated weight (lb)", min_value=0.0, value=2.0, step=0.25, key="rb_wt")
        with c2:
            ebay_pct = st.number_input("eBay fee % (est.)", min_value=0.0, max_value=30.0, value=float(DEFAULT_EBAY_FEE_PCT), step=0.25, key="rb_ebay")
            proc_pct = st.number_input("Processing % (est.)", min_value=0.0, max_value=10.0, value=float(DEFAULT_PROCESSING_PCT), step=0.1, key="rb_proc")
            proc_fixed = st.number_input("Processing fixed ($)", min_value=0.0, max_value=2.0, value=float(DEFAULT_PROCESSING_FIXED), step=0.05, key="rb_fixed")

        ship_method = st.selectbox(
            "Shipping method",
            ["Ground (est.)", "USPS Priority (est.)", "Local pickup"],
            index=["Ground (est.)", "USPS Priority (est.)", "Local pickup"].index(DEFAULT_SHIP_METHOD),
            key="rb_ship_method"
        )
        packaging = st.number_input("Packaging cost ($)", min_value=0.0, max_value=20.0, value=float(DEFAULT_PACKAGING_COST), step=0.25, key="rb_pack")

        est_ship = shipping_estimate(weight_lb, ship_method, packaging)

        # Profit indicator for target price
        p_target, m_target, ebay_fee_t, pay_fee_t = profit_estimate(target_price, cogs, est_ship, ebay_pct, proc_pct, proc_fixed)
        label, css = profit_status(p_target, m_target)

        st.markdown(
            f"""
            <div class="card">
              <h4>Target Profit Snapshot</h4>
              <div class="pill {css}"><b>{label}</b> • Profit ${p_target:,.2f} • Margin {m_target:.1f}%</div><br><br>
              <div class="muted">Shipping+packaging: <b>${est_ship:,.2f}</b> ({ship_method})</div>
              <div class="muted">Est. fees: eBay <b>${ebay_fee_t:,.2f}</b> + processing <b>${pay_fee_t:,.2f}</b></div>
            </div>
            """,
            unsafe_allow_html=True
        )

        be = break_even_sale_price(cogs, est_ship, ebay_pct, proc_pct, proc_fixed)
        if be is None:
            st.warning("Your fee % settings are too high to compute a break-even price.")
        else:
            st.info(f"Break-even sale price (est.): **${be:,.2f}**")

        st.subheader("Quick pricing tiers")
        low = round(target_price * 0.85, 2)
        mid = round(target_price, 2)
        high = round(target_price * 1.15, 2)

        for label2, price in [("Low (fast sale)", low), ("Target", mid), ("High (patient)", high)]:
            profit, margin, ebay_fee, pay_fee = profit_estimate(price, cogs, est_ship, ebay_pct, proc_pct, proc_fixed)
            status_txt, status_css = profit_status(profit, margin)
            st.markdown(
                f"""
                <div class="card" style="margin-top:10px;">
                  <div style="display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap;">
                    <div><b>{label2}: ${price:,.2f}</b></div>
                    <div class="pill {status_css}"><b>{status_txt}</b> • ${profit:,.2f} • {margin:.1f}%</div>
                  </div>
                  <div class="muted" style="margin-top:6px;">
                    Shipping+packaging: <b>${est_ship:,.2f}</b> • Fees: eBay <b>${ebay_fee:,.2f}</b> + processing <b>${pay_fee:,.2f}</b>
                  </div>
                </div>
                """,
                unsafe_allow_html=True
            )

    # =============================
    # Outputs (Copy-ready)
    # =============================
    st.subheader("4) Generate listings (copy-ready)")

    ebay_title = generate_title(brand, item, model, key_features, condition, platform="ebay")
    fb_title = generate_title(brand, item, model, key_features, condition, platform="fb")

    ebay_desc = build_description(
        brand, item, model, key_features, condition,
        flaws, whats_included, measurements, notes,
        platform="ebay"
    )
    fb_desc = build_description(
        brand, item, model, key_features, condition,
        flaws, whats_included, measurements, notes,
        platform="fb"
    )

    keywords = keyword_pack(brand, item, model, key_features)
    keywords_csv = ", ".join(keywords)

    out1, out2 = st.tabs(["eBay Listing", "Facebook Listing"])

    with out1:
        st.markdown("### eBay")
        st.caption("Click the copy icon on the right side of each code box.")
        st.markdown("**Title (<=80 chars)**")
        st.code(ebay_title, language="text")
        st.markdown("**Description**")
        st.code(ebay_desc, language="text")
        st.markdown("**Keywords**")
        st.code(keywords_csv, language="text")

    with out2:
        st.markdown("### Facebook Marketplace")
        st.caption("Click the copy icon on the right side of each code box.")
        st.markdown("**Title**")
        st.code(fb_title, language="text")
        st.markdown("**Description**")
        st.code(fb_desc, language="text")
        st.markdown("**Keywords/Tags**")
        st.code(keywords_csv, language="text")

# =============================
# TAB 2 — Flip Checker (YES / MAYBE / NO)
# =============================
with tab_flip:
    st.subheader("Flip Checker (before you buy)")
    st.write("Quickly decide if an item is worth flipping based on **real profit after fees + shipping**.")

    c1, c2, c3 = st.columns(3)
    with c1:
        buy_price = st.number_input("Buy price (what you pay) $", min_value=0.0, value=20.0, step=1.0, key="rb_fc_buy")
        expected_sale = st.number_input("Expected sale price $", min_value=0.0, value=60.0, step=1.0, key="rb_fc_sale")
    with c2:
        wt = st.number_input("Estimated weight (lb)", min_value=0.0, value=2.0, step=0.25, key="rb_fc_wt")
        ship_method_fc = st.selectbox("Shipping method", ["Ground (est.)", "USPS Priority (est.)", "Local pickup"], index=0, key="rb_fc_ship")
    with c3:
        ebay_pct_fc = st.number_input("eBay fee % (est.)", min_value=0.0, max_value=30.0, value=float(DEFAULT_EBAY_FEE_PCT), step=0.25, key="rb_fc_ebay")
        proc_pct_fc = st.number_input("Processing % (est.)", min_value=0.0, max_value=10.0, value=float(DEFAULT_PROCESSING_PCT), step=0.1, key="rb_fc_proc")
        proc_fixed_fc = st.number_input("Processing fixed ($)", min_value=0.0, max_value=2.0, value=float(DEFAULT_PROCESSING_FIXED), step=0.05, key="rb_fc_fixed")

    pack_fc = st.number_input("Packaging cost ($)", min_value=0.0, max_value=20.0, value=float(DEFAULT_PACKAGING_COST), step=0.25, key="rb_fc_pack")

    est_ship_fc = shipping_estimate(wt, ship_method_fc, pack_fc)
    profit_fc, margin_fc, ebay_fee_fc, pay_fee_fc = profit_estimate(expected_sale, buy_price, est_ship_fc, ebay_pct_fc, proc_pct_fc, proc_fixed_fc)
    status_txt, status_css = profit_status(profit_fc, margin_fc)

    # Decision rules for flip checker (simple, clear)
    # YES: profit>=20 and margin>=20
    # MAYBE: profit>=10 or margin>=12
    # NO: otherwise
    if profit_fc >= 20 and margin_fc >= 20:
        decision = ("YES — BUY IT", "good")
    elif profit_fc >= 10 or margin_fc >= 12:
        decision = ("MAYBE — ONLY IF EASY", "mid")
    else:
        decision = ("NO — PASS", "bad")

    st.markdown(
        f"""
        <div class="card">
          <h4>Decision</h4>
          <div class="pill {decision[1]}"><b>{decision[0]}</b></div><br><br>
          <div><b>Est. profit:</b> ${profit_fc:,.2f} &nbsp; • &nbsp; <b>Margin:</b> {margin_fc:.1f}%</div>
          <div class="muted" style="margin-top:6px;">
            Shipping+packaging: <b>${est_ship_fc:,.2f}</b> ({ship_method_fc})<br>
            Fees: eBay <b>${ebay_fee_fc:,.2f}</b> + processing <b>${pay_fee_fc:,.2f}</b>
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    be_fc = break_even_sale_price(buy_price, est_ship_fc, ebay_pct_fc, proc_pct_fc, proc_fixed_fc)
    if be_fc is not None:
        st.info(f"Break-even sale price (est.): **${be_fc:,.2f}**")
    else:
        st.warning("Your fee % settings are too high to compute a break-even price.")

# =============================
# TAB 3 — How it works (Trust + clarity)
# =============================
with tab_help:
    st.subheader("How it works")
    st.write(
        """
This tool helps you create fast listings and estimate real profit after:
- platform fees (eBay final value estimate)
- payment processing
- shipping + packaging

**Quick usage**
1) Fill out item info + features  
2) Enter your cost + target price + weight  
3) Copy the listing output into eBay or Facebook Marketplace  

**For broken items**
Use **For Parts/Repair** — the description automatically includes protection text to reduce headaches.

**Note**
All numbers are **estimates** (shipping and fees vary by item, category, and platform).
        """
    )

st.caption(f"© {datetime.now().year} • {APP_NAME}")
st.markdown("</div>", unsafe_allow_html=True)
