import math
import re
from datetime import datetime
from pathlib import Path

import streamlit as st

# =============================
# BRAND (LOCKED)
# =============================
APP_NAME = "Resale Listing Builder"
TAGLINE = "List faster. Price smarter. Profit confidently."
ACCENT = "#7c3aed"  # locked accent
LOGO_PATH = "logo.svg"  # put logo.svg in repo root (same folder as app.py)

# Defaults (locked; users can still override in the form if you allow)
DEFAULT_EBAY_FEE_PCT = 13.25
DEFAULT_PROC_PCT = 2.9
DEFAULT_PROC_FIXED = 0.30
DEFAULT_PACKAGING_COST = 1.50
DEFAULT_SHIP_METHOD = "Ground (est.)"

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

def generate_title(brand, item, model, key_features, condition, platform="ebay"):
    parts = []
    if brand: parts.append(brand)
    if item: parts.append(item)
    if model: parts.append(model)

    feats = [clean_spaces(f) for f in key_features if clean_spaces(f)]
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
    candidate = clean_spaces(" ".join([p for p in parts if p]))

    # add up to 2 features if room
    for f in feats[:2]:
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

def keyword_pack(brand, item, model, key_features):
    base = [clean_spaces(x) for x in [brand, item, model] if clean_spaces(x)]
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

def shipping_estimate(weight_lb: float, shipping_method: str, packaging_cost: float):
    w = max(0.0, float(weight_lb or 0.0))
    if shipping_method == "Local pickup":
        ship = 0.0
    elif shipping_method == "USPS Priority (est.)":
        ship = 8.50 + 1.25 * w
    else:  # Ground
        ship = 6.75 + 1.05 * w

    ship = math.ceil(ship * 4) / 4.0  # round to quarter dollars
    return max(0.0, ship + max(0.0, float(packaging_cost or 0.0)))

def fees_estimate(sale_price: float, ebay_pct: float, proc_pct: float, proc_fixed: float):
    p = max(0.0, float(sale_price or 0.0))
    ebay_fee = p * (max(0.0, ebay_pct) / 100.0)
    pay_fee = p * (max(0.0, proc_pct) / 100.0) + max(0.0, proc_fixed)
    return ebay_fee, pay_fee

def profit_estimate(sale_price, cogs, ship_cost, ebay_pct, proc_pct, proc_fixed):
    ebay_fee, pay_fee = fees_estimate(sale_price, ebay_pct, proc_pct, proc_fixed)
    profit = float(sale_price or 0) - float(cogs or 0) - float(ship_cost or 0) - ebay_fee - pay_fee
    margin = (profit / sale_price * 100.0) if sale_price and sale_price > 0 else 0.0
    return profit, margin, ebay_fee, pay_fee

def build_description(
    platform: str,
    brand, item, model, condition,
    key_features, flaws, included, measurements, notes,
    seller_name, seller_city, pickup_line, shipping_line, handling_time, returns_policy,
    add_for_parts_protection: bool
):
    bullets = []
    item_line = clean_spaces(" ".join([x for x in [brand, item, model] if clean_spaces(x)]))
    if item_line:
        bullets.append(f"Item: {item_line}")
    if condition:
        bullets.append(f"Condition: {condition}")

    feats = [clean_spaces(f) for f in key_features if clean_spaces(f)]
    if feats:
        bullets.append("Key Features: " + "; ".join(feats))

    if measurements:
        bullets.append(f"Measurements: {measurements}")
    if included:
        bullets.append(f"Included: {included}")
    if flaws:
        bullets.append(f"Known Issues/Flaws: {flaws}")
    if notes:
        bullets.append(f"Notes: {notes}")

    protection = []
    if add_for_parts_protection and condition and ("parts" in condition.lower() or "repair" in condition.lower()):
        protection.append("⚠️ Sold AS-IS for parts/repair. No guarantees. Not fully tested unless stated.")
        protection.append("⚠️ Buyer is responsible for compatibility/fit/function.")
        if platform == "ebay":
            protection.append("⚠️ Please read the full description and review all photos before purchase.")

    if platform == "fb":
        intro = "Available for pickup or shipping. Details below:"
        outro = "Message me if you want it (include your ZIP for shipping quote) or to arrange pickup."
    else:
        intro = "Please review the details below before purchasing:"
        outro = "Fast handling. Message with any questions before buying."

    seller_lines = []
    if seller_name:
        seller_lines.append(f"Seller: {seller_name}")
    if seller_city:
        seller_lines.append(f"Location: {seller_city}")
    if pickup_line:
        seller_lines.append(f"Pickup: {pickup_line}")
    if shipping_line:
        seller_lines.append(f"Shipping: {shipping_line}")
    if handling_time:
        seller_lines.append(f"Handling time: {handling_time}")
    if returns_policy:
        seller_lines.append(f"Returns: {returns_policy}")

    lines = [intro, ""]
    if protection:
        lines += protection + [""]

    for b in bullets:
        lines.append(f"• {b}")

    if seller_lines:
        lines += ["", "—", *seller_lines]

    lines += ["", outro]
    return "\n".join(lines)

