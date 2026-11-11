"""Run:  python test_ui_theme.py   (no network, no API key, no database)

Tests the pure HTML builders in ui_theme.py: badges, metric cards, headers and
escaping. It does not render Streamlit, so it needs only that streamlit imports.
"""
import ui_theme

PASSED = 0


def check(condition: bool, label: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"FAILED: {label}")
    PASSED += 1
    print(f"  ok  {label}")


# ---- status badges
for status in ("available", "requested", "transferred", "pending",
               "approved", "completed", "rejected", "cancelled"):
    badge = ui_theme.status_badge_html(status)
    label = ui_theme.STATUS_STYLES[status][0]
    check("rs-badge" in badge and label in badge, f"badge renders for '{status}'")

check("Weird" in ui_theme.status_badge_html("Weird"), "unknown status keeps its own label")
check("unknown" in ui_theme.status_badge_html(None), "None status shows 'unknown'")
check(ui_theme.status_badge_html("PENDING") == ui_theme.status_badge_html("pending"),
      "status lookup is case-insensitive")
check("<script>" not in ui_theme.status_badge_html("<script>alert(1)</script>"),
      "badge escapes unknown status text")

# ---- metric cards
card = ui_theme.metric_card_html("Total", 12, "all resources")
check("12" in card and "Total" in card and "all resources" in card, "metric card shows label, value, hint")
check("rs-metric-hint" not in ui_theme.metric_card_html("Total", 0),
      "metric card omits hint block when no hint")
check("0" in ui_theme.metric_card_html("Zero", 0), "metric card shows a zero value")
evil = ui_theme.metric_card_html("<b>x</b>", "<img src=x>", "<i>h</i>")
check("<b>" not in evil and "<img" not in evil and "<i>" not in evil,
      "metric card escapes label, value and hint")

# ---- page header
header = ui_theme.page_header_html("Dashboard", "Overview", "📊")
check("Dashboard" in header and "Overview" in header and "📊" in header, "header shows title, subtitle, icon")
check("<p>" not in ui_theme.page_header_html("Only title"), "header omits subtitle when empty")
check("<script>" not in ui_theme.page_header_html("<script>x</script>", "<script>y</script>"),
      "header escapes title and subtitle")

# ---- palette and CSS sanity
check(all(v.startswith("#") and len(v) == 7 for v in ui_theme.PALETTE.values()),
      "palette values are 6-digit hex colours")
check(ui_theme.PALETTE["primary"] in ui_theme._CSS, "CSS uses the primary green")
check("{PALETTE" not in ui_theme._CSS, "CSS has no unformatted placeholders")

print(f"\nALL UI THEME TESTS PASSED ({PASSED} checks)")
