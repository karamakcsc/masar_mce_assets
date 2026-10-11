# Copyright (c) 2026, KCSC and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

# "All" would put every user in the list; "Guest" never edits these documents.
DISALLOWED_ROLES = ("All", "Guest")


class ITAssetRoleMatrixSettings(Document):
	def validate(self):
		it_asset_roles = self.validate_roles("it_asset_roles")
		ignore_roles = self.validate_roles("ignore_roles")

		if both := sorted(it_asset_roles & ignore_roles):
			frappe.throw(
				_("Roles {0} cannot be both an IT Asset Role and an Ignore Role.").format(
					", ".join(frappe.bold(r) for r in both)
				)
			)

	def validate_roles(self, fieldname):
		label = self.meta.get_label(fieldname)
		roles = set()
		for row in self.get(fieldname):
			if row.role in DISALLOWED_ROLES:
				frappe.throw(_("{0}, row #{1}: Role {2} is not allowed.").format(label, row.idx, row.role))
			if row.role in roles:
				frappe.throw(_("{0}, row #{1}: Role {2} is duplicated.").format(label, row.idx, row.role))
			roles.add(row.role)
		return roles