# =============================
# Streamlit config + styling
# =============================
st.set_page_config(page_title=APP_NAME, page_icon="🧾", layout="wide")

st.markdown(
    f"""
    <style>
      :root {{ --accent: {ACCENT}; }}
      .app-header {{
        display:flex;
        align-items:center;
        gap:14px;
        padding: 10px 0 4px 0;
      }}
      .app-title {{
        font-size: 2.0rem;
        font-weight: 900;
        line-height: 1.1;
        margin: 0;
      }}
      .app-tag {{
        margin-top: 4px;
        opacity: .78;
        font-size: 1.05rem;
      }}
      .pill {{
        display:inline-block;
        padding: 6px 10px;
        border-radius: 999px;
        border: 1px solid rgba(255,255,255,.12);
        background: rgba(255,255,255,.03);
        font-size: .9rem;
        opacity: .9;
      }}
      a, a:visited {{ color: var(--accent) !important; }}
      /* Make the main container feel roomy */
      section.main > div {{ padding-top: 10px; }}
    </style>
    """,
    unsafe_allow_html=True
)

# =============================
# Header (BIG logo)
# =============================
logo_exists = Path(LOGO_PATH).exists()

hcol1, hcol2 = st.columns([0.20, 0.80], vertical_alignment="center")
with hcol1:
    if logo_exists:
        st.image(LOGO_PATH, width=140)  # BIG (fixes your issue)
    else:
        # fallback badge if logo missing
        st.markdown("<div class='pill'>🧾</div>", unsafe_allow_html=True)

with hcol2:
    st.markdown(f"<div class='app-title'>{APP_NAME}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='app-tag'>{TAGLINE}</div>", unsafe_allow_html=True)

st.divider()

# =============================
# Main App UI
# =============================
left, right = st.columns([1.15, 0.85], gap="large")

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
    flaws = st.text_input("Known flaws / issues (optional)", placeholder="Screen crack, ripped packaging, missing remote, etc.")
    included = st.text_input("What's included (optional)", placeholder="Charger, box, manuals, accessories, etc.")
    measurements = st.text_input("Measurements (optional)", placeholder='13\" laptop, 10x8x6 in, etc.')
    notes = st.text_area("Extra notes (optional)", placeholder="Testing details, smoke-free home, etc.", height=90)

    with st.expander("Optional: Seller info (adds a footer to descriptions)"):
        seller_name = st.text_input("Your name", placeholder="Deondre")
        seller_city = st.text_input("City/Area", placeholder="Jacksonville, FL")
        pickup_line = st.text_input("Pickup line", value="Porch pickup / meetup")
        shipping_line = st.text_input("Shipping line", value="Ships within the US")
        handling_time = st.text_input("Handling time", value="Same or next business day")
        returns_policy = st.text_input("Returns policy", value="No returns (ask questions before buying)")
        add_for_parts_protection = st.toggle("Auto add 'For parts/repair' protection text", value=True)

