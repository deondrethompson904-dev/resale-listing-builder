import json
import math
import re
from datetime import datetime
import streamlit as st

# -----------------------------
# Helpers
# -----------------------------
def clean_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def slugify(s: str) -> str:
    s = clean_spaces(s).lower()
    s = re.sub(r"[^a-z0-9\s\-]", "", s)
    s = re.sub(r"\s+", "-", s)
    return s[:80].strip("-") or "listing"

def clamp(n, lo, hi):
    return max(lo, min(hi, n))

def title_case_smart(text: str) -> str:
    # Keeps common short words lowercased unless first/last.
    if not text:
        return ""
    words = clean_spaces(text).split(" ")
    small = {"a","an","and","as","at","but","by","for","if","in","nor","of","on","or","per","so","the","to","up","via","with","yet"}
    out = []
    for i,w in enumerate(words):
        lw = w.lower()
        if i in (0, len(words)-1) or lw not in small:
            out.append(w[:1].upper() + w[1:])
        else:
            out.append(lw)
    return " ".join(out)

def generate_titles(brand, item, model, key_features, condition, platform="ebay"):
    parts = []
    if brand: parts.append(brand)
    if item: parts.append(item)
    if model: parts.append(model)

    # Feature words: keep short, no commas spam
    feat = []
    for f in key_features:
        f = clean_spaces(f)
        if f:
            feat.append(f)
    # condition snippet
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

    # Platform specific constraints
    if platform == "ebay":
        max_len = 80
    else:
        max_len = 100  # FB is flexible

    base = " ".join([p for p in parts if p])
    # append a couple features if room
    candidate = base
    if feat:
        # prioritize first 2 features
        for f in feat[:2]:
            trial = clean_spaces(f"{candidate} {f}")
            if len(trial) <= max_len:
                candidate = trial

    if cond_snip:
        trial = clean_spaces(f"{candidate} {cond_snip}")
        if len(trial) <= max_len:
            candidate = trial

    # If too long, trim features first then model
    if len(candidate) > max_len:
        candidate = base
        if cond_snip and len(clean_spaces(f"{candidate} {cond_snip}")) <= max_len:
            candidate = clean_spaces(f"{candidate} {cond_snip}")
    if len(candidate) > max_len:
        # hard trim
        candidate = candidate[:max_len].rstrip()

    return title_case_smart(candidate)

def generate_description(
    brand, item, model, key_features, condition, flaws, whats_included,
    measurements, notes, platform="ebay"
):
    bullets = []
    if brand or item or model:
        bullets.append(f"Item: {clean_spaces(' '.join([x for x in [brand, item, model] if x]))}")
    if condition:
        bullets.append(f"Condition: {condition}")
    if key_features:
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

    # Platform tone tweaks
    if platform == "fb":
        intro = "Available for pickup or shipping. Details below:"
        outro = "If you want it, message me with your ZIP for a shipping quote (or to arrange pickup)."
    else:
        intro = "Please review the details below before purchasing:"
        outro = "Fast handling. Please message with any questions before buying."

    # Build text
    lines = [intro, ""]
    for b in bullets:
        lines.append(f"• {b}")
    lines += ["", outro]
    return "\n".join(lines)

def keyword_pack(brand, item, model, key_features):
    base = []
    for x in [brand, item, model]:
        x = clean_spaces(x)
        if x:
            base.append(x)
    feats = [clean_spaces(f) for f in key_features if clean_spaces(f)]
    # Add de-duped keywords
    all_words = []
    for phrase in base + feats:
        # keep phrase and also split words
        all_words.append(phrase)
        all_words += phrase.split(" ")

    # normalize, dedupe, keep meaningful
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
    """
    Simple offline estimate (not a carrier quote):
    - Ground: base + per-lb
    - Priority: base + per-lb (higher)
    - Local: $0
    """
    w = max(0.0, float(weight_lb or 0.0))
    if shipping_method == "Local pickup":
        ship = 0.0
    elif shipping_method == "USPS Priority (est.)":
        ship = 8.50 + 1.25 * w
    else:  # Ground
        ship = 6.75 + 1.05 * w

    # round up to nearest $0.25 for realism
    ship = math.ceil(ship * 4) / 4.0
    return max(0.0, ship + max(0.0, packaging_cost or 0.0))

