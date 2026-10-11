import frappe

from masar_mce_assets.asset_location_limit import (
	get_asset_units,
	is_asset_counted,
	validate_asset_location_limit,
)
from masar_mce_assets.custom.asset_movement.it_asset import (
	mark_asset_receipt_movement,
	unmark_asset_receipt_movement,
)


def before_submit(self, method):
	# Asset.on_submit creates a Receipt Asset Movement; the IT movement rules do not apply to it.
	mark_asset_receipt_movement(self.name)


def on_submit(self, method):
	# Hooks run after the controller's on_submit, so the movement is already created.
	unmark_asset_receipt_movement(self.name)


def before_insert(self, method):
	# Inserts flagged ignore_validate (e.g. Asset Capitalization's composite asset) skip `validate`.
	if self.flags.ignore_validate:
		validate_location_limit(self)


def validate(self, method):
	validate_location_limit(self)


def validate_location_limit(doc):
	"""Covers Assets created or edited through the UI, REST API, Data Import or server code.

	Assets auto-created by Purchase Receipt (`db_insert`) and location changes by
	Asset Movement (`db.set_value`) bypass these hooks and are validated in those flows.
	"""
	if not doc.location or not is_asset_counted(doc):
		return

	asset_category = doc.asset_category or frappe.get_cached_value("Item", doc.item_code, "asset_category")
	quantity = get_asset_units(doc.asset_quantity)

	if doc.is_new() and doc.split_from:
		parent = frappe.db.get_value("Asset", doc.split_from, ["location", "asset_category"], as_dict=True)
		# split_asset moves units from the parent; the location total does not change.
		if parent and (parent.location, parent.asset_category) == (doc.location, asset_category):
			return

	previous = None if doc.is_new() else doc.get_doc_before_save()
	if (
		previous
		and is_asset_counted(previous)
		and (previous.location, previous.asset_category) == (doc.location, asset_category)
	):
		# Already counted in this location; only a quantity increase adds units.
		validate_asset_location_limit(
			doc.location, asset_category, quantity - get_asset_units(previous.asset_quantity)
		)
	else:
		validate_asset_location_limit(
			doc.location, asset_category, quantity, exclude_assets=None if doc.is_new() else [doc.name]
		)
