"""Shared list of SCM modules this project tracks and reports on.

Oracle's readiness pages publish many more modules than we care about
(Maintenance, Manufacturing, Warehouse Management, Transportation
Management, Global Trade Management, Supply Chain Collaboration,
Common Technologies, etc.). We only want:

  Order Management, Procurement, Inventory Management,
  Product Lifecycle Management (PIM), and the planning family
  (Supply Planning, Demand Management, Sales and Operations Planning).

Matching is by exact title prefix (Oracle titles are formatted as
"<Module Name> What's New <release>") so "Procurement" doesn't
accidentally match "Self Service Procurement".
"""

TRACKED_MODULE_PREFIXES = (
    "Order Management What's New",
    "Procurement What's New",
    "Inventory Management What's New",
    "Product Lifecycle Management What's New",
    "Supply Planning What's New",
    "Demand Management What's New",
    "Sales and Operations Planning What's New",
)


def is_tracked(title: str) -> bool:
    return title.startswith(TRACKED_MODULE_PREFIXES)
