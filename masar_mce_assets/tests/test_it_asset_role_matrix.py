# Copyright (c) 2026, KCSC and contributors
# For license information, please see license.txt

from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime, nowdate

from masar_mce_assets.custom.asset_movement.it_asset import apply_it_asset_movement_rules
from masar_mce_assets.custom.stock_entry.stock_entry import validate_it_asset_stock_entry_type
from masar_mce_assets.it_asset_auto_submit import submit_purchase_receipt_assets
from masar_mce_assets.it_asset_purchase_receipt import (
	ASSET_SERIAL_NO_FIELD,
	parse_serial_numbers,
)
from masar_mce_assets.it_asset_purchase_receipt import (
	before_insert as purchase_receipt_before_insert,
)
from masar_mce_assets.it_asset_role_matrix import (
	ALLOWED_STOCK_ENTRY_TYPE,
	PURCHASE_RECEIPT_NAMING_SERIES,
	SETTINGS_DOCTYPE,
	STOCK_ENTRY_NAMING_SERIES,
	apply_it_naming_series,
	get_current_user_status,
	get_role_matrix_status,
	is_it_asset_role_matrix_applicable,
)

IT_ROLE = "IT Warehouse"
IGNORE_ROLE = "System Manager"
OTHER_IT_ROLE = "_Test IT Asset Role"
OTHER_IGNORE_ROLE = "_Test IT Asset Ignore Role"
PLAIN_ROLE = "_Test IT Asset Plain Role"

USERS = {
	"it": [IT_ROLE],
	"ignore": [IGNORE_ROLE],
	"both": [IT_ROLE, IGNORE_ROLE],
	"none": [PLAIN_ROLE],
	"other_it": [OTHER_IT_ROLE],
	"other_ignore": [IT_ROLE, OTHER_IGNORE_ROLE],
}

CATEGORY = "_Test IT Matrix Category"
CATEGORY_NO_BOOK = "_Test IT Matrix Category No Book"
LOCATION_A = "_Test IT Matrix A"
LOCATION_B = "_Test IT Matrix B"

MOVEMENT_FIELDS = {
	"custom_approval_letter_no": "AL-1",
	"custom_approval_letter_date": nowdate(),
}


def user_email(key):
	return f"it_matrix_{key}@example.com"


class ITAssetRoleMatrixTestCase(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		for role in (IT_ROLE, OTHER_IT_ROLE, OTHER_IGNORE_ROLE, PLAIN_ROLE):
			if not frappe.db.exists("Role", role):
				frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert()

		settings = frappe.get_single(SETTINGS_DOCTYPE)
		settings.set("it_asset_roles", [{"role": IT_ROLE}, {"role": OTHER_IT_ROLE}])
		settings.set("ignore_roles", [{"role": IGNORE_ROLE}, {"role": OTHER_IGNORE_ROLE}])
		settings.save()

		for key, roles in USERS.items():
			self.make_user(user_email(key), roles)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		# Cached in Redis, which the rollback does not reach.
		frappe.clear_document_cache(SETTINGS_DOCTYPE, SETTINGS_DOCTYPE)
		for key in USERS:
			frappe.cache.hdel("roles", user_email(key))

	def make_user(self, email, roles):
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": email.split("@")[0],
					"send_welcome_email": 0,
				}
			).insert()
		user = frappe.get_doc("User", email)
		user.set("roles", [{"role": role} for role in roles])
		user.save()

	@contextmanager
	def as_user(self, key):
		frappe.set_user(user_email(key))
		try:
			yield
		finally:
			frappe.set_user("Administrator")