with right:
    st.subheader("3) Money math")

    c1, c2 = st.columns(2)
    with c1:
        cogs = st.number_input("Your cost (COGS) $", min_value=0.0, value=10.0, step=0.50)
        target_price = st.number_input("Target sale price $", min_value=0.0, value=49.99, step=1.00)
        weight_lb = st.number_input("Estimated weight (lb)", min_value=0.0, value=2.0, step=0.25)
    with c2:
        ebay_pct = st.number_input("eBay fee %", min_value=0.0, max_value=30.0, value=float(DEFAULT_EBAY_FEE_PCT), step=0.25)
        proc_pct = st.number_input("Processing %", min_value=0.0, max_value=10.0, value=float(DEFAULT_PROC_PCT), step=0.1)
        proc_fixed = st.number_input("Processing fixed ($)", min_value=0.0, max_value=2.0, value=float(DEFAULT_PROC_FIXED), step=0.05)

    ship_method = st.selectbox("Shipping method", ["Ground (est.)", "USPS Priority (est.)", "Local pickup"],
                               index=["Ground (est.)", "USPS Priority (est.)", "Local pickup"].index(DEFAULT_SHIP_METHOD))
    packaging_cost = st.number_input("Packaging cost ($)", min_value=0.0, max_value=20.0, value=float(DEFAULT_PACKAGING_COST), step=0.25)

    est_ship = shipping_estimate(weight_lb, ship_method, packaging_cost)

    st.markdown("#### Quick pricing tiers")
    tiers = [
        ("Low (fast sale)", round(target_price * 0.85, 2)),
        ("Target", round(target_price, 2)),
        ("High (patient)", round(target_price * 1.15, 2)),
    ]

    for label, price in tiers:
        profit, margin, ebay_fee, pay_fee = profit_estimate(price, cogs, est_ship, ebay_pct, proc_pct, proc_fixed)
        st.write(f"**{label}: ${price:.2f}**")
        st.write(f"- Est. shipping+packaging: **${est_ship:.2f}** ({ship_method})")
        st.write(f"- Est. fees: eBay **${ebay_fee:.2f}** + processing **${pay_fee:.2f}**")
        st.write(f"- **Est. profit: ${profit:.2f}** (margin {margin:.1f}%)")
        st.divider()

# Defaults for seller info if expander not opened
if "seller_name" not in locals():
    seller_name = ""
    seller_city = ""
    pickup_line = ""
    shipping_line = ""
    handling_time = ""
    returns_policy = ""
    add_for_parts_protection = True

# =============================
# Outputs
# =============================
st.subheader("4) Generate listings")

ebay_title = generate_title(brand, item, model, key_features, condition, platform="ebay")
fb_title = generate_title(brand, item, model, key_features, condition, platform="fb")

ebay_desc = build_description(
    platform="ebay",
    brand=brand, item=item, model=model, condition=condition,
    key_features=key_features, flaws=flaws, included=included, measurements=measurements, notes=notes,
    seller_name=seller_name, seller_city=seller_city,
    pickup_line=pickup_line, shipping_line=shipping_line,
    handling_time=handling_time, returns_policy=returns_policy,
    add_for_parts_protection=add_for_parts_protection
)

fb_desc = build_description(
    platform="fb",
    brand=brand, item=item, model=model, condition=condition,
    key_features=key_features, flaws=flaws, included=included, measurements=measurements, notes=notes,
    seller_name=seller_name, seller_city=seller_city,
    pickup_line=pickup_line, shipping_line=shipping_line,
    handling_time=handling_time, returns_policy=returns_policy,
    add_for_parts_protection=add_for_parts_protection
)

keywords = keyword_pack(brand, item, model, key_features)

tab1, tab2, tab3 = st.tabs(["eBay Listing", "Facebook Listing", "Copy Pack"])

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

with tab3:
    st.markdown("### Copy Pack (quick grab)")
    st.write("Use this box to copy everything fast.")
    pack = [
        f"EBAY TITLE: {ebay_title}",
        "",
        "EBAY DESCRIPTION:",
        ebay_desc,
        "",
        f"FB TITLE: {fb_title}",
        "",
        "FB DESCRIPTION:",
        fb_desc,
        "",
        "KEYWORDS:",
        ", ".join(keywords),
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    ]
    st.text_area("Copy Pack", value="\n".join(pack), height=360)

st.caption("Branding is locked. Next upgrades: bulk mode, CSV export, and optional paid Pro features.")
