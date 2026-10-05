# Copyright (c) 2026, KCSC and contributors
# For license information, please see license.txt

"""Asset Location Quantity Limit.

A Location may cap the number of asset units per Asset Category through its
`custom_asset_category_limits` table. Categories without a row are unlimited.

Quantities are always asset units (`Asset.asset_quantity`), never the number
of Asset documents. Every entry point that adds units to a location builds a
`{(location, asset_category): incoming_units}` map and calls
`validate_incoming_asset_quantities`, so the rule lives in one place.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint

LIMITS_FIELD = "custom_asset_category_limits"
LIMIT_DOCTYPE = "Location Asset Category Limit"

# Assets in these states no longer occupy their location.
INACTIVE_ASSET_STATUSES = ("Cancelled", "Sold", "Scrapped", "Capitalized")


class AssetLocationLimitExceededError(frappe.ValidationError):
	pass


def get_asset_units(asset_quantity):
	"""Units represented by one Asset document (an Asset is at least one unit)."""
	return max(cint(asset_quantity), 1)


def is_asset_counted(asset):
	"""Whether the asset occupies its location for limit purposes."""
	return cint(asset.get("docstatus")) < 2 and asset.get("status") not in INACTIVE_ASSET_STATUSES


def get_location_asset_category_limit(location, asset_category):
	"""Configured maximum, or None when the category is unlimited in the location."""
	limit = frappe.db.get_value(
		LIMIT_DOCTYPE,
		{
			"parenttype": "Location",
			"parentfield": LIMITS_FIELD,
			"parent": location,
			"asset_category": asset_category,
		},
		"maximum_quantity",
	)
	return None if limit is None else cint(limit)


def get_location_asset_quantity(location, asset_category, exclude_assets=None, for_update=False):
	"""Asset units of `asset_category` currently in `location`, derived from Asset records."""
	asset = frappe.qb.DocType("Asset")
	query = (
		frappe.qb.from_(asset)
		.select(asset.asset_quantity)
		.where(asset.location == location)
		.where(asset.asset_category == asset_category)
		.where(asset.docstatus < 2)
		.where(asset.status.notin(INACTIVE_ASSET_STATUSES))
	)
	if exclude_assets:
		query = query.where(asset.name.notin(list(exclude_assets)))
	if for_update:
		# A locking read sees rows committed after this transaction's snapshot (REPEATABLE READ).
		query = query.for_update()

	return sum(get_asset_units(qty) for (qty,) in query.run())


def validate_asset_location_limit(location, asset_category, incoming_quantity, exclude_assets=None):
	"""Throw if adding `incoming_quantity` units to the location would exceed its limit.

	`exclude_assets` removes assets from the current quantity, for callers that
	validate after the assets were already written to the location.
	"""
	incoming_quantity = cint(incoming_quantity)
	if not (location and asset_category) or incoming_quantity <= 0:
		return

	maximum_quantity = get_location_asset_category_limit(location, asset_category)
	if maximum_quantity is None:
		return

	# Serialize concurrent transactions adding to the same location until commit,
	# so two of them cannot both pass against the same current quantity.
	frappe.db.get_value("Location", location, "name", for_update=True)

	current_quantity = get_location_asset_quantity(
		location, asset_category, exclude_assets=exclude_assets, for_update=True
	)
	if current_quantity + incoming_quantity <= maximum_quantity:
		return

	frappe.throw(
		"<br>".join(
			[
				_("Asset Category {0} cannot be received or moved to Location {1}.").format(
					frappe.bold(asset_category), frappe.bold(location)
				),
				"",
				_("Maximum allowed quantity: {0}").format(maximum_quantity),
				_("Current quantity: {0}").format(current_quantity),
				_("Incoming quantity: {0}").format(incoming_quantity),
				_("Available quantity: {0}").format(max(maximum_quantity - current_quantity, 0)),
			]
		),
		AssetLocationLimitExceededError,
		title=_("Location Asset Limit Exceeded"),
	)


def validate_incoming_asset_quantities(incoming, exclude_assets=None):
	"""Validate a `{(location, asset_category): units}` map, each pair independently."""
	# Sorted so concurrent transactions acquire location locks in the same order.
	for location, asset_category in sorted(key for key in incoming if all(key)):
		validate_asset_location_limit(
			location, asset_category, incoming[(location, asset_category)], exclude_assets=exclude_assets
		)


def validate_location_limits_configuration(location_doc):
	"""Server-side validation of a Location's limit table."""
	seen = set()
	for row in location_doc.get(LIMITS_FIELD) or []:
		if cint(row.maximum_quantity) < 0:
			frappe.throw(
				_("Row #{0}: Maximum Quantity for Asset Category {1} cannot be negative.").format(
					row.idx, frappe.bold(row.asset_category)
				)
			)
		if row.asset_category in seen:
			frappe.throw(
				_("Row #{0}: Asset Category {1} is already configured for this Location.").format(
					row.idx, frappe.bold(row.asset_category)
				)
			)
		seen.add(row.asset_category)


def get_purchase_document_incoming_quantities(doc):
	"""Asset units a Purchase Receipt / Invoice will create on submit.

	Mirrors `BuyingController.auto_make_assets`: only auto-created assets are
	counted (manually created ones are validated on Asset save). A grouped asset
	item creates one Asset with `asset_quantity = qty`, otherwise `qty` Assets of
	one unit each, so both represent `cint(qty)` units in the row's location.
	"""
	from erpnext.controllers.buying_controller import get_asset_item_details

	incoming = defaultdict(int)
	if doc.get("is_return") or (doc.doctype == "Purchase Invoice" and not doc.get("update_stock")):
		return incoming

	rows = [d for d in doc.get("items") if d.is_fixed_asset and d.asset_location and cint(d.qty) > 0]
	if not rows:
		return incoming

	items = get_asset_item_details(list({d.item_code for d in rows}))
	for d in rows:
		item = items.get(d.item_code) or {}
		if not (item.get("auto_create_assets") and item.get("asset_naming_series")):
			continue
		# `make_asset` takes the category from the Item, not from the row.
		asset_category = frappe.get_cached_value("Item", d.item_code, "asset_category")
		incoming[(d.asset_location, asset_category)] += cint(d.qty)

	return incoming