def fees_estimate(
    sale_price: float,
    ebay_final_value_pct: float,
    payment_processing_pct: float,
    payment_processing_fixed: float
):
    """
    Generic fee model:
    - eBay Final Value Fee: % of sale price
    - Payment processing: % of sale price + fixed
    """
    p = max(0.0, float(sale_price or 0.0))
    ebay_fee = p * (max(0.0, ebay_final_value_pct) / 100.0)
    pay_fee = p * (max(0.0, payment_processing_pct) / 100.0) + max(0.0, payment_processing_fixed)
    return ebay_fee, pay_fee

def profit_estimate(sale_price, cogs, ship_cost, ebay_pct, proc_pct, proc_fixed):
    ebay_fee, pay_fee = fees_estimate(sale_price, ebay_pct, proc_pct, proc_fixed)
    profit = float(sale_price or 0) - float(cogs or 0) - float(ship_cost or 0) - ebay_fee - pay_fee
    margin = (profit / sale_price * 100.0) if sale_price and sale_price > 0 else 0.0
    return profit, margin, ebay_fee, pay_fee

# -----------------------------
# UI
# -----------------------------
st.set_page_config(page_title="Resale Listing Builder + Profit Calculator", page_icon="🧾", layout="wide")

st.title("🧾 Resale Listing Builder + Profit Calculator")
st.caption("Offline-friendly v1 • Generates eBay + Facebook listings and estimates profit (fees + shipping).")

with st.sidebar:
    st.header("⚙️ Defaults")
    st.write("You can adjust these anytime per item.")
    default_ebay_pct = st.number_input("eBay final value fee % (est.)", min_value=0.0, max_value=30.0, value=13.25, step=0.25)
    default_proc_pct = st.number_input("Payment processing % (est.)", min_value=0.0, max_value=10.0, value=2.9, step=0.1)
    default_proc_fixed = st.number_input("Payment processing fixed fee ($)", min_value=0.0, max_value=2.0, value=0.30, step=0.05)
    st.divider()
    st.subheader("Shipping estimate model")
    default_ship_method = st.selectbox("Method", ["Ground (est.)", "USPS Priority (est.)", "Local pickup"], index=0)
    default_packaging = st.number_input("Packaging cost ($) (box/tape)", min_value=0.0, max_value=20.0, value=1.50, step=0.25)
    st.caption("Tip: this is a simple estimate, not a carrier quote.")

col1, col2 = st.columns([1.1, 0.9], gap="large")

with col1:
    st.subheader("1) Item info")
    cA, cB = st.columns(2)
    with cA:
        brand = st.text_input("Brand", placeholder="Apple, DeWalt, Nike, etc.")
        item = st.text_input("Item", placeholder="MacBook Pro, Drill, Sneakers, etc.")
        model = st.text_input("Model / Part # (optional)", placeholder="A1990, DCD791, etc.")
    with cB:
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

    flaws = st.text_input("Known flaws / issues (optional)", placeholder="Small rip on top, screen crack, missing remote, etc.")
    whats_included = st.text_input("What's included (optional)", placeholder="Charger, box, manuals, accessories, etc.")
    measurements = st.text_input("Measurements (optional)", placeholder='13" laptop, 10x8x6 in, etc.')
    notes = st.text_area("Extra notes (optional)", placeholder="Any testing details, pickup info, smoke-free home, etc.", height=100)

