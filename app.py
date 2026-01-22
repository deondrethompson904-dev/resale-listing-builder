import math
import re
from datetime import datetime

import streamlit as st

# =============================
# BRAND (LOCKED)
# =============================
APP_NAME = "Resale Listing Builder"
TAGLINE = "List faster. Price smarter. Profit confidently."
ACCENT = "#7c3aed"
LOGO_PATH = "logo.svg"  # keep this file in repo root

# Locked default assumptions (users can still change numbers in the form)
DEFAULT_EBAY_FEE_PCT = 13.25
DEFAULT_PROCESSING_PCT = 2.90
DEFAULT_PROCESSING_FIXED = 0.30
DEFAULT_PACKAGING_COST = 1.50
DEFAULT_SHIP_METHOD = "Ground (est.)"

st.set_page_config(page_title=APP_NAME, page_icon="🧾", layout="wide")

st.markdown(
    f"""
    <style>
      :root {{
        --accent: {ACCENT};
      }}
      .rb-wrap {{
        padding-top: 4px;
      }}
      .rb-header {{
        display:flex;
        align-items:center;
        gap:16px;
        padding: 10px 12px;
        border-radius: 16px;
        border: 1px solid rgba(255,255,255,.08);
        background: rgba(255,255,255,.03);
      }}
      .rb-title {{
        font-size: 1.6rem;
        font-weight: 900;
        margin: 0;
        line-height: 1.1;
      }}
      .rb-sub {{
        opacity: .75;
        margin-top: 4px;
        font-size: 0.98rem;
      }}
      a, a:visited {{ color: var(--accent) !important; }}
      .rb-divider {{
        margin: 14px 0 18px 0;
        height: 1px;
        background: rgba(255,255,255,.08);
      }}
      .rb-hint {{
        opacity:.7;
        font-size: .92rem;
      }}
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

    # Auto-protection language for For Parts/Repair
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
    st.markdown("<div class='rb-hint'>Tip: For broken electronics, choose <b>For Parts/Repair</b> to auto-add protection text.</div>", unsafe_allow_html=True)

st.markdown("<div class='rb-divider'></div>", unsafe_allow_html=True)

# =============================
# Main UI
# =============================
left, right = st.columns([1.1, 0.9], gap="large")

with left:
    st.subheader("1) Item info")
    a, b = st.columns(2)
    with a:
        brand = st.text_input("Brand", placeholder="Apple, DeWalt, Nike, etc.")
        item = st.text_input("Item", placeholder="MacBook Pro, Drill, Sneakers, etc.")
        model = st.text_input("Model / Part # (optional)", placeholder="A1990, DCD791, etc.")
    with b:
        condition = st.selectbox("Condition", ["New", "Open Box", "Used - Good", "Used - Fair", "For Parts/Repair"], index=2)
        category = st.text_input("Category (optional)", placeholder="Electronics, Tools, Home, etc.")
        quantity = st.number_input("Quantity", min_value=1, max_value=999, value=1, step=1)

    st.subheader("2) Features & notes")
    feat_text = st.text_area(
        "Key features (one per line)",
        placeholder="Example:\n16GB RAM\n512GB SSD\nIncludes charger\nTested & works",
        height=140
    )
    key_features = [f for f in feat_text.split("\n") if clean_spaces(f)]

    flaws = st.text_input("Known flaws / issues (optional)", placeholder="Small rip, screen crack, missing remote, etc.")
    whats_included = st.text_input("What's included (optional)", placeholder="Charger, box, manuals, accessories, etc.")
    measurements = st.text_input("Measurements (optional)", placeholder='13\" laptop, 10x8x6 in, etc.')
    notes = st.text_area("Extra notes (optional)", placeholder="Testing details, pickup info, smoke-free home, etc.", height=90)

with right:
    st.subheader("3) Money math")
    c1, c2 = st.columns(2)
    with c1:
        cogs = st.number_input("Your cost (COGS) $", min_value=0.0, value=10.0, step=0.50)
        target_price = st.number_input("Target sale price $", min_value=0.0, value=49.99, step=1.00)
        weight_lb = st.number_input("Estimated weight (lb)", min_value=0.0, value=2.0, step=0.25)
    with c2:
        ebay_pct = st.number_input("eBay fee % (est.)", min_value=0.0, max_value=30.0, value=float(DEFAULT_EBAY_FEE_PCT), step=0.25)
        proc_pct = st.number_input("Processing % (est.)", min_value=0.0, max_value=10.0, value=float(DEFAULT_PROCESSING_PCT), step=0.1)
        proc_fixed = st.number_input("Processing fixed ($)", min_value=0.0, max_value=2.0, value=float(DEFAULT_PROCESSING_FIXED), step=0.05)

    ship_method = st.selectbox("Shipping method", ["Ground (est.)", "USPS Priority (est.)", "Local pickup"],
                               index=["Ground (est.)", "USPS Priority (est.)", "Local pickup"].index(DEFAULT_SHIP_METHOD))
    packaging = st.number_input("Packaging cost ($)", min_value=0.0, max_value=20.0, value=float(DEFAULT_PACKAGING_COST), step=0.25)

    est_ship = shipping_estimate(weight_lb, ship_method, packaging)

    st.subheader("Quick pricing tiers")
    low = round(target_price * 0.85, 2)
    mid = round(target_price, 2)
    high = round(target_price * 1.15, 2)

    for label, price in [("Low (fast sale)", low), ("Target", mid), ("High (patient)", high)]:
        profit, margin, ebay_fee, pay_fee = profit_estimate(price, cogs, est_ship, ebay_pct, proc_pct, proc_fixed)
        st.write(f"**{label}: ${price:.2f}**")
        st.write(f"- Est. shipping+packaging: **${est_ship:.2f}** ({ship_method})")
        st.write(f"- Est. fees: eBay **${ebay_fee:.2f}** + processing **${pay_fee:.2f}**")
        st.write(f"- **Est. profit: ${profit:.2f}** (margin {margin:.1f}%)")
        st.divider()

# =============================
# Outputs
# =============================
st.subheader("4) Generate listings")

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

tab1, tab2 = st.tabs(["eBay Listing", "Facebook Listing"])

with tab1:
    st.markdown("### eBay")
    st.text_input("eBay Title (<=80 chars)", value=ebay_title)
    st.text_area("eBay Description", value=ebay_desc, height=260)
    st.text_area("Search Keywords (copy/paste)", value=", ".join(keywords), height=90)

with tab2:
    st.markdown("### Facebook Marketplace")
    st.text_input("FB Title", value=fb_title)
    st.text_area("FB Description", value=fb_desc, height=260)
    st.text_area("Keywords/Tags (copy/paste)", value=", ".join(keywords), height=90)

st.caption(f"© {datetime.now().year} • {APP_NAME}")
st.markdown("</div>", unsafe_allow_html=True)

