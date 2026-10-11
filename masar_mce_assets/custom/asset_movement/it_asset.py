"""Asset Movement rules of the IT asset workflow.

For Function 1 users the purpose is limited to Transfer / Issue, the approval
letter fields and the location are mandatory, and the location field
(`custom_default_target_location`) is the only source of every row's
`target_location`.
"""

import frappe
from frappe import _

from masar_mce_assets.it_asset_role_matrix import (
	ALLOWED_ASSET_MOVEMENT_PURPOSES,
	MOVEMENT_LOCATION_FIELD,
	MOVEMENT_MANDATORY_FIELDS,
	is_it_asset_role_matrix_applicable,
)

# Assets being submitted in this request; set by the Asset hooks.
ASSET_RECEIPT_FLAG = "masar_mce_assets_receipt_movement_assets"


def mark_asset_receipt_movement(asset_name):
	frappe.flags.setdefault(ASSET_RECEIPT_FLAG, set()).add(asset_name)


def unmark_asset_receipt_movement(asset_name):
	frappe.flags.get(ASSET_RECEIPT_FLAG, set()).discard(asset_name)


def is_asset_receipt_movement(doc):
	"""The Receipt movement ERPNext creates inside `Asset.on_submit`, not entered by the user."""
	marked = frappe.flags.get(ASSET_RECEIPT_FLAG) or set()
	# ERPNext inserts it and then submits it, both inside the Asset's submit.
	return doc.purpose == "Receipt" and bool(doc.assets) and all(d.asset in marked for d in doc.assets)


def apply_it_asset_movement_rules(doc):
	if not is_it_asset_role_matrix_applicable() or is_asset_receipt_movement(doc):
		return

	if doc.purpose not in ALLOWED_ASSET_MOVEMENT_PURPOSES:
		frappe.throw(
			_("IT asset users can only use Asset Movement purpose {0}, not {1}.").format(
				" / ".join(frappe.bold(_(p)) for p in ALLOWED_ASSET_MOVEMENT_PURPOSES),
				frappe.bold(_(doc.purpose) if doc.purpose else _("(empty)")),
			),
			frappe.PermissionError,
			title=_("Asset Movement Purpose Not Allowed"),
		)

	if missing := [doc.meta.get_label(f) for f in MOVEMENT_MANDATORY_FIELDS if not doc.get(f)]:
		frappe.throw(
			_("Mandatory fields required for IT asset users: {0}").format(", ".join(_(m) for m in missing)),
			frappe.MandatoryError,
			title=_("Missing Fields"),
		)

	sync_target_location(doc)


def sync_target_location(doc):
	location = doc.get(MOVEMENT_LOCATION_FIELD)
	if not frappe.db.exists("Location", location):
		frappe.throw(
			_("Location {0} does not exist.").format(frappe.bold(location)), frappe.LinkValidationError
		)

	for d in doc.assets:
		d.target_location = location
