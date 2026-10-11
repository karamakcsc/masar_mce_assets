import frappe

from masar_mce_assets.it_asset_role_matrix import SETTINGS_DOCTYPE, register_it_naming_series

DEFAULT_IT_ASSET_ROLES = ("IT Warehouse",)
DEFAULT_IGNORE_ROLES = ("System Manager",)


def after_install():
	set_default_it_asset_role_matrix()


def after_migrate():
	add_asset_location_index()
	register_it_naming_series()


def add_asset_location_index():
	# The location limit counts assets with a locking read on (location, asset_category);
	# the index keeps that lock to the rows of one location/category instead of the whole table.
	frappe.db.add_index("Asset", ["location", "asset_category"])


def set_default_it_asset_role_matrix():
	"""Seed the role lists once; a configured matrix is never changed."""
	settings = frappe.get_single(SETTINGS_DOCTYPE)
	if settings.it_asset_roles or settings.ignore_roles:
		return

	for fieldname, roles in (
		("it_asset_roles", DEFAULT_IT_ASSET_ROLES),
		("ignore_roles", DEFAULT_IGNORE_ROLES),
	):
		for role in roles:
			if frappe.db.exists("Role", role):
				settings.append(fieldname, {"role": role})
	settings.save(ignore_permissions=True)
