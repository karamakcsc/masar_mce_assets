from masar_mce_assets import it_asset_purchase_receipt
from masar_mce_assets.asset_location_limit import (
	get_purchase_document_incoming_quantities,
	validate_incoming_asset_quantities,
)


def before_insert(self, method):
	it_asset_purchase_receipt.before_insert(self)


def before_submit(self, method):
	# Assets are auto-created in on_submit via db_insert (no Asset hooks), so validate here.
	validate_incoming_asset_quantities(get_purchase_document_incoming_quantities(self))
	it_asset_purchase_receipt.validate_serial_numbers(self)


def on_submit(self, method):
	# Hooks run after the controller's on_submit, which created the Assets.
	it_asset_purchase_receipt.set_asset_serial_numbers(self)
	it_asset_purchase_receipt.enqueue_auto_submit_assets(self)
