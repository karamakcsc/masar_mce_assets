# Copyright (c) 2026, KCSC and contributors
# For license information, please see license.txt

"""IT Asset Role Matrix.

Two role lists are configured in `IT Asset Role Matrix Settings`:

- IT Asset Roles (Function 1): users who must follow the IT asset workflow.
- Ignore Roles (Function 2): users exempt from it. Always wins over Function 1.

Every server-side rule calls `is_it_asset_role_matrix_applicable` so the
precedence lives in one place. The rules only add restrictions on top of the
standard ones; being exempt never skips ERPNext permissions or validation.
"""

import frappe
from frappe import _

SETTINGS_DOCTYPE = "IT Asset Role Matrix Settings"

PURCHASE_RECEIPT_NAMING_SERIES = "IT-PRE-.YYYY.-"
STOCK_ENTRY_NAMING_SERIES = "IT-STE-.YYYY.-"
IT_NAMING_SERIES = {
	"Purchase Receipt": PURCHASE_RECEIPT_NAMING_SERIES,
	"Stock Entry": STOCK_ENTRY_NAMING_SERIES,
}

ALLOWED_STOCK_ENTRY_TYPE = "سند اخراج"
ALLOWED_ASSET_MOVEMENT_PURPOSES = ("Transfer", "Issue")

NORMAL_CYCLE_FIELD = "custom_normal_cycle"
MOVEMENT_LOCATION_FIELD = "custom_default_target_location"
MOVEMENT_MANDATORY_FIELDS = (
	"custom_approval_letter_no",
	"custom_approval_letter_date",
	MOVEMENT_LOCATION_FIELD,
)


def get_it_asset_roles():
	return _get_roles("it_asset_roles")


def get_it_asset_ignore_roles():
	return _get_roles("ignore_roles")


def _get_roles(fieldname):
	settings = frappe.get_cached_doc(SETTINGS_DOCTYPE)
	return {row.role for row in settings.get(fieldname) if row.role}


def get_role_matrix_status(user=None):
	user_roles = set(frappe.get_roles(user or frappe.session.user))
	ignored = bool(user_roles & get_it_asset_ignore_roles())
	it_asset_user = bool(user_roles & get_it_asset_roles())
	return frappe._dict(
		# Function 1 applies: the IT asset restrictions are enforced.
		applicable=it_asset_user and not ignored,
		# Function 2 applies: exempt, but may still use the IT options.
		ignored=ignored,
		# In either function: may use the IT naming series and sees the IT fields.
		member=it_asset_user or ignored,
	)


def is_it_asset_role_matrix_applicable(user=None):
	return get_role_matrix_status(user).applicable


@frappe.whitelist()
def get_current_user_status():
	"""Role matrix status of the session user, for form behaviour only (never trusted by the server)."""
	status = get_role_matrix_status()
	status.update(
		purchase_receipt_naming_series=PURCHASE_RECEIPT_NAMING_SERIES,
		stock_entry_naming_series=STOCK_ENTRY_NAMING_SERIES,
		allowed_stock_entry_type=ALLOWED_STOCK_ENTRY_TYPE,
		allowed_asset_movement_purposes=ALLOWED_ASSET_MOVEMENT_PURPOSES,
	)
	return status


def apply_it_naming_series(doc):
	"""Run in `before_insert`, which Frappe calls before naming the document.

	Function 1 users always get the IT series, whatever the client sent (the
	field is read-only for them). Function 2 users may choose it. Other users
	cannot use it, so their options stay exactly as before.
	"""
	series = IT_NAMING_SERIES[doc.doctype]
	status = get_role_matrix_status()
	if status.applicable:
		doc.naming_series = series
	elif doc.get("naming_series") == series and not status.member:
		frappe.throw(
			_("Naming Series {0} is reserved for IT asset users.").format(frappe.bold(series)),
			frappe.PermissionError,
		)


def register_it_naming_series():
	"""Add the IT series to the naming series options (as Document Naming Settings does).

	Runs after every migrate, because masar_mce's fixtures re-import these
	Property Setters without the IT series.
	"""
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	for doctype, series in IT_NAMING_SERIES.items():
		options = frappe.get_meta(doctype).get_options("naming_series").split("\n")
		if series in options:
			continue
		make_property_setter(
			doctype,
			"naming_series",
			"options",
			"\n".join([*filter(None, options), series]),
			"Text",
			validate_fields_for_doctype=False,
		)
