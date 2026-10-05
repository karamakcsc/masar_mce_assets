from masar_mce_assets.asset_location_limit import validate_location_limits_configuration


def validate(self, method):
	validate_location_limits_configuration(self)
