"""Shared category definitions for Oracle readiness tracking.

We track modules across two Oracle readiness pillars -- SCM (scm.html)
and ERP (erp.html) -- and organize what we find into five report
categories: SCM, Finance, PPM, AI, and Redwood.

SCM/Finance/PPM are module-based: a feature belongs to that category
because of which Oracle module its "What's New" page came from. Finance
is additionally narrowed to five sub-areas (General Ledger, Accounts
Payable, Accounts Receivable, Fixed Assets, Cash Management) matched by
keyword against Oracle's own (and frequently changing) "Area" labels
inside the Financials feature tables -- Oracle does not use those five
names literally, so this is necessarily a heuristic, refined by watching
real output over time.

AI and Redwood are not modules at all -- they're tags Oracle puts on
individual features (e.g. "AI agent", "Agentic app", "Redwood Platform")
that can appear on a feature from any tracked module. "Idea Lab" tagged
items are early-stage ideas rather than shipped features and are
deliberately excluded from both.
"""

# --- Module-based categories -------------------------------------------------

SCM_MODULE_PREFIXES = (
    "Order Management What's New",
    "Procurement What's New",
    "Inventory Management What's New",
    "Product Lifecycle Management What's New",
    "Supply Planning What's New",
    "Demand Management What's New",
    "Sales and Operations Planning What's New",
)

FINANCE_MODULE_PREFIXES = (
    "Financials What's New",
    "Self Service Financials What's New",
)

PPM_MODULE_PREFIXES = ("Project Management What's New",)

TRACKED_MODULE_PREFIXES = SCM_MODULE_PREFIXES + FINANCE_MODULE_PREFIXES + PPM_MODULE_PREFIXES


def is_tracked(title: str) -> bool:
    return title.startswith(TRACKED_MODULE_PREFIXES)


def category_for_module(title: str) -> str | None:
    if title.startswith(SCM_MODULE_PREFIXES):
        return "SCM"
    if title.startswith(FINANCE_MODULE_PREFIXES):
        return "Finance"
    if title.startswith(PPM_MODULE_PREFIXES):
        return "PPM"
    return None


# --- Finance sub-area keywords (heuristic, see module docstring) ------------

FINANCE_SUBAREA_KEYWORDS = {
    "General Ledger": ("ledger", "journal", "chart of accounts"),
    "Accounts Payable": ("payable",),
    "Accounts Receivable": ("receivable", "billing", "bill management", "revenue management", "collections"),
    "Fixed Assets": ("asset",),
    "Cash Management": ("cash", "bank", "payment", "treasury", "virtual card"),
}


def finance_subarea_for(area_text: str) -> str | None:
    """Return the matching Finance sub-area name, or None if area_text
    doesn't match any of the five tracked sub-areas."""
    low = area_text.lower()
    for name, keywords in FINANCE_SUBAREA_KEYWORDS.items():
        if any(keyword in low for keyword in keywords):
            return name
    return None


# --- Tag-based categories (cross-cutting, see module docstring) ------------

AI_TAG_TEXTS = ("AI agent", "Agentic app")
REDWOOD_TAG_TEXTS = ("Redwood Platform",)


def has_ai_tag(tags_text: str) -> bool:
    low = tags_text.lower()
    return any(tag.lower() in low for tag in AI_TAG_TEXTS)


def has_redwood_tag(tags_text: str) -> bool:
    low = tags_text.lower()
    return any(tag.lower() in low for tag in REDWOOD_TAG_TEXTS)