with col2:
    st.subheader("3) Money math")
    c1, c2 = st.columns(2)
    with c1:
        cost_of_goods = st.number_input("Your cost (COGS) $", min_value=0.0, value=10.0, step=0.50)
        target_sale_price = st.number_input("Target sale price $", min_value=0.0, value=49.99, step=1.00)
        weight_lb = st.number_input("Estimated weight (lb)", min_value=0.0, value=2.0, step=0.25)
    with c2:
        ebay_pct = st.number_input("eBay fee %", min_value=0.0, max_value=30.0, value=float(default_ebay_pct), step=0.25)
        proc_pct = st.number_input("Processing %", min_value=0.0, max_value=10.0, value=float(default_proc_pct), step=0.1)
        proc_fixed = st.number_input("Processing fixed ($)", min_value=0.0, max_value=2.0, value=float(default_proc_fixed), step=0.05)

    ship_method = st.selectbox("Shipping method", ["Ground (est.)", "USPS Priority (est.)", "Local pickup"],
                               index=["Ground (est.)", "USPS Priority (est.)", "Local pickup"].index(default_ship_method))
    packaging_cost = st.number_input("Packaging cost ($)", min_value=0.0, max_value=20.0, value=float(default_packaging), step=0.25)

    est_ship = shipping_estimate(weight_lb, ship_method, packaging_cost)

    # Pricing tiers around target
    st.subheader("Quick pricing tiers")
    low = round(target_sale_price * 0.85, 2)
    mid = round(target_sale_price, 2)
    high = round(target_sale_price * 1.15, 2)

    tiers = [("Low (fast sale)", low), ("Target", mid), ("High (patient)", high)]
    tier_rows = []
    for label, price in tiers:
        profit, margin, ebay_fee, pay_fee = profit_estimate(price, cost_of_goods, est_ship, ebay_pct, proc_pct, proc_fixed)
        tier_rows.append((label, price, profit, margin, ebay_fee, pay_fee))

    for label, price, profit, margin, ebay_fee, pay_fee in tier_rows:
        st.write(f"**{label}: ${price:.2f}**")
        st.write(f"- Est. shipping+packaging: **${est_ship:.2f}** ({ship_method})")
        st.write(f"- Est. fees: eBay **${ebay_fee:.2f}** + processing **${pay_fee:.2f}**")
        st.write(f"- **Est. profit: ${profit:.2f}** (margin {margin:.1f}%)")
        st.divider()

# -----------------------------
# Generate listing content
# -----------------------------
st.subheader("4) Generate listings")

ebay_title = generate_titles(brand, item, model, key_features, condition, platform="ebay")
fb_title = generate_titles(brand, item, model, key_features, condition, platform="fb")

ebay_desc = generate_description(
    brand, item, model, key_features, condition, flaws, whats_included, measurements, notes, platform="ebay"
)
fb_desc = generate_description(
    brand, item, model, key_features, condition, flaws, whats_included, measurements, notes, platform="fb"
)

keywords = keyword_pack(brand, item, model, key_features)

tab1, tab2, tab3 = st.tabs(["eBay Listing", "Facebook Listing", "Save / Export"])

with tab1:
    st.markdown("### eBay")
    st.text_input("eBay Title (<=80 chars)", value=ebay_title, key="ebay_title_out")
    st.text_area("eBay Description", value=ebay_desc, height=260, key="ebay_desc_out")
    st.text_area("Search Keywords (copy/paste)", value=", ".join(keywords), height=90, key="kw_out_ebay")

with tab2:
    st.markdown("### Facebook Marketplace")
    st.text_input("FB Title", value=fb_title, key="fb_title_out")
    st.text_area("FB Description", value=fb_desc, height=260, key="fb_desc_out")
    st.text_area("Keywords/Tags (copy/paste)", value=", ".join(keywords), height=90, key="kw_out_fb")

with tab3:
    st.markdown("### Save this listing bundle")
    bundle = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "item": {
            "brand": brand,
            "item": item,
            "model": model,
            "condition": condition,
            "category": category,
            "quantity": int(quantity),
            "features": key_features,
            "flaws": flaws,
            "included": whats_included,
            "measurements": measurements,
            "notes": notes,
        },
        "pricing": {
            "cogs": float(cost_of_goods),
            "target_sale_price": float(target_sale_price),
            "weight_lb": float(weight_lb),
            "shipping_method": ship_method,
            "packaging_cost": float(packaging_cost),
            "estimated_shipping_total": float(est_ship),
            "ebay_fee_pct": float(ebay_pct),
            "processing_pct": float(proc_pct),
            "processing_fixed": float(proc_fixed),
        },
        "outputs": {
            "ebay_title": ebay_title,
            "ebay_description": ebay_desc,
            "fb_title": fb_title,
            "fb_description": fb_desc,
            "keywords": keywords,
        }
    }

    filename = f"{slugify(brand + ' ' + item + ' ' + model)}.json"
    st.download_button(
        "⬇️ Download listing bundle (.json)",
        data=json.dumps(bundle, indent=2),
        file_name=filename,
        mime="application/json"
    )

    st.markdown("### Snapshot")
    st.code(json.dumps(bundle["pricing"], indent=2), language="json")

st.caption("Next upgrade: optional eBay sold-comp lookup (requires internet), bulk mode for multiple items, and CSV export for your tracker.")