class TestRoleMatrix(ITAssetRoleMatrixTestCase):
	def test_it_role_only_applies(self):
		self.assertTrue(is_it_asset_role_matrix_applicable(user_email("it")))

	def test_ignore_role_only_is_exempt(self):
		status = get_role_matrix_status(user_email("ignore"))
		self.assertFalse(status.applicable)
		self.assertTrue(status.ignored)
		self.assertTrue(status.member)

	def test_ignore_role_takes_precedence(self):
		status = get_role_matrix_status(user_email("both"))
		self.assertFalse(status.applicable)
		self.assertTrue(status.ignored)

	def test_user_outside_both_functions(self):
		status = get_role_matrix_status(user_email("none"))
		self.assertFalse(status.applicable)
		self.assertFalse(status.member)

	def test_other_configured_it_role_applies(self):
		self.assertTrue(is_it_asset_role_matrix_applicable(user_email("other_it")))

	def test_other_configured_ignore_role_takes_precedence(self):
		self.assertFalse(is_it_asset_role_matrix_applicable(user_email("other_ignore")))

	def test_defaults_to_session_user(self):
		with self.as_user("it"):
			self.assertTrue(is_it_asset_role_matrix_applicable())
			self.assertTrue(get_current_user_status().applicable)

	def test_role_lists_are_configurable(self):
		settings = frappe.get_single(SETTINGS_DOCTYPE)
		settings.set("it_asset_roles", [{"role": PLAIN_ROLE}])
		settings.save()
		self.assertFalse(is_it_asset_role_matrix_applicable(user_email("it")))
		self.assertTrue(is_it_asset_role_matrix_applicable(user_email("none")))

	def test_settings_reject_role_in_both_lists(self):
		settings = frappe.get_single(SETTINGS_DOCTYPE)
		settings.append("ignore_roles", {"role": IT_ROLE})
		self.assertRaisesRegex(frappe.ValidationError, "both", settings.save)

	def test_settings_reject_all_role(self):
		settings = frappe.get_single(SETTINGS_DOCTYPE)
		settings.append("ignore_roles", {"role": "All"})
		self.assertRaisesRegex(frappe.ValidationError, "not allowed", settings.save)


class TestNamingSeries(ITAssetRoleMatrixTestCase):
	def named(self, doctype, key, naming_series=None):
		doc = frappe.new_doc(doctype)
		doc.naming_series = naming_series
		with self.as_user(key):
			apply_it_naming_series(doc)
		return doc.naming_series

	def test_it_user_always_gets_it_series(self):
		self.assertEqual(self.named("Purchase Receipt", "it"), PURCHASE_RECEIPT_NAMING_SERIES)
		self.assertEqual(
			self.named("Purchase Receipt", "it", "MAT-PRE-.YYYY.-"), PURCHASE_RECEIPT_NAMING_SERIES
		)
		self.assertEqual(self.named("Stock Entry", "it"), STOCK_ENTRY_NAMING_SERIES)
		self.assertEqual(self.named("Stock Entry", "it", "MAT-STE-.YYYY.-"), STOCK_ENTRY_NAMING_SERIES)

	def test_ignore_user_may_choose_it_series(self):
		self.assertEqual(self.named("Purchase Receipt", "both", "MAT-PRE-.YYYY.-"), "MAT-PRE-.YYYY.-")
		self.assertEqual(
			self.named("Purchase Receipt", "both", PURCHASE_RECEIPT_NAMING_SERIES),
			PURCHASE_RECEIPT_NAMING_SERIES,
		)
		self.assertEqual(self.named("Stock Entry", "ignore", "MAT-STE-.YYYY.-"), "MAT-STE-.YYYY.-")
		self.assertEqual(
			self.named("Stock Entry", "ignore", STOCK_ENTRY_NAMING_SERIES), STOCK_ENTRY_NAMING_SERIES
		)

	def test_other_users_keep_standard_series(self):
		self.assertEqual(self.named("Stock Entry", "none", "MAT-STE-.YYYY.-"), "MAT-STE-.YYYY.-")
		self.assertIsNone(self.named("Purchase Receipt", "none"))

	def test_other_users_cannot_use_it_series(self):
		self.assertRaises(
			frappe.PermissionError, self.named, "Stock Entry", "none", STOCK_ENTRY_NAMING_SERIES
		)

	def test_it_series_registered_in_options(self):
		from masar_mce_assets.it_asset_role_matrix import register_it_naming_series

		register_it_naming_series()
		self.assertIn(
			PURCHASE_RECEIPT_NAMING_SERIES,
			frappe.get_meta("Purchase Receipt").get_options("naming_series").split("\n"),
		)
		self.assertIn(
			STOCK_ENTRY_NAMING_SERIES, frappe.get_meta("Stock Entry").get_options("naming_series").split("\n")
		)

	def test_normal_cycle_default_for_it_user(self):
		doc = frappe.new_doc("Purchase Receipt")
		doc.custom_normal_cycle = None
		with self.as_user("it"):
			purchase_receipt_before_insert(doc)
		self.assertEqual(doc.custom_normal_cycle, 1)

		# A value sent by the client is kept: it is a default, not a rule.
		doc = frappe.new_doc("Purchase Receipt")
		doc.custom_normal_cycle = 0
		with self.as_user("it"):
			purchase_receipt_before_insert(doc)
		self.assertEqual(doc.custom_normal_cycle, 0)

		doc = frappe.new_doc("Purchase Receipt")
		doc.custom_normal_cycle = None
		with self.as_user("both"):
			purchase_receipt_before_insert(doc)
		self.assertIsNone(doc.custom_normal_cycle)


