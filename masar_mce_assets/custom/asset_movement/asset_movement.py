from collections import defaultdict

import frappe

from masar_mce_assets.asset_location_limit import (
	get_asset_units,
	is_asset_counted,
	validate_incoming_asset_quantities,
)
from masar_mce_assets.custom.asset_movement.it_asset import apply_it_asset_movement_rules


def before_validate(self, method):
	# Before ERPNext's validate, which requires the target location the IT rules fill in.
	apply_it_asset_movement_rules(self)


def before_submit(self, method):
	"""Validate destination locations; the source location only decreases.

	Asset Movement always moves the whole Asset (partial quantities require
	splitting the Asset first), so each row brings `asset_quantity` units.
	"""
	incoming = defaultdict(int)
	for d in self.assets:
		if not (d.asset and d.target_location):
			continue
		asset = get_asset(d.asset)
		# Same-location rows (e.g. the Receipt made on Asset submit) add nothing.
		if not is_asset_counted(asset) or asset.location == d.target_location:
			continue
		incoming[(d.target_location, asset.asset_category)] += get_asset_units(asset.asset_quantity)

	validate_incoming_asset_quantities(incoming)


def before_cancel(self, method):
	self.flags.asset_locations_before_cancel = {
		d.asset: frappe.db.get_value("Asset", d.asset, "location") for d in self.assets if d.asset
	}


def on_cancel(self, method):
	"""Cancelling restores each Asset's previous location, which may add units there."""
	locations_before = self.flags.asset_locations_before_cancel or {}
	incoming = defaultdict(int)
	returned_assets = []
	for asset_name, location_before in locations_before.items():
		asset = get_asset(asset_name)
		if not is_asset_counted(asset) or not asset.location or asset.location == location_before:
			continue
		incoming[(asset.location, asset.asset_category)] += get_asset_units(asset.asset_quantity)
		returned_assets.append(asset_name)

	# The locations are already restored at this point, so exclude the returning assets from "current".
	validate_incoming_asset_quantities(incoming, exclude_assets=returned_assets)


def get_asset(asset_name):
	return frappe.db.get_value(
		"Asset",
		asset_name,
		["name", "location", "asset_category", "asset_quantity", "docstatus", "status"],
		as_dict=True,
	)
