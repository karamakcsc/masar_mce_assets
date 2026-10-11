app_name = "masar_mce_assets"
app_title = "Masar MCE Assets"
app_publisher = "KCSC"
app_description = "Masar MCE Assets"
app_email = "info@kcsc.com.jo"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "masar_mce_assets",
# 		"logo": "/assets/masar_mce_assets/logo.png",
# 		"title": "Masar MCE Assets",
# 		"route": "/masar_mce_assets",
# 		"has_permission": "masar_mce_assets.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/masar_mce_assets/css/masar_mce_assets.css"
# app_include_js = "/assets/masar_mce_assets/js/masar_mce_assets.js"

# include js, css files in header of web template
# web_include_css = "/assets/masar_mce_assets/css/masar_mce_assets.css"
# web_include_js = "/assets/masar_mce_assets/js/masar_mce_assets.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "masar_mce_assets/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
	"Purchase Receipt": ["public/js/it_asset_role_matrix.js", "public/js/purchase_receipt.js"],
	"Stock Entry": ["public/js/it_asset_role_matrix.js", "public/js/stock_entry.js"],
	"Asset Movement": ["public/js/it_asset_role_matrix.js", "public/js/asset_movement.js"],
}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "masar_mce_assets/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "masar_mce_assets.utils.jinja_methods",
# 	"filters": "masar_mce_assets.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "masar_mce_assets.install.before_install"
after_install = "masar_mce_assets.install.after_install"
after_migrate = "masar_mce_assets.install.after_migrate"

# Uninstallation
# ------------

# before_uninstall = "masar_mce_assets.uninstall.before_uninstall"
# after_uninstall = "masar_mce_assets.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "masar_mce_assets.utils.before_app_install"
# after_app_install = "masar_mce_assets.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "masar_mce_assets.utils.before_app_uninstall"
# after_app_uninstall = "masar_mce_assets.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "masar_mce_assets.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Location": {
		"validate": "masar_mce_assets.custom.location.location.validate",
	},
	"Asset": {
		"before_insert": "masar_mce_assets.custom.asset.asset.before_insert",
		"validate": "masar_mce_assets.custom.asset.asset.validate",
		"before_submit": "masar_mce_assets.custom.asset.asset.before_submit",
		"on_submit": "masar_mce_assets.custom.asset.asset.on_submit",
	},
	"Asset Movement": {
		"before_validate": "masar_mce_assets.custom.asset_movement.asset_movement.before_validate",
		"before_submit": "masar_mce_assets.custom.asset_movement.asset_movement.before_submit",
		"before_cancel": "masar_mce_assets.custom.asset_movement.asset_movement.before_cancel",
		"on_cancel": "masar_mce_assets.custom.asset_movement.asset_movement.on_cancel",
	},
	"Purchase Receipt": {
		"before_insert": "masar_mce_assets.custom.purchase_receipt.purchase_receipt.before_insert",
		"before_submit": "masar_mce_assets.custom.purchase_receipt.purchase_receipt.before_submit",
		"on_submit": "masar_mce_assets.custom.purchase_receipt.purchase_receipt.on_submit",
	},
	"Stock Entry": {
		"before_insert": "masar_mce_assets.custom.stock_entry.stock_entry.before_insert",
		"before_validate": "masar_mce_assets.custom.stock_entry.stock_entry.before_validate",
	},
	"Purchase Invoice": {
		"before_submit": "masar_mce_assets.custom.purchase_invoice.purchase_invoice.before_submit",
	},
}

# Fixtures
# --------

fixtures = [
	# masar_mce's fixtures also export every Purchase Receipt custom field, including the ones
	# in this module; keep both exports in sync.
	{"dt": "Custom Field", "filters": [["module", "=", "Masar MCE Assets"]]},
]

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"masar_mce_assets.tasks.all"
# 	],
# 	"daily": [
# 		"masar_mce_assets.tasks.daily"
# 	],
# 	"hourly": [
# 		"masar_mce_assets.tasks.hourly"
# 	],
# 	"weekly": [
# 		"masar_mce_assets.tasks.weekly"
# 	],
# 	"monthly": [
# 		"masar_mce_assets.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "masar_mce_assets.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "masar_mce_assets.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "masar_mce_assets.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["masar_mce_assets.utils.before_request"]
# after_request = ["masar_mce_assets.utils.after_request"]

# Job Events
# ----------
# before_job = ["masar_mce_assets.utils.before_job"]
# after_job = ["masar_mce_assets.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"masar_mce_assets.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

