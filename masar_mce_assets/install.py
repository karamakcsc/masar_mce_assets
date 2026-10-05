import frappe


def after_migrate():
	add_asset_location_index()


def add_asset_location_index():
	# The location limit counts assets with a locking read on (location, asset_category);
	# the index keeps that lock to the rows of one location/category instead of the whole table.
	frappe.db.add_index("Asset", ["location", "asset_category"])
