import os
import re
import io
import json
import time
import base64
import pathlib
import datetime as dt
from typing import Dict, Any, Optional, Tuple

import streamlit as st


# =========================
# File storage (Streamlit Cloud-friendly)
# =========================
BASE_DIR = pathlib.Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"
ASSETS_DIR = BASE_DIR / "assets"
DATA_DIR.mkdir(exist_ok=True)
ASSETS_DIR.mkdir(exist_ok=True)

CONFIG_PATH = DATA_DIR / "config.json"
STATS_PATH = DATA_DIR / "stats.json"
WAITLIST_CSV = DATA_DIR / "waitlist.csv"
LOGO_OVERRIDE_PATH = DATA_DIR / "logo_override.png"

DEFAULT_CONFIG = {
    "app_name": "Resale Listing Builder",
    "tagline": "List faster. Price smarter. Profit confidently.",
    "accent_color": "#7C3AED",
    "logo_size": 64,
    "show_how_it_works_tab": True,
}

DEFAULT_STATS = {
    "created_at": None,
    "updated_at": None,
    "sessions": 0,
    "tiktok_sessions": 0,
    "profit_checks": 0,
    "listings_generated": 0,
    "emails_captured": 0,
}


# =========================
# Helpers
# =========================
def _read_json(path: pathlib.Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return dict(default)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(default)


def _write_json(path: pathlib.Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_config() -> Dict[str, Any]:
    cfg = _read_json(CONFIG_PATH, DEFAULT_CONFIG)
    # Ensure keys exist
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    return cfg


def save_config(cfg: Dict[str, Any]) -> None:
    cfg2 = dict(cfg)
    for k, v in DEFAULT_CONFIG.items():
        cfg2.setdefault(k, v)
    _write_json(CONFIG_PATH, cfg2)


def load_stats() -> Dict[str, Any]:
    stats = _read_json(STATS_PATH, DEFAULT_STATS)
    for k, v in DEFAULT_STATS.items():
        stats.setdefault(k, v)
    if stats["created_at"] is None:
        stats["created_at"] = dt.datetime.utcnow().isoformat()
    return stats


def save_stats(stats: Dict[str, Any]) -> None:
    stats["updated_at"] = dt.datetime.utcnow().isoformat()
    _write_json(STATS_PATH, stats)


def bump_stat(key: str, n: int = 1) -> None:
    stats = load_stats()
    stats[key] = int(stats.get(key, 0)) + n
    save_stats(stats)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def is_valid_email(email: str) -> bool:
    email = normalize_email(email)
    # Simple, practical validation
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def append_waitlist(email: str, source: str = "", note: str = "") -> Tuple[bool, str]:
    email = normalize_email(email)
    if not is_valid_email(email):
        return False, "That doesn’t look like a valid email."

    # Create file with headers if needed
    new_file = not WAITLIST_CSV.exists()
    if new_file:
        WAITLIST_CSV.write_text("timestamp_utc,email,source,note\n", encoding="utf-8")

    # Prevent duplicates
    existing = WAITLIST_CSV.read_text(encoding="utf-8", errors="ignore").splitlines()[1:]
    for line in existing:
        parts = line.split(",")
        if len(parts) >= 2 and normalize_email(parts[1]) == email:
            return False, "You’re already on the list ✅"

    ts = dt.datetime.utcnow().isoformat()
    safe_source = (source or "").replace(",", " ").strip()
    safe_note = (note or "").replace(",", " ").strip()
    with WAITLIST_CSV.open("a", encoding="utf-8") as f:
        f.write(f"{ts},{email},{safe_source},{safe_note}\n")

    bump_stat("emails_captured", 1)
    return True, "You’re on the waitlist ✅"


def get_query_source() -> str:
    # e.g. add ?src=tiktok to your bio link
    qp = st.query_params
    src = ""
    try:
        src = qp.get("src", "")
        if isinstance(src, list):
            src = src[0] if src else ""
    except Exception:
        pass
    return (src or "").strip().lower()


def read_file_bytes(path: pathlib.Path) -> Optional[bytes]:
    try:
        if path.exists():
            return path.read_bytes()
    except Exception:
        return None
    return None


def bytes_to_data_url(img_bytes: bytes, mime: str) -> str:
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def get_logo_data_url() -> Optional[str]:
    """
    Priority:
    1) LOGO_URL env var (remote or data URL)
    2) uploaded override in data/logo_override.png
    3) assets/logo.png
    4) assets/logo.svg
    """
    env_logo = os.getenv("LOGO_URL", "").strip()
    if env_logo:
        return env_logo

    override = read_file_bytes(LOGO_OVERRIDE_PATH)
    if override:
        return bytes_to_data_url(override, "image/png")

    png = read_file_bytes(ASSETS_DIR / "logo.png")
    if png:
        return bytes_to_data_url(png, "image/png")

    svg = read_file_bytes(ASSETS_DIR / "logo.svg")
    if svg:
        # SVG as data URL
        b64 = base64.b64encode(svg).decode("utf-8")
        return f"data:image/svg+xml;base64,{b64}"

    return None


def inject_css(accent: str) -> None:
    st.markdown(
        f"""
        <style>
          :root {{
            --accent: {accent};
          }}
          .app-header {{
            display:flex;
            align-items:center;
            gap:14px;
            margin-top:6px;
            margin-bottom:6px;
          }}
          .app-logo {{
            width:auto;
            display:flex;
            align-items:center;
          }}
          .app-title {{
            font-size: 1.6rem;
            font-weight: 800;
            line-height: 1.1;
          }}
          .app-tagline {{
            margin-top: 2px;
            opacity: 0.8;
            font-size: 0.95rem;
          }}
          .pill {{
            display:inline-block;
            border: 1px solid rgba(255,255,255,0.10);
            padding: 6px 10px;
            border-radius: 999px;
            font-size: 0.85rem;
            opacity: 0.9;
          }}
          .accent {{
            color: var(--accent);
          }}
          .card {{
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 14px;
            padding: 14px;
            background: rgba(255,255,255,0.02);
          }}
          .small {{
            font-size: 0.9rem;
            opacity: 0.85;
          }}
          .muted {{
            opacity: 0.75;
          }}
          .divider {{
            margin: 12px 0;
            border-bottom: 1px solid rgba(255,255,255,0.08);
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header(cfg: Dict[str, Any]) -> None:
    logo_url = get_logo_data_url()
    size = int(cfg.get("logo_size", 64))

    logo_html = ""
    if logo_url:
        logo_html = f"""
        <div class="app-logo">
          <img src="{logo_url}" style="width:{size}px;height:{size}px;border-radius:14px;" />
        </div>
        """

    st.markdown(
        f"""
        <div class="app-header">
          {logo_html}
          <div>
            <div class="app-title">{cfg.get("app_name","")}</div>
            <div class="app-tagline">{cfg.get("tagline","")}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)


def money(x: float) -> str:
    return f"${x:,.2f}"


# =========================
# Core logic
# =========================
def calc_profit(
    sale_price: float,
    cogs: float,
    ebay_fee_pct: float,
    processing_pct: float,
    processing_fixed: float,
    shipping_cost: float,
    packaging_cost: float,
) -> Dict[str, float]:
    ebay_fee = sale_price * (ebay_fee_pct / 100.0)
    processing_fee = sale_price * (processing_pct / 100.0) + processing_fixed
    total_fees = ebay_fee + processing_fee
    total_cost = cogs + shipping_cost + packaging_cost + total_fees
    profit = sale_price - total_cost
    margin = (profit / sale_price * 100.0) if sale_price > 0 else 0.0
    return {
        "ebay_fee": ebay_fee,
        "processing_fee": processing_fee,
        "total_fees": total_fees,
        "total_cost": total_cost,
        "profit": profit,
        "margin_pct": margin,
    }


def shipping_estimate(method: str, weight_lb: float) -> float:
    """
    Simple offline-friendly estimate model (you can refine later).
    """
    w = max(0.0, float(weight_lb))
    if method == "Ground (est.)":
        return 6.50 + 1.10 * w
    if method == "Priority (est.)":
        return 9.50 + 1.50 * w
    if method == "Local pickup":
        return 0.0
    return 7.50 + 1.20 * w


def build_listing_text(
    brand: str,
    item: str,
    model: str,
    condition: str,
    category: str,
    qty: int,
    features_lines: str,
    defects_lines: str,
    seller_city: str,
    pickup_line: str,
    shipping_line: str,
    handling_time: str,
    returns_line: str,
    include_parts_repair_note: bool,
) -> Dict[str, str]:
    features = [ln.strip() for ln in features_lines.splitlines() if ln.strip()]
    defects = [ln.strip() for ln in defects_lines.splitlines() if ln.strip()]

    title_parts = [brand.strip(), item.strip()]
    if model.strip():
        title_parts.append(model.strip())
    title = " ".join([p for p in title_parts if p]).strip()
    if not title:
        title = "Item for sale"

    bullets = ""
    if features:
        bullets = "\n".join([f"- {x}" for x in features])

    defects_bullets = ""
    if defects:
        defects_bullets = "\n".join([f"- {x}" for x in defects])

    parts_repair = ""
    if include_parts_repair_note:
        parts_repair = (
            "\n\n**For parts/repair note:** This item may have issues not listed. "
            "Please read the description and ask questions before purchase."
        )

    common_footer = f"""
**Condition:** {condition}
**Quantity:** {qty}
**Category:** {category or "—"}

**Location:** {seller_city or "—"}
**Pickup:** {pickup_line or "—"}
**Shipping:** {shipping_line or "—"}
**Handling time:** {handling_time or "—"}
**Returns:** {returns_line or "—"}
""".strip()

    ebay_desc = f"""
## {title}

{"### Key features\n" + bullets if bullets else ""}

{"### Notes / defects\n" + defects_bullets if defects_bullets else ""}

{common_footer}
{parts_repair}
""".strip()

    fb_desc = f"""
{title}

Condition: {condition}
Qty: {qty}
{("Category: " + category) if category else ""}

{("Features:\n" + "\n".join([f"• {x}" for x in features])) if features else ""}

{("Notes/defects:\n" + "\n".join([f"• {x}" for x in defects])) if defects else ""}

Pickup: {pickup_line or "—"}
Shipping: {shipping_line or "—"}
Location: {seller_city or "—"}
Returns: {returns_line or "—"}
""".strip()

    return {"title": title, "ebay_desc": ebay_desc, "fb_desc": fb_desc}


# =========================
# App
# =========================
st.set_page_config(
    page_title="Resale Listing Builder",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded",
)

cfg = load_config()
inject_css(cfg.get("accent_color", "#7C3AED"))

# Session + source stats
if "session_bumped" not in st.session_state:
    bump_stat("sessions", 1)
    src = get_query_source()
    if src == "tiktok":
        bump_stat("tiktok_sessions", 1)
    st.session_state["session_bumped"] = True

# Owner mode
ADMIN_PIN = os.getenv("ADMIN_PIN", "").strip()
is_owner = False
with st.sidebar:
    st.markdown("### 🔒 Owner Mode")
    st.caption("Tip: set `ADMIN_PIN` env var to hide admin tools from customers.")
    pin_input = st.text_input("Enter PIN", type="password", placeholder="Owner PIN")
    if ADMIN_PIN and pin_input and pin_input == ADMIN_PIN:
        is_owner = True
        st.success("Owner mode enabled")

    st.markdown("---")
    st.markdown("### ⚙️ Settings")

    if is_owner:
        st.markdown("#### Branding (Owner)")
        cfg["app_name"] = st.text_input("App name", value=cfg.get("app_name", DEFAULT_CONFIG["app_name"]))
        cfg["tagline"] = st.text_input("Tagline", value=cfg.get("tagline", DEFAULT_CONFIG["tagline"]))
        cfg["accent_color"] = st.color_picker("Accent color", value=cfg.get("accent_color", DEFAULT_CONFIG["accent_color"]))
        cfg["logo_size"] = st.slider("Logo size", min_value=40, max_value=120, value=int(cfg.get("logo_size", 64)), step=2)
        cfg["show_how_it_works_tab"] = st.toggle("Show “How it works” tab", value=bool(cfg.get("show_how_it_works_tab", True)))

        st.caption("Logo options: set `LOGO_URL` env var, or place `assets/logo.png` / `assets/logo.svg`.")
        uploaded = st.file_uploader("Upload logo (PNG)", type=["png"], help="Owner-only. Overrides other logo sources.")
        if uploaded is not None:
            try:
                LOGO_OVERRIDE_PATH.write_bytes(uploaded.read())
                st.success("Logo uploaded ✅ (saved to data/logo_override.png)")
            except Exception as e:
                st.error(f"Could not save logo: {e}")

        colA, colB = st.columns(2)
        with colA:
            if st.button("Save settings"):
                save_config(cfg)
                st.success("Saved ✅ Refreshing…")
                st.rerun()
        with colB:
            if st.button("Reset defaults"):
                save_config(DEFAULT_CONFIG)
                st.warning("Reset. Refreshing…")
                st.rerun()

        st.markdown("---")
        st.markdown("#### Owner Dashboard")
        stats = load_stats()
        st.write(f"**Sessions:** {stats.get('sessions', 0)}")
        st.write(f"**TikTok sessions:** {stats.get('tiktok_sessions', 0)}  *(use `?src=tiktok` in bio link)*")
        st.write(f"**Profit checks:** {stats.get('profit_checks', 0)}")
        st.write(f"**Listings generated:** {stats.get('listings_generated', 0)}")
        st.write(f"**Emails captured:** {stats.get('emails_captured', 0)}")

        # Download buttons
        st.download_button(
            "Download stats.json",
            data=json.dumps(stats, indent=2).encode("utf-8"),
            file_name="stats.json",
            mime="application/json",
            use_container_width=True,
        )
        if WAITLIST_CSV.exists():
            st.download_button(
                "Download waitlist.csv",
                data=WAITLIST_CSV.read_bytes(),
                file_name="waitlist.csv",
                mime="text/csv",
                use_container_width=True,
            )
        else:
            st.caption("No waitlist yet (waitlist.csv will appear after first signup).")

    else:
        # Customer sidebar: keep it simple and product-like (not customizable)
        st.caption("Free tool. No login. Built for fast flips.")
        st.markdown("**Tip:** Add `?src=tiktok` to your bio link to track TikTok traffic.")
        st.markdown("---")
        st.markdown("#### Get updates")
        st.caption("Want early access to Pro features? Join the waitlist.")
        email_side = st.text_input("Email", key="email_sidebar", placeholder="you@example.com")
        if st.button("Join waitlist", use_container_width=True):
            ok, msg = append_waitlist(email_side, source=get_query_source() or "app_sidebar", note="sidebar")
            (st.success(msg) if ok else st.warning(msg))

# Main header
render_header(cfg)
st.caption("Offline-friendly v1 • Generates listings + estimates profit (fees + shipping).")

# Tabs
tabs = ["🧾 Listing Builder", "✅ Flip Checker", "🚀 Coming Soon"]
if cfg.get("show_how_it_works_tab", True):
    tabs.append("ℹ️ How it works")

tab_objs = st.tabs(tabs)

# -------------------------
# Tab 1: Listing Builder
# -------------------------
with tab_objs[0]:
    left, right = st.columns([1.05, 0.95], gap="large")

    with left:
        st.markdown("### 1) Item info")
        col1, col2 = st.columns(2)
        with col1:
            brand = st.text_input("Brand", placeholder="Apple, DeWalt, Nike, etc.")
            item = st.text_input("Item", placeholder="MacBook Pro, Drill, Sneakers, etc.")
            model = st.text_input("Model / Part # (optional)", placeholder="A1990, DCD791, etc.")
        with col2:
            condition = st.selectbox("Condition", ["New", "Open box", "Used - Like New", "Used - Good", "Used - Fair", "For parts/repair"])
            category = st.text_input("Category (optional)", placeholder="Electronics, Tools, Home, etc.")
            qty = st.number_input("Quantity", min_value=1, max_value=100, value=1, step=1)

        st.markdown("### 2) Features & notes")
        features_lines = st.text_area(
            "Key features (one per line)",
            height=140,
            placeholder="Example:\n16GB RAM\n512GB SSD\nIncludes charger",
        )
        defects_lines = st.text_area(
            "Notes / defects (one per line)",
            height=120,
            placeholder="Example:\nSmall scratch on lid\nBattery service recommended\nNo original box",
        )

        st.markdown("### 3) Seller profile (auto-added)")
        colA, colB = st.columns(2)
        with colA:
            seller_city = st.text_input("City/Area", value="Jacksonville, FL")
            pickup_line = st.text_input("Pickup line", value="Porch pickup / meetup")
            shipping_line = st.text_input("Shipping line", value="Ships within the US")
        with colB:
            handling_time = st.text_input("Handling time", value="Same or next business day")
            returns_line = st.text_input("Returns policy line", value="No returns (ask questions before buying)")
            include_parts_repair_note = st.toggle("Auto-add “For parts/repair” protection text", value=True)

        st.markdown("---")
        generate = st.button("Generate listing text", type="primary", use_container_width=True)

    with right:
        st.markdown("### Output")
        st.caption("Copy/paste into eBay or Facebook Marketplace.")

        if generate:
            bump_stat("listings_generated", 1)
            payload = build_listing_text(
                brand=brand,
                item=item,
                model=model,
                condition=condition,
                category=category,
                qty=int(qty),
                features_lines=features_lines,
                defects_lines=defects_lines,
                seller_city=seller_city,
                pickup_line=pickup_line,
                shipping_line=shipping_line,
                handling_time=handling_time,
                returns_line=returns_line,
                include_parts_repair_note=include_parts_repair_note,
            )
            st.session_state["last_listing"] = payload

        payload = st.session_state.get("last_listing")
        if not payload:
            st.info("Fill out the item and click **Generate listing text**.")
        else:
            st.markdown("#### Title")
            st.code(payload["title"], language=None)

            st.markdown("#### eBay description")
            st.code(payload["ebay_desc"], language="markdown")
            st.download_button(
                "Download eBay description (.txt)",
                data=payload["ebay_desc"].encode("utf-8"),
                file_name="ebay_description.txt",
                mime="text/plain",
                use_container_width=True,
            )

            st.markdown("#### Facebook Marketplace description")
            st.code(payload["fb_desc"], language=None)
            st.download_button(
                "Download FB description (.txt)",
                data=payload["fb_desc"].encode("utf-8"),
                file_name="facebook_description.txt",
                mime="text/plain",
                use_container_width=True,
            )

    st.markdown("---")
    st.markdown("### Get updates (optional)")
    st.caption("Want Bulk Mode / Pro tools? Join the waitlist. No spam.")
    colw1, colw2 = st.columns([0.6, 0.4])
    with colw1:
        email_main = st.text_input("Email address", key="email_main", placeholder="you@example.com")
    with colw2:
        if st.button("Join waitlist", key="join_waitlist_main", use_container_width=True):
            ok, msg = append_waitlist(email_main, source=get_query_source() or "app_main", note="main_footer")
            (st.success(msg) if ok else st.warning(msg))


# -------------------------
# Tab 2: Flip Checker
# -------------------------
with tab_objs[1]:
    st.markdown("### Flip Checker (profit after fees + shipping)")

    c1, c2, c3 = st.columns(3)
    with c1:
        sale_price = st.number_input("Target sale price ($)", min_value=0.0, value=49.99, step=1.0)
        cogs = st.number_input("Your cost (COGS) ($)", min_value=0.0, value=10.00, step=1.0)
        weight = st.number_input("Estimated weight (lb)", min_value=0.0, value=2.0, step=0.25)
    with c2:
        shipping_method = st.selectbox("Shipping method", ["Ground (est.)", "Priority (est.)", "Local pickup"])
        packaging_cost = st.number_input("Packaging cost ($)", min_value=0.0, value=1.50, step=0.25)
        manual_shipping = st.toggle("Manually enter shipping cost", value=False)
        if manual_shipping:
            shipping_cost = st.number_input("Shipping cost ($)", min_value=0.0, value=8.00, step=0.5)
        else:
            shipping_cost = shipping_estimate(shipping_method, weight)
            st.caption(f"Estimated shipping: **{money(shipping_cost)}**")
    with c3:
        st.markdown("#### Fee defaults")
        ebay_fee_pct = st.number_input("eBay fee %", min_value=0.0, max_value=30.0, value=13.25, step=0.25)
        processing_pct = st.number_input("Processing %", min_value=0.0, max_value=10.0, value=2.90, step=0.10)
        processing_fixed = st.number_input("Processing fixed ($)", min_value=0.0, max_value=2.0, value=0.30, step=0.05)

    st.markdown("---")
    if st.button("Calculate profit", type="primary"):
        bump_stat("profit_checks", 1)
        result = calc_profit(
            sale_price=sale_price,
            cogs=cogs,
            ebay_fee_pct=ebay_fee_pct,
            processing_pct=processing_pct,
            processing_fixed=processing_fixed,
            shipping_cost=shipping_cost,
            packaging_cost=packaging_cost,
        )
        st.session_state["last_profit"] = result

    result = st.session_state.get("last_profit")
    if not result:
        st.info("Click **Calculate profit** to log a check and get final numbers.")
    else:
        profit = result["profit"]
        margin = result["margin_pct"]

        top = st.columns(3)
        top[0].metric("Profit", money(profit))
        top[1].metric("Margin", f"{margin:.1f}%")
        top[2].metric("Total fees", money(result["total_fees"]))

        st.markdown("#### Breakdown")
        b1, b2 = st.columns(2)
        with b1:
            st.write(f"- eBay fee: **{money(result['ebay_fee'])}**")
            st.write(f"- Processing: **{money(result['processing_fee'])}**")
            st.write(f"- Shipping: **{money(shipping_cost)}**")
            st.write(f"- Packaging: **{money(packaging_cost)}**")
        with b2:
            st.write(f"- COGS: **{money(cogs)}**")
            st.write(f"- Total cost (all-in): **{money(result['total_cost'])}**")
            st.write(f"- Sale price: **{money(sale_price)}**")

        st.markdown("---")
        st.markdown("### Quick decision rule")
        st.write("✅ **Buy** if profit and margin look strong for the time + risk.")
        st.write("❌ **Pass** if fees + shipping crush the margin.")


# -------------------------
# Tab 3: Coming Soon + Waitlist (real)
# -------------------------
with tab_objs[2]:
    st.markdown("## 🚀 Coming Soon")
    st.caption("This tool will always have a free version. Pro is for serious flippers.")

    st.markdown("### Planned “Pro” features (not live yet)")
    st.markdown(
        """
- **Bulk Mode** — build listings for 5–20 items at once  
- **Profit presets** — save platform fee profiles (eBay / FB / local)  
- **Flip Score** — quick pass/buy rating based on margin + ROI  
- **Inventory tracker** — cost, price, sold date, net profit  
- **Export pack** — CSV exports for listings + bookkeeping  
        """.strip()
    )

    st.markdown("---")
    st.markdown("### Join the waitlist")
    st.caption("Get early access + updates. No spam.")
    colx, coly = st.columns([0.7, 0.3])
    with colx:
        email_cs = st.text_input("Email", key="email_comingsoon", placeholder="you@example.com")
        note_cs = st.text_input("What feature do you want most? (optional)", key="note_comingsoon", placeholder="Bulk mode, inventory, exports…")
    with coly:
        if st.button("Join waitlist", key="join_waitlist_cs", use_container_width=True):
            ok, msg = append_waitlist(email_cs, source=get_query_source() or "coming_soon", note=note_cs)
            (st.success(msg) if ok else st.warning(msg))

    st.markdown("---")
    st.markdown("### Share link")
    app_url_hint = "Tip: add **?src=tiktok** to your bio link so TikTok traffic gets counted."
    st.info(app_url_hint)


# -------------------------
# Tab 4: How it works
# -------------------------
if cfg.get("show_how_it_works_tab", True):
    with tab_objs[3]:
        st.markdown("## ℹ️ How it works")
        st.markdown(
            """
### What this app does
- Helps you draft clean, copy/paste listings for **eBay** and **Facebook Marketplace**
- Estimates profit after:
  - eBay fee %
  - processing %
  - processing fixed fee
  - shipping + packaging

### Best way to use it (fast)
1) Enter the item’s **target sale price** + your **cost**
2) Estimate weight + shipping method  
3) If profit doesn’t make sense → **don’t buy it**

### Privacy
- No login required
- Waitlist is **optional**
- Stats are **anonymous counters** (no personal data)
            """.strip()
        )
