# Copyright (c) 2026, KCSC and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime, nowdate

from masar_mce_assets.asset_location_limit import (
	LIMITS_FIELD,
	AssetLocationLimitExceededError,
	get_location_asset_quantity,
)

LAPTOP = "_Test LocLimit Laptop"
PRINTER = "_Test LocLimit Printer"
LOCATION_A = "_Test LocLimit A"
LOCATION_B = "_Test LocLimit B"
LOCATION_FREE = "_Test LocLimit Unlimited"


class TestAssetLocationLimit(FrappeTestCase):
	"""Uses the site's existing company, supplier, warehouse and accounts; every test is rolled back."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.relax_site_mandatory_fields()
		self.company = frappe.db.get_value(
			"Asset Category Account", {"fixed_asset_account": ("is", "set")}, "company_name"
		)
		fixed_asset_account = frappe.db.get_value(
			"Asset Category Account", {"company_name": self.company}, "fixed_asset_account"
		)
		self.item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")

		for category in (LAPTOP, PRINTER):
			frappe.get_doc(
				{
					"doctype": "Asset Category",
					"asset_category_name": category,
					"accounts": [{"company_name": self.company, "fixed_asset_account": fixed_asset_account}],
				}
			).insert()

		self.items = {
			(LAPTOP, False): self.make_item(LAPTOP, grouped=False),
			(LAPTOP, True): self.make_item(LAPTOP, grouped=True),
			(PRINTER, False): self.make_item(PRINTER, grouped=False),
			(PRINTER, True): self.make_item(PRINTER, grouped=True),
		}
		for location in (LOCATION_A, LOCATION_B, LOCATION_FREE):
			frappe.get_doc({"doctype": "Location", "location_name": location}).insert()

	def tearDown(self):
		frappe.db.rollback()

	# Helpers

	def relax_site_mandatory_fields(self):
		# The site makes this custom field mandatory, which breaks the Receipt movement ERPNext
		# creates on Asset submit. Patched on the request-local meta only, never in the database.
		field = frappe.get_meta("Asset Movement").get_field("custom_default_target_location")
		if field and field.reqd:
			patcher = patch.object(field, "reqd", 0)
			patcher.start()
			self.addCleanup(patcher.stop)

	def make_item(self, category, grouped):
		code = f"{category} {'Grouped' if grouped else 'Unit'}"
		return (
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": code,
					"item_name": code,
					"item_group": self.item_group,
					"stock_uom": "Nos",
					"is_stock_item": 0,
					"is_fixed_asset": 1,
					"asset_category": category,
					"auto_create_assets": 1,
					"is_grouped_asset": int(grouped),
					"asset_naming_series": "ACC-ASS-.YYYY.-",
				}
			)
			.insert()
			.name
		)

	def set_limits(self, location, limits):
		doc = frappe.get_doc("Location", location)
		doc.set(LIMITS_FIELD, [{"asset_category": c, "maximum_quantity": q} for c, q in limits.items()])
		doc.save()

	def make_asset(self, category, location, qty=1, submit=True):
		asset = frappe.get_doc(
			{
				"doctype": "Asset",
				"company": self.company,
				"item_code": self.items[(category, True)],
				"asset_name": category,
				"location": location,
				"asset_quantity": qty,
				"is_existing_asset": 1,
				"calculate_depreciation": 0,
				"purchase_date": nowdate(),
				"available_for_use_date": nowdate(),
				"gross_purchase_amount": 100 * qty,
				"purchase_amount": 100 * qty,
			}
		).insert()
		if submit:
			asset.submit()
		return asset

	def make_purchase_receipt(self, rows, submit=True):
		"""rows: [(category, grouped, qty, location)]"""
		reference = frappe.db.get_value(
			"Purchase Receipt Item",
			{"is_fixed_asset": 1, "docstatus": 1},
			["parent", "warehouse"],
			as_dict=True,
		)
		supplier = frappe.db.get_value("Purchase Receipt", reference.parent, "supplier")
		pr = frappe.get_doc(
			{
				"doctype": "Purchase Receipt",
				"company": self.company,
				"supplier": supplier,
				"posting_date": nowdate(),
				"set_warehouse": reference.warehouse,
				"custom_normal_cycle": 1,
				"items": [
					{
						"item_code": self.items[(category, grouped)],
						"qty": qty,
						"rate": 100,
						"warehouse": reference.warehouse,
						"asset_location": location,
					}
					for category, grouped, qty, location in rows
				],
			}
		).insert()
		if submit:
			pr.submit()
		return pr

	def move(self, assets, target, purpose="Transfer"):
		movement = frappe.get_doc(
			{
				"doctype": "Asset Movement",
				"company": self.company,
				"purpose": purpose,
				"transaction_date": now_datetime(),
				"assets": [
					{"asset": a.name, "source_location": a.location, "target_location": target}
					for a in assets
				],
			}
		).insert()
		movement.submit()
		return movement

	def quantity(self, location, category=LAPTOP):
		return get_location_asset_quantity(location, category)

	def created_assets(self, pr):
		return frappe.get_all("Asset", {"purchase_receipt": pr.name}, pluck="asset_quantity")

	# Purchase Receipt

	def test_01_unlimited_category_allows_receipt(self):
		self.set_limits(LOCATION_A, {PRINTER: 1})
		pr = self.make_purchase_receipt([(LAPTOP, True, 500, LOCATION_A)])
		self.assertEqual(self.created_assets(pr), [500])

	def test_02_receipt_below_maximum(self):
		self.set_limits(LOCATION_A, {LAPTOP: 100})
		self.make_asset(LAPTOP, LOCATION_A, 50)
		self.make_purchase_receipt([(LAPTOP, True, 20, LOCATION_A)])
		self.assertEqual(self.quantity(LOCATION_A), 70)

	def test_03_receipt_exactly_maximum(self):
		self.set_limits(LOCATION_A, {LAPTOP: 100})
		self.make_asset(LAPTOP, LOCATION_A, 80)
		self.make_purchase_receipt([(LAPTOP, True, 20, LOCATION_A)])
		self.assertEqual(self.quantity(LOCATION_A), 100)

	def test_04_receipt_above_maximum_is_rejected_without_partial_assets(self):
		self.set_limits(LOCATION_A, {LAPTOP: 100})
		self.make_asset(LAPTOP, LOCATION_A, 80)

		pr = self.make_purchase_receipt([(LAPTOP, True, 21, LOCATION_A)], submit=False)
		self.assertRaises(AssetLocationLimitExceededError, pr.submit)

		# Non-grouped item: 21 Assets of one unit each, also rejected.
		pr = self.make_purchase_receipt([(LAPTOP, False, 21, LOCATION_A)], submit=False)
		self.assertRaises(AssetLocationLimitExceededError, pr.submit)
		self.assertEqual(self.created_assets(pr), [])
		self.assertEqual(self.quantity(LOCATION_A), 80)

	def test_receipt_counts_rows_for_same_location_together(self):
		self.set_limits(LOCATION_A, {LAPTOP: 10})
		pr = self.make_purchase_receipt(
			[(LAPTOP, True, 6, LOCATION_A), (LAPTOP, False, 5, LOCATION_A)], submit=False
		)
		self.assertRaises(AssetLocationLimitExceededError, pr.submit)

	# Asset Movement

	def test_05_movement_into_limited_location_allowed(self):
		self.set_limits(LOCATION_B, {LAPTOP: 100})
		self.make_asset(LAPTOP, LOCATION_B, 95)
		asset = self.make_asset(LAPTOP, LOCATION_A, 5)
		self.move([asset], LOCATION_B)
		self.assertEqual(self.quantity(LOCATION_B), 100)

	def test_06_movement_exceeding_destination_rejected(self):
		self.set_limits(LOCATION_B, {LAPTOP: 100})
		self.make_asset(LAPTOP, LOCATION_B, 95)
		asset = self.make_asset(LAPTOP, LOCATION_A, 6)
		self.assertRaises(AssetLocationLimitExceededError, self.move, [asset], LOCATION_B)
		self.assertEqual(frappe.db.get_value("Asset", asset.name, "location"), LOCATION_A)

	def test_07_movement_out_ignores_source_limit(self):
		asset = self.make_asset(LAPTOP, LOCATION_A, 10)
		# Limit lowered below the existing quantity: moving out must still work.
		self.set_limits(LOCATION_A, {LAPTOP: 1})
		self.move([asset], LOCATION_B)
		self.assertEqual(self.quantity(LOCATION_A), 0)
		self.assertEqual(self.quantity(LOCATION_B), 10)

	def test_same_location_receipt_is_not_counted_twice(self):
		self.set_limits(LOCATION_A, {LAPTOP: 10})
		# Asset submit creates a Receipt movement into the asset's own location.
		asset = self.make_asset(LAPTOP, LOCATION_A, 10)
		self.assertEqual(asset.docstatus, 1)
		self.move([asset], LOCATION_A, purpose="Receipt")
		self.assertEqual(self.quantity(LOCATION_A), 10)

	def test_movement_into_destination_counts_all_rows(self):
		self.set_limits(LOCATION_B, {LAPTOP: 10})
		assets = [self.make_asset(LAPTOP, LOCATION_A, 6), self.make_asset(LAPTOP, LOCATION_A, 5)]
		self.assertRaises(AssetLocationLimitExceededError, self.move, assets, LOCATION_B)

	def test_partial_movement_via_split(self):
		# ERPNext moves whole Assets; a partial move is a split followed by a movement.
		from erpnext.assets.doctype.asset.asset import split_asset

		self.set_limits(LOCATION_A, {LAPTOP: 10})
		self.set_limits(LOCATION_B, {LAPTOP: 4})
		asset = self.make_asset(LAPTOP, LOCATION_A, 10)

		new_asset = split_asset(asset.name, 4)  # location total unchanged, so allowed at the limit
		self.assertEqual(self.quantity(LOCATION_A), 10)

		self.move([new_asset], LOCATION_B)
		self.assertEqual(self.quantity(LOCATION_A), 6)
		self.assertEqual(self.quantity(LOCATION_B), 4)

	def test_cancelling_movement_back_into_full_location_rejected(self):
		self.set_limits(LOCATION_A, {LAPTOP: 10})
		asset = self.make_asset(LAPTOP, LOCATION_A, 5)
		movement = self.move([asset], LOCATION_B)
		self.make_asset(LAPTOP, LOCATION_A, 10)

		self.assertRaises(AssetLocationLimitExceededError, movement.cancel)

	# Quantity semantics

	def test_08_asset_quantity_counts_units_not_documents(self):
		self.make_asset(LAPTOP, LOCATION_A, 10)
		self.assertEqual(self.quantity(LOCATION_A), 10)

		self.set_limits(LOCATION_B, {LAPTOP: 9})
		self.assertRaises(
			AssetLocationLimitExceededError, self.make_asset, LAPTOP, LOCATION_B, 10, submit=False
		)

	def test_asset_quantity_increase_is_validated(self):
		self.set_limits(LOCATION_A, {LAPTOP: 10})
		asset = self.make_asset(LAPTOP, LOCATION_A, 8, submit=False)
		asset.asset_quantity = 11
		self.assertRaises(AssetLocationLimitExceededError, asset.save)

	def test_inactive_assets_are_not_counted(self):
		asset = self.make_asset(LAPTOP, LOCATION_A, 10)
		asset.db_set("status", "Scrapped")
		self.assertEqual(self.quantity(LOCATION_A), 0)

	def test_09_categories_validated_independently(self):
		self.set_limits(LOCATION_A, {LAPTOP: 10, PRINTER: 4})
		rows = [(LAPTOP, True, 10, LOCATION_A), (PRINTER, True, 5, LOCATION_A)]
		pr = self.make_purchase_receipt(rows, submit=False)
		self.assertRaises(AssetLocationLimitExceededError, pr.submit)

		self.set_limits(LOCATION_A, {LAPTOP: 10, PRINTER: 5})
		self.make_purchase_receipt(rows)
		self.assertEqual(self.quantity(LOCATION_A, LAPTOP), 10)
		self.assertEqual(self.quantity(LOCATION_A, PRINTER), 5)

	# API

	def test_10_api_cannot_bypass_limit(self):
		from frappe.client import insert, submit

		self.set_limits(LOCATION_B, {LAPTOP: 5})
		asset_payload = {
			"doctype": "Asset",
			"company": self.company,
			"item_code": self.items[(LAPTOP, True)],
			"asset_name": LAPTOP,
			"location": LOCATION_B,
			"asset_quantity": 6,
			"is_existing_asset": 1,
			"purchase_date": nowdate(),
			"available_for_use_date": nowdate(),
			"gross_purchase_amount": 600,
			"purchase_amount": 600,
		}
		self.assertRaises(AssetLocationLimitExceededError, insert, frappe.as_json(asset_payload))

		asset = self.make_asset(LAPTOP, LOCATION_A, 6)
		movement = insert(
			{
				"doctype": "Asset Movement",
				"company": self.company,
				"purpose": "Transfer",
				"transaction_date": str(now_datetime()),
				"assets": [
					{"asset": asset.name, "source_location": LOCATION_A, "target_location": LOCATION_B}
				],
			}
		)
		self.assertRaises(AssetLocationLimitExceededError, submit, movement)

	# Location configuration

	def test_11_duplicate_category_rejected(self):
		self.assertRaisesRegex(
			frappe.ValidationError,
			"already configured",
			frappe.get_doc(
				{
					"doctype": "Location",
					"location_name": "_Test LocLimit Duplicate",
					LIMITS_FIELD: [
						{"asset_category": LAPTOP, "maximum_quantity": 1},
						{"asset_category": LAPTOP, "maximum_quantity": 2},
					],
				}
			).insert,
		)

	def test_negative_maximum_rejected(self):
		self.assertRaisesRegex(
			frappe.ValidationError, "cannot be negative", self.set_limits, LOCATION_A, {LAPTOP: -1}
		)

	def test_zero_maximum_blocks_category(self):
		self.set_limits(LOCATION_A, {LAPTOP: 0})
		self.assertRaises(AssetLocationLimitExceededError, self.make_asset, LAPTOP, LOCATION_A, 1)

	def test_12_location_without_configuration_is_unlimited(self):
		self.make_asset(LAPTOP, LOCATION_FREE, 1000)
		asset = self.make_asset(PRINTER, LOCATION_A, 50)
		self.move([asset], LOCATION_FREE)
		self.make_purchase_receipt([(LAPTOP, True, 1000, LOCATION_FREE)])
		self.assertEqual(self.quantity(LOCATION_FREE), 2000)

	def test_existing_over_limit_asset_can_be_resaved(self):
		asset = self.make_asset(LAPTOP, LOCATION_A, 10, submit=False)
		self.set_limits(LOCATION_A, {LAPTOP: 5})
		asset.asset_name = "Renamed"
		asset.save()
