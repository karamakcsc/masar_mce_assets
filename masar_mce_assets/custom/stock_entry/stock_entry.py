import frappe
from frappe import _

from masar_mce_assets.it_asset_role_matrix import (
	ALLOWED_STOCK_ENTRY_TYPE,
	apply_it_naming_series,
	is_it_asset_role_matrix_applicable,
)


def before_insert(self, method):
	apply_it_naming_series(self)


def before_validate(self, method):
	# before_validate also runs for documents saved with ignore_validate.
	validate_it_asset_stock_entry_type(self)


def validate_it_asset_stock_entry_type(doc):
	if doc.stock_entry_type == ALLOWED_STOCK_ENTRY_TYPE or not is_it_asset_role_matrix_applicable():
		return

	frappe.throw(
		_("IT asset users can only use Stock Entry Type {0}, not {1}.").format(
			frappe.bold(ALLOWED_STOCK_ENTRY_TYPE), frappe.bold(doc.stock_entry_type or _("(empty)"))
		),
		frappe.PermissionError,
		title=_("Stock Entry Type Not Allowed"),
	)
