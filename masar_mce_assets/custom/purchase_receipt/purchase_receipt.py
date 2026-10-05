from masar_mce_assets.asset_location_limit import (
	get_purchase_document_incoming_quantities,
	validate_incoming_asset_quantities,
)


def before_submit(self, method):
	# Assets are auto-created in on_submit via db_insert (no Asset hooks), so validate here.
	validate_incoming_asset_quantities(get_purchase_document_incoming_quantities(self))