class TestStockEntryType(ITAssetRoleMatrixTestCase):
	def stock_entry(self, stock_entry_type):
		return frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"company": frappe.db.get_value("Company", {}, "name"),
				"stock_entry_type": stock_entry_type,
			}
		)

	def test_it_user_limited_to_issue_type(self):
		with self.as_user("it"):
			validate_it_asset_stock_entry_type(self.stock_entry(ALLOWED_STOCK_ENTRY_TYPE))
			self.assertRaises(
				frappe.PermissionError,
				validate_it_asset_stock_entry_type,
				self.stock_entry("Material Transfer"),
			)
			self.assertRaises(
				frappe.PermissionError, validate_it_asset_stock_entry_type, self.stock_entry(None)
			)

	def test_other_users_keep_all_types(self):
		for key in ("ignore", "both", "none"):
			with self.as_user(key):
				validate_it_asset_stock_entry_type(self.stock_entry("Material Transfer"))

	def test_api_insert_rejected_with_it_naming_series_forced(self):
		from frappe.client import insert

		with self.as_user("it"):
			doc = self.stock_entry("Material Transfer")
			doc.flags.ignore_permissions = True
			self.assertRaises(frappe.PermissionError, doc.insert)
			self.assertEqual(doc.naming_series, STOCK_ENTRY_NAMING_SERIES)

		# The REST/whitelisted path runs the same hooks.
		with self.as_user("it"), patch("frappe.model.document.Document.check_permission"):
			self.assertRaises(frappe.PermissionError, insert, self.stock_entry("Material Transfer").as_dict())


