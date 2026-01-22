import json
import math
import os
import re
from datetime import datetime
from pathlib import Path

import streamlit as st

# =============================
# Simple local persistence
# (Works locally; on Streamlit Cloud it usually persists during runtime,
# and may reset on rebuilds—still helpful for defaults.)
# =============================
APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / ".appdata"
DATA_DIR.mkdir(exist_ok=True)
SETTINGS_FILE = DATA_DIR / "settings.json"
UPLOADED_LOGO_FILE = DATA_DIR / "logo_upload.png"

def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_settings(settings: dict) -> None:
    try:
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except Exception:
        pass

def clean_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def slugify(s: str) -> str:
    s = clean_spaces(s).lower()
    s = re.sub(r"[^a-z0-9\s\-]", "", s)
    s = re.sub(r"\s+", "-", s)
    return s[:80].strip("-") or "listing"

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

def generate_titles(brand, item, model, key_features, condition, platform="ebay"):
    parts = []
    if brand: parts.append(brand)
    if item: parts.append(item)
    if model: parts.append(model)

    feat = []
    for f in key_features:
        f = clean_spaces(f)
        if f:
            feat.append(f)

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

    # add up to 2 features if room
    if feat:
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

def build_description(
    brand, item, model, key_features, condition, flaws, whats_included, measurements, notes,
    platform,
    seller_name, seller_city, seller_pickup, seller_shipping, handling_time, returns_policy,
    for_parts_autowarn: bool
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

    # Auto-protection language for "For Parts / Repair"
    protection = []
    if for_parts_autowarn and condition and ("parts" in condition.lower() or "repair" in condition.lower()):
        protection.append("⚠️ Sold AS-IS for parts/repair. No guarantees. Not fully tested unless stated.")
        protection.append("⚠️ Buyer is responsible for ensuring compatibility / fit / function.")
        if platform == "ebay":
            protection.append("⚠️ Please read the full description and view all photos before purchase.")

    # Platform tone
    if platform == "fb":
        intro = "Available for pickup or shipping. Details below:"
        outro = "Message me if you want it (include your ZIP for a shipping quote) or to arrange pickup."
    else:
        intro = "Please review the details below before purchasing:"
        outro = "Fast handling. Please message with any questions before buying."

    # Seller footer
    seller_lines = []
    if seller_name:
        seller_lines.append(f"Seller: {seller_name}")
    if seller_city:
        seller_lines.append(f"Location: {seller_city}")
    if seller_pickup:
        seller_lines.append(f"Pickup: {seller_pickup}")
    if seller_shipping:
        seller_lines.append(f"Shipping: {seller_shipping}")
    if handling_time:
        seller_lines.append(f"Handling time: {handling_time}")
    if returns_policy:
        seller_lines.append(f"Returns: {returns_policy}")

    lines = [intro, ""]
    for p in protection:
        lines.append(p)
    if protection:
        lines.append("")

    for b in bullets:
        lines.append(f"• {b}")

    if seller_lines:
        lines += ["", "—", *seller_lines]

    lines += ["", outro]
    return "\n".join(lines)

# =============================
# Streamlit setup
# =============================
stored = load_settings()

# Defaults (fallbacks)
DEFAULT_APP_NAME = stored.get("app_name", "Resale Listing Builder")
DEFAULT_TAGLINE = stored.get("tagline", "Generate eBay + Facebook listings and estimate profit (fees + shipping).")
DEFAULT_ACCENT = stored.get("accent", "#7c3aed")  # purple-ish
DEFAULT_USER = stored.get("user_name", "")

# fee defaults
DEFAULT_EBAY_PCT = float(stored.get("ebay_pct", 13.25))
DEFAULT_PROC_PCT = float(stored.get("proc_pct", 2.9))
DEFAULT_PROC_FIXED = float(stored.get("proc_fixed", 0.30))
DEFAULT_PACKAGING = float(stored.get("packaging_cost", 1.50))
DEFAULT_SHIP_METHOD = stored.get("ship_method", "Ground (est.)")

# seller profile defaults
DEFAULT_CITY = stored.get("seller_city", "")
DEFAULT_PICKUP = stored.get("seller_pickup", "Porch pickup / meetup")
DEFAULT_SHIPPING = stored.get("seller_shipping", "Ships within the US")
DEFAULT_HANDLING = stored.get("handling_time", "Same or next business day")
DEFAULT_RETURNS = stored.get("returns_policy", "No returns (ask questions before buying)")
DEFAULT_AUTOWARN = bool(stored.get("for_parts_autowarn", True))

# logo: env var wins, then stored url, then uploaded file
ENV_LOGO_URL = os.environ.get("LOGO_URL", "").strip()
STORED_LOGO_URL = stored.get("logo_url", "").strip()

st.set_page_config(
    page_title=f"{DEFAULT_APP_NAME} • Listings + Profit",
    page_icon="🧾",
    layout="wide"
)

# Accent styling
st.markdown(
    f"""
    <style>
      :root {{
        --accent: {DEFAULT_ACCENT};
      }}
      .tf-badge {{
        display:inline-flex;
        gap:10px;
        align-items:center;
        padding:10px 14px;
        border-radius:14px;
        border:1px solid rgba(255,255,255,.10);
        background: rgba(255,255,255,.03);
        margin-bottom: 10px;
      }}
      .tf-dot {{
        width:10px;height:10px;border-radius:999px;background: var(--accent);
        box-shadow: 0 0 16px var(--accent);
      }}
      .tf-title {{
        font-size: 1.6rem;
        font-weight: 800;
        line-height: 1.15;
        margin: 0;
      }}
      .tf-sub {{
        opacity:.75;
        margin-top: 2px;
      }}
      a, a:visited {{
        color: var(--accent) !important;
      }}
    </style>
    """,
    unsafe_allow_html=True
)

def pick_logo_url() -> str:
    if ENV_LOGO_URL:
        return ENV_LOGO_URL
    if STORED_LOGO_URL:
        return STORED_LOGO_URL
    if UPLOADED_LOGO_FILE.exists():
        return str(UPLOADED_LOGO_FILE)
    return ""

# =============================
# Sidebar: Branding + Defaults
# =============================
with st.sidebar:
    st.header("🛠️ Settings")

    st.subheader("Branding")
    app_name = st.text_input("App name", value=DEFAULT_APP_NAME)
    tagline = st.text_input("Tagline", value=DEFAULT_TAGLINE)
    accent = st.color_picker("Accent color", value=DEFAULT_ACCENT)

    # Logo controls
    st.caption("Logo options: set LOGO_URL env var, paste a URL here, or upload an image.")
    logo_url = st.text_input("Logo URL (optional)", value=STORED_LOGO_URL)
    uploaded_logo = st.file_uploader("Upload logo (png/jpg)", type=["png", "jpg", "jpeg"])
    if uploaded_logo is not None:
        try:
            UPLOADED_LOGO_FILE.write_bytes(uploaded_logo.getbuffer())
        except Exception:
            pass

    st.divider()

    st.subheader("Personalization")
    user_name = st.text_input("Your name (optional)", value=DEFAULT_USER, placeholder="Deondre")

    st.subheader("Seller profile (auto-added to descriptions)")
    seller_city = st.text_input("City/Area", value=DEFAULT_CITY, placeholder="Jacksonville, FL")
    seller_pickup = st.text_input("Pickup line", value=DEFAULT_PICKUP)
    seller_shipping = st.text_input("Shipping line", value=DEFAULT_SHIPPING)
    handling_time = st.text_input("Handling time", value=DEFAULT_HANDLING)
    returns_policy = st.text_input("Returns policy line", value=DEFAULT_RETURNS)
    for_parts_autowarn = st.toggle("Auto add 'For parts/repair' protection text", value=DEFAULT_AUTOWARN)

    st.divider()

    st.subheader("Fee + shipping defaults")
    ebay_pct_default = st.number_input("eBay final value fee % (est.)", min_value=0.0, max_value=30.0, value=float(DEFAULT_EBAY_PCT), step=0.25)
    proc_pct_default = st.number_input("Payment processing % (est.)", min_value=0.0, max_value=10.0, value=float(DEFAULT_PROC_PCT), step=0.1)
    proc_fixed_default = st.number_input("Payment processing fixed fee ($)", min_value=0.0, max_value=2.0, value=float(DEFAULT_PROC_FIXED), step=0.05)

    ship_method_default = st.selectbox("Default shipping method", ["Ground (est.)", "USPS Priority (est.)", "Local pickup"],
                                       index=["Ground (est.)", "USPS Priority (est.)", "Local pickup"].index(DEFAULT_SHIP_METHOD) if DEFAULT_SHIP_METHOD in ["Ground (est.)", "USPS Priority (est.)", "Local pickup"] else 0)
    packaging_default = st.number_input("Default packaging cost ($)", min_value=0.0, max_value=20.0, value=float(DEFAULT_PACKAGING), step=0.25)

    col_save, col_reset = st.columns(2)
    with col_save:
        if st.button("💾 Save settings", use_container_width=True):
            save_settings({
                "app_name": app_name,
                "tagline": tagline,
                "accent": accent,
                "logo_url": logo_url,
                "user_name": user_name,
                "seller_city": seller_city,
                "seller_pickup": seller_pickup,
                "seller_shipping": seller_shipping,
                "handling_time": handling_time,
                "returns_policy": returns_policy,
                "for_parts_autowarn": for_parts_autowarn,
                "ebay_pct": ebay_pct_default,
                "proc_pct": proc_pct_default,
                "proc_fixed": proc_fixed_default,
                "ship_method": ship_method_default,
                "packaging_cost": packaging_default,
            })
            st.success("Saved.")
    with col_reset:
        if st.button("↩️ Reset session", use_container_width=True):
            st.session_state.clear()
            st.rerun()

# Re-render accent after sidebar changes (so it updates immediately)
st.markdown(
    f"""
    <style>
      :root {{
        --accent: {accent};
      }}
    </style>
    """,
    unsafe_allow_html=True
)

# =============================
# Header (logo + title)
# =============================
logo_src = pick_logo_url()
header_cols = st.columns([0.12, 0.88], vertical_alignment="center")

with header_cols[0]:
    if logo_src:
        try:
            st.image(logo_src, width=120)
        except Exception:
            # fallback if URL fails
            st.markdown('<div class="tf-badge"><div class="tf-dot"></div></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="tf-badge"><div class="tf-dot"></div></div>', unsafe_allow_html=True)

with header_cols[1]:
    st.markdown(f"<div class='tf-title'>{app_name}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='tf-sub'>{tagline}</div>", unsafe_allow_html=True)

if user_name:
    st.caption(f"👋 Hey {user_name} — build listings fast, price with confidence.")

st.divider()

# =============================
# Main UI
# =============================
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

    flaws = st.text_input("Known flaws / issues (optional)", placeholder="Small rip, screen crack, missing remote, etc.")
    whats_included = st.text_input("What's included (optional)", placeholder="Charger, box, manuals, accessories, etc.")
    measurements = st.text_input("Measurements (optional)", placeholder='13\" laptop, 10x8x6 in, etc.')
    notes = st.text_area("Extra notes (optional)", placeholder="Testing details, pickup info, smoke-free home, etc.", height=100)

with col2:
    st.subheader("3) Money math")
    c1, c2 = st.columns(2)
    with c1:
        cost_of_goods = st.number_input("Your cost (COGS) $", min_value=0.0, value=10.0, step=0.50)
        target_sale_price = st.number_input("Target sale price $", min_value=0.0, value=49.99, step=1.00)
        weight_lb = st.number_input("Estimated weight (lb)", min_value=0.0, value=2.0, step=0.25)
    with c2:
        ebay_pct = st.number_input("eBay fee %", min_value=0.0, max_value=30.0, value=float(ebay_pct_default), step=0.25)
        proc_pct = st.number_input("Processing %", min_value=0.0, max_value=10.0, value=float(proc_pct_default), step=0.1)
        proc_fixed = st.number_input("Processing fixed ($)", min_value=0.0, max_value=2.0, value=float(proc_fixed_default), step=0.05)

    ship_method = st.selectbox("Shipping method", ["Ground (est.)", "USPS Priority (est.)", "Local pickup"],
                               index=["Ground (est.)", "USPS Priority (est.)", "Local pickup"].index(ship_method_default) if ship_method_default in ["Ground (est.)","USPS Priority (est.)","Local pickup"] else 0)
    packaging_cost = st.number_input("Packaging cost ($)", min_value=0.0, max_value=20.0, value=float(packaging_default), step=0.25)

    est_ship = shipping_estimate(weight_lb, ship_method, packaging_cost)

    st.subheader("Quick pricing tiers")
    low = round(target_sale_price * 0.85, 2)
    mid = round(target_sale_price, 2)
    high = round(target_sale_price * 1.15, 2)

    tiers = [("Low (fast sale)", low), ("Target", mid), ("High (patient)", high)]
    for label, price in tiers:
        profit, margin, ebay_fee, pay_fee = profit_estimate(price, cost_of_goods, est_ship, ebay_pct, proc_pct, proc_fixed)
        st.write(f"**{label}: ${price:.2f}**")
        st.write(f"- Est. shipping+packaging: **${est_ship:.2f}** ({ship_method})")
        st.write(f"- Est. fees: eBay **${ebay_fee:.2f}** + processing **${pay_fee:.2f}**")
        st.write(f"- **Est. profit: ${profit:.2f}** (margin {margin:.1f}%)")
        st.divider()

# =============================
# Outputs
# =============================
st.subheader("4) Generate listings")

ebay_title = generate_titles(brand, item, model, key_features, condition, platform="ebay")
fb_title = generate_titles(brand, item, model, key_features, condition, platform="fb")

ebay_desc = build_description(
    brand, item, model, key_features, condition, flaws, whats_included, measurements, notes,
    platform="ebay",
    seller_name=user_name,
    seller_city=seller_city,
    seller_pickup=seller_pickup,
    seller_shipping=seller_shipping,
    handling_time=handling_time,
    returns_policy=returns_policy,
    for_parts_autowarn=for_parts_autowarn,
)

fb_desc = build_description(
    brand, item, model, key_features, condition, flaws, whats_included, measurements, notes,
    platform="fb",
    seller_name=user_name,
    seller_city=seller_city,
    seller_pickup=seller_pickup,
    seller_shipping=seller_shipping,
    handling_time=handling_time,
    returns_policy=returns_policy,
    for_parts_autowarn=for_parts_autowarn,
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
        "brand_settings": {
            "app_name": app_name,
            "tagline": tagline,
            "accent": accent,
            "logo_url": logo_url,
        },
        "seller_profile": {
            "seller_name": user_name,
            "seller_city": seller_city,
            "seller_pickup": seller_pickup,
            "seller_shipping": seller_shipping,
            "handling_time": handling_time,
            "returns_policy": returns_policy,
            "for_parts_autowarn": for_parts_autowarn,
        },
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

st.caption("Next upgrades: bulk mode (paste 10 items), CSV export for your tracker, optional sold-comp lookup (internet).")
