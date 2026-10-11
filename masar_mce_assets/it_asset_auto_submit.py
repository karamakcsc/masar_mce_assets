# Copyright (c) 2026, KCSC and contributors
# For license information, please see license.txt

"""Background submission of the Assets created by a Purchase Receipt.

Enqueued on Purchase Receipt submit when `custom_auto_submit_assets` is set.
Runs as the user who submitted the receipt, so normal Asset permissions apply.
Each Asset is configured, submitted and committed on its own: a failing Asset
is logged and skipped without blocking or undoing the others, and a rerun
only picks up Assets that are still drafts.
"""

import frappe
from frappe import _
from frappe.utils import get_link_to_form

BATCH_SIZE = 100
SAVEPOINT = "auto_submit_asset"


def submit_purchase_receipt_assets(purchase_receipt):
	receipt = frappe.db.get_value(
		"Purchase Receipt",
		purchase_receipt,
		["name", "docstatus", "is_return", "custom_auto_submit_assets"],
		as_dict=True,
	)
	if not receipt or receipt.docstatus != 1 or receipt.is_return or not receipt.custom_auto_submit_assets:
		return frappe._dict(submitted=[], failed={}, skipped=[])

	item_rows = set(
		frappe.get_all(
			"Purchase Receipt Item",
			filters={"parenttype": "Purchase Receipt", "parent": purchase_receipt},
			pluck="name",
		)
	)

	result = frappe._dict(submitted=[], failed={}, skipped=[])
	while assets := get_draft_assets(purchase_receipt, exclude=[*result.failed, *result.skipped]):
		for asset in assets:
			# Assets linked to the receipt by hand can point at no row of it.
			if asset.purchase_receipt_item not in item_rows:
				result.skipped.append(asset.name)
				continue
			frappe.db.savepoint(SAVEPOINT)
			try:
				if submit_asset(asset.name):
					result.submitted.append(asset.name)
				frappe.db.commit()
			except Exception as e:
				frappe.db.rollback(save_point=SAVEPOINT)
				result.failed[asset.name] = get_error_message(e)
				frappe.log_error(
					title=_("Auto Submit Assets failed for {0}").format(asset.name),
					reference_doctype="Asset",
					reference_name=asset.name,
				)
			finally:
				frappe.clear_messages()

	add_result_comment(purchase_receipt, result)
	frappe.db.commit()
	return result


def get_draft_assets(purchase_receipt, exclude):
	filters = {"purchase_receipt": purchase_receipt, "docstatus": 0}
	if exclude:
		filters["name"] = ("not in", exclude)
	return frappe.get_all(
		"Asset",
		filters=filters,
		fields=["name", "purchase_receipt_item"],
		order_by="name asc",
		limit=BATCH_SIZE,
	)


def submit_asset(asset_name):
	"""Configure depreciation from the Asset Category and submit. Returns False if already submitted."""
	# Row lock: a concurrent run waits here, then sees the Asset submitted and skips it.
	if frappe.db.get_value("Asset", asset_name, "docstatus", for_update=True) != 0:
		return False

	asset = frappe.get_doc("Asset", asset_name)
	finance_book = get_category_finance_book(asset)

	asset.available_for_use_date = asset.purchase_date
	asset.calculate_depreciation = 1

	# Update the category's book instead of appending, so a retry cannot add a second row.
	row = next((d for d in asset.finance_books if d.finance_book == finance_book.finance_book), None)
	if not row:
		row = asset.append("finance_books", {})
	row.update(
		{
			"finance_book": finance_book.finance_book,
			"depreciation_method": finance_book.depreciation_method,
			"total_number_of_depreciations": finance_book.total_number_of_depreciations,
			"frequency_of_depreciation": finance_book.frequency_of_depreciation,
			"depreciation_start_date": asset.purchase_date,
		}
	)

	asset.save()
	asset.submit()
	return True


def get_category_finance_book(asset):
	if not asset.asset_category:
		frappe.throw(_("Asset {0} has no Asset Category.").format(asset.name))
	if not frappe.db.exists("Asset Category", asset.asset_category):
		frappe.throw(
			_("Asset Category {0} of Asset {1} does not exist.").format(asset.asset_category, asset.name)
		)

	category = frappe.get_doc("Asset Category", asset.asset_category)
	if not category.finance_books:
		frappe.throw(
			_(
				"Asset Category {0} has no Finance Book, so the depreciation of Asset {1} cannot be set."
			).format(asset.asset_category, asset.name)
		)
	return category.finance_books[0]


def get_error_message(exception):
	return frappe.utils.strip_html(str(exception)) or exception.__class__.__name__


def add_result_comment(purchase_receipt, result):
	if not (result.submitted or result.failed or result.skipped):
		return

	lines = [_("Auto Submit Assets: {0} submitted.").format(len(result.submitted))]
	if result.failed:
		lines.append(_("{0} failed (see Error Log):").format(len(result.failed)))
		lines.extend(
			f"{get_link_to_form('Asset', name)}: {message}" for name, message in result.failed.items()
		)
	if result.skipped:
		lines.append(
			_("{0} skipped, not linked to an item row of this receipt: {1}").format(
				len(result.skipped), ", ".join(result.skipped)
			)
		)

	frappe.get_doc("Purchase Receipt", purchase_receipt).add_comment("Comment", "<br>".join(lines))
