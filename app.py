import os
import base64
from pathlib import Path
from dataclasses import dataclass
import streamlit as st


# =============================
# Page + Basic Theme
# =============================
st.set_page_config(
    page_title="Resale Listing Builder",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Small CSS polish (logo size, spacing)
st.markdown(
    """
<style>
    .app-header {
        display:flex;
        align-items:center;
        gap:16px;
        padding: 8px 0 6px 0;
    }
    .app-logo img {
        border-radius: 12px;
        box-shadow: 0 6px 18px rgba(0,0,0,0.25);
    }
    .muted {
        opacity: 0.85;
        font-size: 0.95rem;
    }
    .tiny {
        opacity: 0.7;
        font-size: 0.85rem;
    }
    .section-card {
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 16px;
        padding: 14px 14px 6px 14px;
        margin-bottom: 14px;
        background: rgba(255,255,255,0.02);
    }
</style>
""",
    unsafe_allow_html=True,
)


# =============================
# Helpers
# =============================
def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def money(x: float) -> str:
    return f"${x:,.2f}"


def load_local_or_url_logo(logo_url: str | None) -> str | None:
    """
    Returns an HTML <img> src value:
      - If URL is provided -> return as-is
      - Else tries local files:
          assets/logo.png, assets/logo.jpg, assets/logo.jpeg, assets/logo.svg,
          logo.png, logo.jpg, logo.jpeg, logo.svg
    """
    if logo_url and logo_url.strip():
        return logo_url.strip()

    candidates = [
        Path("assets/logo.png"),
        Path("assets/logo.jpg"),
        Path("assets/logo.jpeg"),
        Path("assets/logo.svg"),
        Path("logo.png"),
        Path("logo.jpg"),
        Path("logo.jpeg"),
        Path("logo.svg"),
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            # Convert to data URI so it works everywhere (Streamlit Cloud, etc.)
            data = p.read_bytes()
            ext = p.suffix.lower().lstrip(".")
            if ext == "svg":
                mime = "image/svg+xml"
            elif ext in ("png", "jpg", "jpeg"):
                mime = f"image/{'jpeg' if ext in ('jpg','jpeg') else 'png'}"
            else:
                continue
            b64 = base64.b64encode(data).decode("utf-8")
            return f"data:{mime};base64,{b64}"

    return None


@dataclass
class FeeModel:
    ebay_fee_pct: float = 13.25
    processing_pct: float = 2.90
    processing_fixed: float = 0.30


def estimate_shipping(weight_lb: float, method: str) -> float:
    """
    Simple offline-friendly estimate.
    You can tune these later if you want.
    """
    w = max(0.0, weight_lb)

    # Rough buckets (USD)
    if method == "Local pickup":
        return 0.00
    if method == "USPS Ground Advantage (est.)":
        # decent for small/medium
        if w <= 1:
            return 6.50
        if w <= 3:
            return 8.75
        if w <= 5:
            return 10.75
        if w <= 10:
            return 14.25
        return 18.50
    if method == "UPS Ground (est.)":
        if w <= 1:
            return 8.50
        if w <= 5:
            return 12.50
        if w <= 10:
            return 16.50
        if w <= 20:
            return 24.00
        return 34.00
    if method == "FedEx Ground (est.)":
        if w <= 1:
            return 8.75
        if w <= 5:
            return 13.00
        if w <= 10:
            return 17.00
        if w <= 20:
            return 25.00
        return 36.00

    # fallback
    return 12.00


def calc_profit(
    sale_price: float,
    cogs: float,
    shipping_cost: float,
    packaging_cost: float,
    fee_model: FeeModel,
) -> dict:
    sale_price = max(0.0, sale_price)
    cogs = max(0.0, cogs)
    shipping_cost = max(0.0, shipping_cost)
    packaging_cost = max(0.0, packaging_cost)

    ebay_fee = sale_price * (fee_model.ebay_fee_pct / 100.0)
    processing_fee = sale_price * (fee_model.processing_pct / 100.0) + fee_model.processing_fixed

    total_fees = ebay_fee + processing_fee
    total_costs = cogs + shipping_cost + packaging_cost + total_fees
    net_profit = sale_price - total_costs

    roi = (net_profit / cogs * 100.0) if cogs > 0 else 0.0
    margin = (net_profit / sale_price * 100.0) if sale_price > 0 else 0.0

    return {
        "ebay_fee": ebay_fee,
        "processing_fee": processing_fee,
        "total_fees": total_fees,
        "total_costs": total_costs,
        "net_profit": net_profit,
        "roi_pct": roi,
        "margin_pct": margin,
    }


def flip_verdict(net_profit: float, roi_pct: float, min_profit: float, min_roi: float) -> tuple[str, str]:
    """
    Returns (label, reason)
    """
    if net_profit >= min_profit and roi_pct >= min_roi:
        return ("✅ YES", "Meets your minimum profit and ROI.")
    if net_profit >= (min_profit * 0.6) or roi_pct >= (min_roi * 0.6):
        return ("🟡 MAYBE", "Close. Consider negotiating, raising price, or lowering shipping/fees.")
    return ("❌ NO", "Too thin. Profit/ROI is below your thresholds.")


def build_listing_outputs(
    brand: str,
    item: str,
    model: str,
    condition: str,
    category: str,
    quantity: int,
    features_lines: list[str],
    flaws_lines: list[str],
    seller_name: str,
    city_area: str,
    pickup_line: str,
    shipping_line: str,
    handling_time: str,
    returns_line: str,
    auto_parts_repair_text: bool,
) -> dict:
    brand = (brand or "").strip()
    item = (item or "").strip()
    model = (model or "").strip()
    condition = (condition or "").strip()
    category = (category or "").strip()

    features_lines = [x.strip() for x in features_lines if x.strip()]
    flaws_lines = [x.strip() for x in flaws_lines if x.strip()]

    # Title
    pieces = []
    if brand:
        pieces.append(brand)
    if item:
        pieces.append(item)
    if model:
        pieces.append(model)
    if condition:
        pieces.append(condition)
    title = " ".join(pieces)
    title = title[:80]  # eBay title soft cap

    # Description blocks
    intro = []
    if brand or item or model:
        intro.append(f"**Item:** {brand} {item} {model}".strip())
    intro.append(f"**Condition:** {condition}")
    if category:
        intro.append(f"**Category:** {category}")
    if quantity and quantity > 1:
        intro.append(f"**Quantity:** {quantity}")

    feat_block = ""
    if features_lines:
        feat_block = "\n".join([f"- {f}" for f in features_lines])

    flaws_block = ""
    if flaws_lines:
        flaws_block = "\n".join([f"- {f}" for f in flaws_lines])

    seller_block = []
    if seller_name:
        seller_block.append(f"**Seller:** {seller_name}")
    if city_area:
        seller_block.append(f"**Location:** {city_area}")
    if pickup_line:
        seller_block.append(f"**Pickup:** {pickup_line}")
    if shipping_line:
        seller_block.append(f"**Shipping:** {shipping_line}")
    if handling_time:
        seller_block.append(f"**Handling time:** {handling_time}")
    if returns_line:
        seller_block.append(f"**Returns:** {returns_line}")

    parts_repair = ""
    if auto_parts_repair_text:
        parts_repair = (
            "\n\n**For parts/repair notice:**\n"
            "This item is sold **as-is** for parts/repair. Please review photos and description carefully "
            "and ask any questions before purchase."
        )

    ebay_desc = (
        "\n".join(intro)
        + "\n\n"
        + ("**Key features:**\n" + feat_block + "\n\n" if feat_block else "")
        + ("**Notes / flaws:**\n" + flaws_block + "\n\n" if flaws_block else "")
        + ("**Seller info:**\n" + "\n".join(seller_block) if seller_block else "")
        + parts_repair
    ).strip()

    fb_desc = (
        f"{title}\n\n"
        + ("Key features:\n" + "\n".join([f"• {f}" for f in features_lines]) + "\n\n" if features_lines else "")
        + ("Notes / flaws:\n" + "\n".join([f"• {f}" for f in flaws_lines]) + "\n\n" if flaws_lines else "")
        + ("\n".join([x.replace("**", "") for x in seller_block]) if seller_block else "")
        + (parts_repair.replace("**", "") if parts_repair else "")
    ).strip()

    keywords = []
    for x in [brand, item, model, category, condition]:
        if x:
            keywords.extend([w.strip() for w in x.replace("/", " ").split() if w.strip()])
    # de-dup preserving order
    seen = set()
    keywords_unique = []
    for k in keywords:
        lk = k.lower()
        if lk not in seen:
            seen.add(lk)
            keywords_unique.append(k)
    keyword_string = ", ".join(keywords_unique[:25])

    return {
        "title": title,
        "ebay_description": ebay_desc,
        "fb_description": fb_desc,
        "keywords": keyword_string,
    }


# =============================
# Session Defaults
# =============================
if "app_name" not in st.session_state:
    st.session_state.app_name = "Resale Listing Builder"
if "tagline" not in st.session_state:
    st.session_state.tagline = "List faster. Price smarter. Profit confidently."
if "accent_color" not in st.session_state:
    st.session_state.accent_color = "#7c3aed"
if "logo_url" not in st.session_state:
    st.session_state.logo_url = os.getenv("LOGO_URL", "").strip()
if "logo_size" not in st.session_state:
    st.session_state.logo_size = 56

if "seller_name" not in st.session_state:
    st.session_state.seller_name = "Deondre"
if "city_area" not in st.session_state:
    st.session_state.city_area = "Jacksonville, FL"
if "pickup_line" not in st.session_state:
    st.session_state.pickup_line = "Porch pickup / meetup"
if "shipping_line" not in st.session_state:
    st.session_state.shipping_line = "Ships within the US"
if "handling_time" not in st.session_state:
    st.session_state.handling_time = "Same or next business day"
if "returns_line" not in st.session_state:
    st.session_state.returns_line = "No returns (ask questions before buying)"
if "auto_parts_repair_text" not in st.session_state:
    st.session_state.auto_parts_repair_text = True

if "fee_model" not in st.session_state:
    st.session_state.fee_model = FeeModel()
if "shipping_method" not in st.session_state:
    st.session_state.shipping_method = "USPS Ground Advantage (est.)"

if "admin_unlocked" not in st.session_state:
    st.session_state.admin_unlocked = False


# =============================
# Sidebar: Admin Gate (Owner Mode)
# =============================
ADMIN_PIN = os.getenv("ADMIN_PIN", "").strip()

with st.sidebar:
    st.markdown("### 🔒 Owner Mode")
    if ADMIN_PIN:
        if not st.session_state.admin_unlocked:
            pin = st.text_input("Enter admin PIN", type="password")
            if st.button("Unlock"):
                if pin == ADMIN_PIN:
                    st.session_state.admin_unlocked = True
                    st.success("Owner Mode unlocked.")
                else:
                    st.error("Wrong PIN.")
        else:
            st.success("Owner Mode is ON")
            if st.button("Lock"):
                st.session_state.admin_unlocked = False
                st.info("Owner Mode locked.")
    else:
        st.caption("Tip: set `ADMIN_PIN` env var to hide Settings from customers.")
        st.session_state.admin_unlocked = True  # if no pin, allow (dev mode)


# =============================
# Sidebar: Settings (Owner Only)
# =============================
if st.session_state.admin_unlocked:
    with st.sidebar:
        st.markdown("---")
        st.markdown("## ⚙️ Settings")

        with st.expander("Branding", expanded=True):
            st.session_state.app_name = st.text_input("App name", st.session_state.app_name)
            st.session_state.tagline = st.text_input("Tagline", st.session_state.tagline)
            st.session_state.accent_color = st.color_picker("Accent color", st.session_state.accent_color)

            st.caption("Logo options: set LOGO_URL env var, paste a URL here, or add logo.svg/logo.png to repo.")
            st.session_state.logo_url = st.text_input("Logo URL (optional)", st.session_state.logo_url)
            st.session_state.logo_size = st.slider("Logo size", 36, 96, int(st.session_state.logo_size), 4)

        with st.expander("Personalization (auto-added to descriptions)", expanded=False):
            st.session_state.seller_name = st.text_input("Your name (optional)", st.session_state.seller_name)
            st.session_state.city_area = st.text_input("City/Area", st.session_state.city_area)
            st.session_state.pickup_line = st.text_input("Pickup line", st.session_state.pickup_line)
            st.session_state.shipping_line = st.text_input("Shipping line", st.session_state.shipping_line)
            st.session_state.handling_time = st.text_input("Handling time", st.session_state.handling_time)
            st.session_state.returns_line = st.text_input("Returns policy line", st.session_state.returns_line)
            st.session_state.auto_parts_repair_text = st.toggle(
                "Auto add 'For parts/repair' protection text",
                value=st.session_state.auto_parts_repair_text,
            )

        with st.expander("Default fee model", expanded=False):
            fm: FeeModel = st.session_state.fee_model
            fm.ebay_fee_pct = st.number_input("eBay fee % (est.)", min_value=0.0, max_value=30.0, value=float(fm.ebay_fee_pct), step=0.25)
            fm.processing_pct = st.number_input("Processing % (est.)", min_value=0.0, max_value=10.0, value=float(fm.processing_pct), step=0.05)
            fm.processing_fixed = st.number_input("Processing fixed ($)", min_value=0.0, max_value=5.0, value=float(fm.processing_fixed), step=0.05)
            st.session_state.fee_model = fm


# =============================
# Header (Logo + Title)
# =============================
logo_src = load_local_or_url_logo(st.session_state.logo_url)
logo_html = ""
if logo_src:
    logo_html = f"""
    <div class="app-logo">
      <img src="{logo_src}" width="{int(st.session_state.logo_size)}" height="{int(st.session_state.logo_size)}"/>
    </div>
    """

st.markdown(
    f"""
<div class="app-header">
  {logo_html}
  <div>
    <div style="font-size: 1.8rem; font-weight: 800;">{st.session_state.app_name}</div>
    <div class="muted">{st.session_state.tagline}</div>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown(f"<div class='tiny'>Offline-friendly v1 • Generates listings + estimates profit (fees + shipping).</div>", unsafe_allow_html=True)
st.markdown("---")


# =============================
# Tabs
# =============================
tab_builder, tab_flip, tab_soon, tab_help = st.tabs(
    ["🧾 Listing Builder", "✅ Flip Checker", "🚀 Coming Soon", "ℹ️ How it works"]
)

# =============================
# TAB 1 — Listing Builder + Profit Calculator
# =============================
with tab_builder:
    left, right = st.columns([1.15, 1.0], gap="large")

    with left:
        st.markdown("<div class='section-card'>", unsafe_allow_html=True)
        st.subheader("1) Item info")

        brand = st.text_input("Brand", placeholder="Apple, DeWalt, Nike, etc.")
        item = st.text_input("Item", placeholder="MacBook Pro, Drill, Sneakers, etc.")
        model = st.text_input("Model / Part # (optional)", placeholder="A1990, DCD791, etc.")
        condition = st.selectbox("Condition", ["New", "Open box", "Used - Like new", "Used - Good", "Used - Fair", "For parts/repair"])
        category = st.text_input("Category (optional)", placeholder="Electronics, Tools, Home, etc.")
        quantity = st.number_input("Quantity", min_value=1, max_value=100, value=1, step=1)

        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div class='section-card'>", unsafe_allow_html=True)
        st.subheader("2) Features & notes")

        features_text = st.text_area(
            "Key features (one per line)",
            placeholder="Example:\n16GB RAM\n512GB SSD\nIncludes charger",
            height=120,
        )
        flaws_text = st.text_area(
            "Notes / flaws (one per line)",
            placeholder="Example:\nSmall scratch on lid\nBattery service recommended",
            height=90,
        )

        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown("<div class='section-card'>", unsafe_allow_html=True)
        st.subheader("3) Money math")

        cogs = st.number_input("Your cost (COGS) $", min_value=0.0, value=10.00, step=1.00)
        target_sale = st.number_input("Target sale price $", min_value=0.0, value=49.99, step=1.00)
        weight = st.number_input("Estimated weight (lb)", min_value=0.0, value=2.0, step=0.25)

        shipping_method = st.selectbox(
            "Shipping method",
            ["USPS Ground Advantage (est.)", "UPS Ground (est.)", "FedEx Ground (est.)", "Local pickup"],
            index=["USPS Ground Advantage (est.)", "UPS Ground (est.)", "FedEx Ground (est.)", "Local pickup"].index(st.session_state.shipping_method)
            if st.session_state.shipping_method in ["USPS Ground Advantage (est.)", "UPS Ground (est.)", "FedEx Ground (est.)", "Local pickup"]
            else 0,
        )
        st.session_state.shipping_method = shipping_method

        packaging_cost = st.number_input("Packaging cost ($)", min_value=0.0, value=1.50, step=0.25)

        fm: FeeModel = st.session_state.fee_model
        ship_est = estimate_shipping(weight, shipping_method)

        results = calc_profit(
            sale_price=target_sale,
            cogs=cogs,
            shipping_cost=ship_est,
            packaging_cost=packaging_cost,
            fee_model=fm,
        )

        st.markdown("---")
        m1, m2, m3 = st.columns(3)
        m1.metric("Net profit", money(results["net_profit"]))
        m2.metric("Margin", f'{results["margin_pct"]:.1f}%')
        m3.metric("ROI (on COGS)", f'{results["roi_pct"]:.1f}%')

        with st.expander("See breakdown", expanded=False):
            st.write(f"Shipping estimate: **{money(ship_est)}** ({shipping_method})")
            st.write(f"eBay fee est.: **{money(results['ebay_fee'])}** ({fm.ebay_fee_pct:.2f}%)")
            st.write(f"Processing est.: **{money(results['processing_fee'])}** ({fm.processing_pct:.2f}% + {money(fm.processing_fixed)})")
            st.write(f"Packaging: **{money(packaging_cost)}**")
            st.write(f"Total costs (incl. fees): **{money(results['total_costs'])}**")

        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div class='section-card'>", unsafe_allow_html=True)
        st.subheader("Quick pricing tiers")

        # Simple tier suggestions based on adding profit on top of costs
        desired_profits = [10, 20, 35]
        tier_cols = st.columns(3)
        for i, p in enumerate(desired_profits):
            # solve approximate price ignoring price-dependent fees -> quick heuristic
            base = cogs + ship_est + packaging_cost + p
            # adjust for pct fees (approx)
            pct_total = (fm.ebay_fee_pct + fm.processing_pct) / 100.0
            approx_price = (base + fm.processing_fixed) / max(0.01, (1 - pct_total))
            approx_price = round(approx_price + 0.01, 2)
            tier_cols[i].metric(f"~{money(p)} profit", money(approx_price))

        st.caption("These are quick estimates. Use the main calculator for exact breakdown.")
        st.markdown("</div>", unsafe_allow_html=True)

    # Build outputs
    features_lines = features_text.splitlines() if features_text else []
    flaws_lines = flaws_text.splitlines() if flaws_text else []

    outputs = build_listing_outputs(
        brand=brand,
        item=item,
        model=model,
        condition=condition,
        category=category,
        quantity=int(quantity),
        features_lines=features_lines,
        flaws_lines=flaws_lines,
        seller_name=st.session_state.seller_name,
        city_area=st.session_state.city_area,
        pickup_line=st.session_state.pickup_line,
        shipping_line=st.session_state.shipping_line,
        handling_time=st.session_state.handling_time,
        returns_line=st.session_state.returns_line,
        auto_parts_repair_text=st.session_state.auto_parts_repair_text or (condition.lower().startswith("for parts")),
    )

    st.markdown("### 4) Outputs (copy/paste)")
    out_a, out_b = st.columns(2, gap="large")

    with out_a:
        st.markdown("**eBay Title**")
        st.code(outputs["title"], language=None)

        st.markdown("**eBay Description**")
        st.code(outputs["ebay_description"], language="markdown")

    with out_b:
        st.markdown("**Facebook Marketplace Description**")
        st.code(outputs["fb_description"], language=None)

        st.markdown("**Keywords**")
        st.code(outputs["keywords"], language=None)

    st.caption("Tip: Streamlit code blocks have a built-in copy button in the top-right.")


# =============================
# TAB 2 — Flip Checker
# =============================
with tab_flip:
    st.subheader("Flip Checker (YES / MAYBE / NO)")

    c1, c2 = st.columns([1.0, 1.0], gap="large")

    with c1:
        st.markdown("<div class='section-card'>", unsafe_allow_html=True)
        st.write("Enter your deal numbers and thresholds. This gives you a quick decision.")
        deal_cost = st.number_input("Your total cost (COGS) $", min_value=0.0, value=20.00, step=1.00, key="deal_cost")
        expected_sale = st.number_input("Expected sale price $", min_value=0.0, value=150.00, step=1.00, key="expected_sale")
        est_weight = st.number_input("Estimated weight (lb)", min_value=0.0, value=2.0, step=0.25, key="est_weight")
        ship_method = st.selectbox(
            "Shipping method",
            ["USPS Ground Advantage (est.)", "UPS Ground (est.)", "FedEx Ground (est.)", "Local pickup"],
            key="ship_method_flip",
        )
        pack_cost = st.number_input("Packaging cost ($)", min_value=0.0, value=1.50, step=0.25, key="pack_cost_flip")
        st.markdown("</div>", unsafe_allow_html=True)

    with c2:
        st.markdown("<div class='section-card'>", unsafe_allow_html=True)
        st.write("Your personal minimums (tune these over time).")
        min_profit = st.number_input("Minimum profit ($)", min_value=0.0, value=25.00, step=1.00)
        min_roi = st.number_input("Minimum ROI (%)", min_value=0.0, value=60.0, step=5.0)
        fm: FeeModel = st.session_state.fee_model
        ship = estimate_shipping(est_weight, ship_method)

        r = calc_profit(
            sale_price=expected_sale,
            cogs=deal_cost,
            shipping_cost=ship,
            packaging_cost=pack_cost,
            fee_model=fm,
        )
        label, reason = flip_verdict(r["net_profit"], r["roi_pct"], min_profit, min_roi)

        st.markdown("### Result")
        if "YES" in label:
            st.success(f"{label} — {reason}")
        elif "MAYBE" in label:
            st.warning(f"{label} — {reason}")
        else:
            st.error(f"{label} — {reason}")

        st.markdown("---")
        st.metric("Net profit", money(r["net_profit"]))
        st.metric("ROI", f"{r['roi_pct']:.1f}%")
        st.metric("Margin", f"{r['margin_pct']:.1f}%")

        with st.expander("Breakdown", expanded=False):
            st.write(f"Shipping estimate: **{money(ship)}** ({ship_method})")
            st.write(f"Total fees: **{money(r['total_fees'])}**")
            st.write(f"Total costs: **{money(r['total_costs'])}**")

        st.markdown("</div>", unsafe_allow_html=True)


# =============================
# TAB 3 — Coming Soon (Soft Freemium Hook)
# =============================
with tab_soon:
    st.subheader("🚀 Coming Soon")
    st.write(
        """
This tool will always have a **free version**.

For power users (serious flippers), we’re building features that save even more time:
"""
    )

    st.markdown(
        """
### Planned “Pro” features (not live yet)
- **Bulk Mode** — build listings for 5–20 items at once  
- **Saved Listings** — come back to your drafts anytime  
- **CSV Export** — track profit, ROI, and taxes  
- **Smarter Pricing Insights** — fast sale vs max profit suggestions  

### Early users get priority
If you keep using this tool, you’ll be first in line when Pro features drop.
"""
    )

    st.info("You’re on v1. Feedback helps decide what ships first.")


# =============================
# TAB 4 — Help
# =============================
with tab_help:
    st.subheader("How it works")
    st.markdown(
        """
**What this app does**
- Helps you draft clean, copy/paste listings for **eBay** and **Facebook Marketplace**
- Estimates profit after:
  - eBay fee %
  - processing fee %
  - processing fixed fee
  - shipping estimate (offline-friendly)
  - packaging cost

**Best workflow**
1) Enter item details + features  
2) Enter your cost + target sale price  
3) Read the profit + ROI  
4) Copy outputs into eBay / Facebook listing

**Owner tip (recommended for customers)**
Set an environment variable `ADMIN_PIN` to hide the Settings panel.
Without the PIN, customers won’t be able to change your branding/personalization.
"""
    )

    st.caption("v1 is intentionally simple. The goal is speed + accuracy.")


# =============================
# Footer
# =============================
st.markdown("---")
st.caption("Built for resellers who want profit clarity before they list.")
