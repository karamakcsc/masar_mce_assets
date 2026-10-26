# Copyright (c) 2026, KCSC and contributors
# For license information, please see license.txt

"""Purchase Receipt rules of the IT asset workflow.

IT receipts are the ones named with the IT naming series: Function 1 users
always create them, Function 2 users may choose to. Their fixed asset items
that ERPNext turns into one Asset per unit need one serial number per unit in
`custom_serial_numbers_it`; on submit each created Asset gets its serial
number in `custom_serial_no`.
"""

import re

import frappe
from frappe import _
from frappe.utils import cint, flt

from masar_mce_assets.it_asset_role_matrix import (
	NORMAL_CYCLE_FIELD,
	PURCHASE_RECEIPT_NAMING_SERIES,
	apply_it_naming_series,
	is_it_asset_role_matrix_applicable,
)

SERIAL_NUMBERS_FIELD = "custom_serial_numbers_it"
ASSET_SERIAL_NO_FIELD = "custom_serial_no"
AUTO_SUBMIT_ASSETS_FIELD = "custom_auto_submit_assets"


def before_insert(doc):
	apply_it_naming_series(doc)
	check_warehouses(doc)
	# A default, not a rule: only applied when the creator did not send a value.
	if doc.get(NORMAL_CYCLE_FIELD) is None and is_it_asset_role_matrix_applicable():
		doc.set(NORMAL_CYCLE_FIELD, 1)


def is_it_purchase_receipt(doc):
	return doc.get("naming_series") == PURCHASE_RECEIPT_NAMING_SERIES and not doc.get("is_return")


def parse_serial_numbers(value):
	"""Serial numbers are entered one per line (commas are accepted too)."""
	return [s.strip() for s in re.split(r"[\n,]+", value or "") if s.strip()]


def get_serialized_asset_rows(doc):
	"""Rows for which ERPNext auto-creates one Asset per unit (see `BuyingController.auto_make_assets`)."""
	from erpnext.controllers.buying_controller import get_asset_item_details

	if not is_it_purchase_receipt(doc):
		return []

	rows = [d for d in doc.get("items") if d.is_fixed_asset and flt(d.qty) > 0]
	if not rows:
		return []

	items = get_asset_item_details(list({d.item_code for d in rows}))
	return [
		d
		for d in rows
		if (item := items.get(d.item_code))
		and item.auto_create_assets
		and item.asset_naming_series
		and not item.is_grouped_asset
	]


def validate_serial_numbers(doc):
	seen = {}
	for row in get_serialized_asset_rows(doc):
		serial_numbers = parse_serial_numbers(row.get(SERIAL_NUMBERS_FIELD))
		if not serial_numbers:
			frappe.throw(
				_("Row #{0}: Serial Numbers are required for fixed asset item {1}.").format(
					row.idx, frappe.bold(row.item_code)
				),
				title=_("Missing Serial Numbers"),
			)
		if flt(row.qty) != cint(row.qty):
			frappe.throw(
				_("Row #{0}: Quantity of fixed asset item {1} must be a whole number.").format(
					row.idx, frappe.bold(row.item_code)
				)
			)
		if len(serial_numbers) != cint(row.qty):
			frappe.throw(
				_(
					"Row #{0}: Item {1} has quantity {2} but {3} serial numbers. Enter one serial number per line."
				).format(row.idx, frappe.bold(row.item_code), cint(row.qty), len(serial_numbers)),
				title=_("Serial Numbers Mismatch"),
			)
		for serial_no in serial_numbers:
			key = (row.item_code, serial_no)
			if key in seen:
				frappe.throw(
					_("Row #{0}: Serial Number {1} of item {2} is repeated (also in row #{3}).").format(
						row.idx, frappe.bold(serial_no), frappe.bold(row.item_code), seen[key]
					)
				)
			seen[key] = row.idx

		existing = frappe.get_all(
			"Asset",
			filters={
				"item_code": row.item_code,
				ASSET_SERIAL_NO_FIELD: ("in", serial_numbers),
				"docstatus": ("<", 2),
			},
			fields=["name", ASSET_SERIAL_NO_FIELD],
			limit=1,
		)
		if existing:
			frappe.throw(
				_("Row #{0}: Serial Number {1} of item {2} is already used by Asset {3}.").format(
					row.idx,
					frappe.bold(existing[0][ASSET_SERIAL_NO_FIELD]),
					frappe.bold(row.item_code),
					frappe.utils.get_link_to_form("Asset", existing[0].name),
				)
			)


def set_asset_serial_numbers(doc):
	"""Run in `on_submit`, after ERPNext created the Assets of the receipt.

	Each row's Assets are matched to its serial numbers in creation order. They
	were inserted with `db_insert` (no Asset hooks), so the value is written directly.
	"""
	for row in get_serialized_asset_rows(doc):
		serial_numbers = parse_serial_numbers(row.get(SERIAL_NUMBERS_FIELD))
		assets = frappe.get_all(
			"Asset",
			filters={"purchase_receipt": doc.name, "purchase_receipt_item": row.name, "docstatus": 0},
			fields=["name", ASSET_SERIAL_NO_FIELD],
			order_by="creation asc, name asc",
		)
		if len(assets) != len(serial_numbers):
			frappe.throw(
				_(
					"Row #{0}: {1} Assets were created for item {2} but {3} serial numbers were entered."
				).format(row.idx, len(assets), frappe.bold(row.item_code), len(serial_numbers))
			)
		for asset, serial_no in zip(assets, serial_numbers, strict=True):
			if asset.get(ASSET_SERIAL_NO_FIELD) != serial_no:
				frappe.db.set_value(
					"Asset", asset.name, ASSET_SERIAL_NO_FIELD, serial_no, update_modified=False
				)


def enqueue_auto_submit_assets(doc):
	if not doc.get(AUTO_SUBMIT_ASSETS_FIELD) or doc.get("is_return"):
		return

	# After commit, so the job sees the Assets created by this submit.
	frappe.enqueue(
		"masar_mce_assets.it_asset_auto_submit.submit_purchase_receipt_assets",
		queue="long",
		job_id=f"masar_mce_assets::auto_submit_assets::{doc.name}",
		deduplicate=True,
		enqueue_after_commit=True,
		purchase_receipt=doc.name,
	)
	frappe.msgprint(
		_("The Assets of this receipt will be submitted in the background."), alert=True, indicator="blue"
	)


def check_warehouses(doc):
    for r in doc.get("items"):
        if r.rejected_qty == 0 and (r.warehouse == r.rejected_warehouse):
            r.rejected_warehouse = None