class AssetTestCase(ITAssetRoleMatrixTestCase):
	"""Builds an asset category, items and locations on the site's first company with asset accounts."""

	def setUp(self):
		super().setUp()
		self.company = frappe.db.get_value(
			"Asset Category Account", {"fixed_asset_account": ("is", "set")}, "company_name"
		)
		if not self.company:
			self.skipTest("Needs a company with a fixed asset account")

		fixed_asset_account = frappe.db.get_value(
			"Asset Category Account", {"company_name": self.company}, "fixed_asset_account"
		)
		self.make_category(CATEGORY, fixed_asset_account, with_book=True)
		self.make_category(CATEGORY_NO_BOOK, fixed_asset_account, with_book=False)
		self.unit_item = self.make_item("_Test IT Matrix Laptop", CATEGORY, grouped=False)
		self.grouped_item = self.make_item("_Test IT Matrix Cables", CATEGORY, grouped=True)
		self.no_book_item = self.make_item("_Test IT Matrix Printer", CATEGORY_NO_BOOK, grouped=False)
		for location in (LOCATION_A, LOCATION_B):
			frappe.get_doc({"doctype": "Location", "location_name": location}).insert()

	def make_category(self, name, fixed_asset_account, with_book):
		frappe.get_doc(
			{
				"doctype": "Asset Category",
				"asset_category_name": name,
				"accounts": [{"company_name": self.company, "fixed_asset_account": fixed_asset_account}],
				"finance_books": [
					{
						"depreciation_method": "Straight Line",
						"total_number_of_depreciations": 36,
						"frequency_of_depreciation": 1,
					}
				]
				if with_book
				else [],
			}
		).insert()

	def make_item(self, code, category, grouped):
		return (
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": code,
					"item_name": code,
					"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
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

	def make_purchase_receipt(self, rows, naming_series=PURCHASE_RECEIPT_NAMING_SERIES, auto_submit=0):
		"""rows: [(item_code, qty, serial_numbers)]"""
		warehouse = frappe.db.get_value("Warehouse", {"company": self.company, "is_group": 0}, "name")
		pr = frappe.get_doc(
			{
				"doctype": "Purchase Receipt",
				"naming_series": naming_series,
				"company": self.company,
				"supplier": frappe.db.get_value("Supplier", {}, "name"),
				"posting_date": nowdate(),
				"set_warehouse": warehouse,
				"custom_normal_cycle": 1,
				"custom_auto_submit_assets": auto_submit,
				"items": [
					{
						"item_code": item_code,
						"qty": qty,
						"rate": 100,
						"warehouse": warehouse,
						"asset_location": LOCATION_A,
						"custom_serial_numbers_it": serial_numbers,
					}
					for item_code, qty, serial_numbers in rows
				],
			}
		)
		pr.insert()
		return pr

	def assets_of(self, pr):
		return frappe.get_all(
			"Asset",
			filters={"purchase_receipt": pr.name},
			fields=["name", "docstatus", "item_code", ASSET_SERIAL_NO_FIELD, "purchase_receipt_item"],
			order_by="creation asc, name asc",
		)


class TestPurchaseReceiptSerialNumbers(AssetTestCase):
	def test_parse_serial_numbers(self):
		self.assertEqual(parse_serial_numbers(" A1\nA2, A3\n\n"), ["A1", "A2", "A3"])
		self.assertEqual(parse_serial_numbers(None), [])

	def test_missing_serial_numbers_rejected(self):
		pr = self.make_purchase_receipt([(self.unit_item, 2, "")])
		self.assertRaisesRegex(frappe.ValidationError, r"Row #1: Serial Numbers are required", pr.submit)

	def test_serial_count_must_match_quantity(self):
		pr = self.make_purchase_receipt([(self.unit_item, 2, "SN-1")])
		self.assertRaisesRegex(frappe.ValidationError, "quantity 2 but 1 serial", pr.submit)

	def test_repeated_serial_rejected(self):
		pr = self.make_purchase_receipt([(self.unit_item, 2, "SN-1\nSN-1")])
		self.assertRaisesRegex(frappe.ValidationError, "repeated", pr.submit)

	def test_serial_numbers_transferred_to_assets(self):
		pr = self.make_purchase_receipt([(self.unit_item, 3, "SN-1\nSN-2\nSN-3")])
		pr.submit()
		assets = self.assets_of(pr)
		self.assertEqual([a[ASSET_SERIAL_NO_FIELD] for a in assets], ["SN-1", "SN-2", "SN-3"])
		self.assertEqual({a.purchase_receipt_item for a in assets}, {pr.items[0].name})

		# Reusing a serial number of the same item on another receipt is rejected.
		other = self.make_purchase_receipt([(self.unit_item, 1, "SN-2")])
		self.assertRaisesRegex(frappe.ValidationError, "already used", other.submit)

	def test_grouped_items_and_non_it_receipts_not_validated(self):
		self.make_purchase_receipt([(self.grouped_item, 5, "")]).submit()
		self.make_purchase_receipt([(self.unit_item, 1, "")], naming_series="MAT-PRE-.YYYY.-").submit()

	def test_auto_submit_checkbox_is_off_by_default(self):
		field = frappe.get_meta("Purchase Receipt").get_field("custom_auto_submit_assets")
		self.assertEqual(field.fieldtype, "Check")
		self.assertFalse(field.reqd)
		self.assertEqual(frappe.new_doc("Purchase Receipt").custom_auto_submit_assets, 0)


@patch("frappe.db.commit")
class TestAutoSubmitAssets(AssetTestCase):
	def test_not_processed_without_checkbox(self, commit):
		pr = self.make_purchase_receipt([(self.unit_item, 1, "SN-1")])
		pr.submit()
		result = submit_purchase_receipt_assets(pr.name)
		self.assertEqual(result.submitted, [])
		self.assertEqual([a.docstatus for a in self.assets_of(pr)], [0])

	def test_assets_submitted_with_category_depreciation(self, commit):
		pr = self.make_purchase_receipt([(self.unit_item, 2, "SN-1\nSN-2")], auto_submit=1)
		pr.submit()

		result = submit_purchase_receipt_assets(pr.name)
		self.assertEqual(len(result.submitted), 2)
		self.assertEqual(result.failed, {})

		for row in self.assets_of(pr):
			asset = frappe.get_doc("Asset", row.name)
			self.assertEqual(asset.docstatus, 1)
			self.assertEqual(asset.calculate_depreciation, 1)
			self.assertEqual(asset.available_for_use_date, asset.purchase_date)
			self.assertEqual(len(asset.finance_books), 1)
			book = asset.finance_books[0]
			self.assertEqual(book.depreciation_method, "Straight Line")
			self.assertEqual(book.total_number_of_depreciations, 36)
			self.assertEqual(book.frequency_of_depreciation, 1)
			self.assertEqual(book.depreciation_start_date, asset.purchase_date)

		# A rerun neither submits again nor adds finance book rows.
		self.assertEqual(submit_purchase_receipt_assets(pr.name).submitted, [])
		self.assertEqual(
			frappe.db.count("Asset Finance Book", {"parent": ("in", [a.name for a in self.assets_of(pr)])}), 2
		)

	def test_missing_finance_book_logged_and_others_processed(self, commit):
		pr = self.make_purchase_receipt(
			[(self.no_book_item, 1, "P-1"), (self.unit_item, 1, "SN-1")], auto_submit=1
		)
		pr.submit()

		result = submit_purchase_receipt_assets(pr.name)
		assets = {a.item_code: a for a in self.assets_of(pr)}
		self.assertEqual(result.submitted, [assets[self.unit_item].name])
		self.assertIn("has no Finance Book", result.failed[assets[self.no_book_item].name])
		self.assertEqual(assets[self.no_book_item].docstatus, 0)
		self.assertEqual(assets[self.unit_item].docstatus, 1)
		self.assertTrue(
			frappe.db.exists(
				"Error Log", {"reference_doctype": "Asset", "reference_name": assets[self.no_book_item].name}
			)
		)
		self.assertTrue(
			frappe.db.exists(
				"Comment",
				{
					"reference_doctype": "Purchase Receipt",
					"reference_name": pr.name,
					"content": ("like", "%1 failed%"),
				},
			)
		)

	def test_existing_category_book_row_is_updated_not_duplicated(self, commit):
		pr = self.make_purchase_receipt([(self.unit_item, 1, "SN-1")], auto_submit=1)
		pr.submit()
		name = self.assets_of(pr)[0].name
		# As left by an earlier run that failed after adding the row.
		asset = frappe.get_doc("Asset", name)
		asset.append(
			"finance_books",
			{
				"depreciation_method": "Straight Line",
				"total_number_of_depreciations": 1,
				"frequency_of_depreciation": 12,
			},
		)
		asset.flags.ignore_validate = True
		asset.save()

		submit_purchase_receipt_assets(pr.name)
		asset = frappe.get_doc("Asset", name)
		self.assertEqual(asset.docstatus, 1)
		self.assertEqual(len(asset.finance_books), 1)
		self.assertEqual(asset.finance_books[0].total_number_of_depreciations, 36)

	def test_enqueued_only_with_checkbox(self, commit):
		with patch("frappe.enqueue") as enqueue:
			self.make_purchase_receipt([(self.unit_item, 1, "SN-1")]).submit()
			enqueue.assert_not_called()
			pr = self.make_purchase_receipt([(self.unit_item, 1, "SN-2")], auto_submit=1)
			pr.submit()
			enqueue.assert_called_once()
			self.assertEqual(enqueue.call_args.kwargs["purchase_receipt"], pr.name)
			self.assertTrue(enqueue.call_args.kwargs["enqueue_after_commit"])


class TestAssetMovement(AssetTestCase):
	def setUp(self):
		super().setUp()
		self.assets = [self.make_asset(LOCATION_A), self.make_asset(LOCATION_A)]

	def make_asset(self, location):
		asset = frappe.get_doc(
			{
				"doctype": "Asset",
				"company": self.company,
				"item_code": self.unit_item,
				"asset_name": "IT Matrix Asset",
				"location": location,
				"is_existing_asset": 1,
				"calculate_depreciation": 0,
				"purchase_date": nowdate(),
				"available_for_use_date": nowdate(),
				"gross_purchase_amount": 100,
				"purchase_amount": 100,
			}
		).insert()
		asset.submit()
		return asset

	def movement(self, purpose="Transfer", location=LOCATION_B, target=None, **fields):
		return frappe.get_doc(
			{
				"doctype": "Asset Movement",
				"company": self.company,
				"purpose": purpose,
				"transaction_date": now_datetime(),
				"custom_default_target_location": location,
				**MOVEMENT_FIELDS,
				**fields,
				"assets": [
					{"asset": a.name, "source_location": a.location, "target_location": target}
					for a in self.assets
				],
			}
		)

	def test_asset_submit_receipt_movement_allowed_for_it_user(self):
		# Asset.on_submit creates a Receipt movement, which the IT rules must not block.
		with self.as_user("it"), patch("frappe.model.document.Document.check_permission"):
			asset = frappe.get_doc(
				{
					"doctype": "Asset",
					"company": self.company,
					"item_code": self.unit_item,
					"asset_name": "IT Matrix Asset",
					"location": LOCATION_A,
					"is_existing_asset": 1,
					"purchase_date": nowdate(),
					"available_for_use_date": nowdate(),
					"gross_purchase_amount": 100,
					"purchase_amount": 100,
				}
			)
			asset.insert()
			asset.submit()
		self.assertTrue(
			frappe.db.exists("Asset Movement Item", {"asset": asset.name, "target_location": LOCATION_A})
		)

	def test_it_user_limited_to_transfer_and_issue(self):
		with self.as_user("it"):
			for purpose in ("Transfer", "Issue"):
				apply_it_asset_movement_rules(self.movement(purpose))
			for purpose in ("Receipt", "Transfer and Issue"):
				self.assertRaises(
					frappe.PermissionError, apply_it_asset_movement_rules, self.movement(purpose)
				)

	def test_fields_mandatory_only_for_it_user(self):
		for fieldname in (
			"custom_approval_letter_no",
			"custom_approval_letter_date",
			"custom_default_target_location",
		):
			field = frappe.get_meta("Asset Movement").get_field(fieldname)
			self.assertFalse(field.hidden)
			self.assertFalse(field.reqd)

			doc = self.movement(**{fieldname: None})
			with self.as_user("it"):
				self.assertRaises(frappe.MandatoryError, apply_it_asset_movement_rules, doc)
			with self.as_user("both"):
				apply_it_asset_movement_rules(doc)

	def test_location_controls_target_location_for_it_user(self):
		doc = self.movement(target=LOCATION_A)
		doc.append("assets", {"asset": self.assets[0].name})
		with self.as_user("it"):
			apply_it_asset_movement_rules(doc)
		self.assertEqual([d.target_location for d in doc.assets], [LOCATION_B] * 3)
		self.assertEqual([d.source_location for d in doc.assets[:2]], [LOCATION_A] * 2)

	def test_invalid_location_rejected(self):
		with self.as_user("it"):
			self.assertRaises(
				frappe.LinkValidationError,
				apply_it_asset_movement_rules,
				self.movement(location="_Test IT Matrix Missing"),
			)

	def test_exempt_users_keep_manual_target_location(self):
		for key in ("ignore", "both", "none"):
			doc = self.movement(purpose="Receipt", target=LOCATION_A)
			with self.as_user(key):
				apply_it_asset_movement_rules(doc)
			self.assertEqual({d.target_location for d in doc.assets}, {LOCATION_A})

	def test_api_insert_syncs_target_location(self):
		from frappe.client import insert, submit

		with self.as_user("it"), patch("frappe.model.document.Document.check_permission"):
			movement = insert(self.movement(target=None).as_dict())
			self.assertEqual({d["target_location"] for d in movement["assets"]}, {LOCATION_B})
			submit(movement)
		for asset in self.assets:
			self.assertEqual(frappe.db.get_value("Asset", asset.name, "location"), LOCATION_B)

	def test_api_insert_rejects_other_purpose(self):
		from frappe.client import insert

		with self.as_user("it"), patch("frappe.model.document.Document.check_permission"):
			self.assertRaises(
				frappe.PermissionError,
				insert,
				self.movement(purpose="Transfer and Issue", target=LOCATION_B).as_dict(),
			)

	def test_standard_transfer_for_other_users(self):
		with self.as_user("none"), patch("frappe.model.document.Document.check_permission"):
			movement = self.movement(target=LOCATION_B, custom_default_target_location=None)
			movement.insert()
			movement.submit()
		self.assertEqual(frappe.db.get_value("Asset", self.assets[0].name, "location"), LOCATION_B)
