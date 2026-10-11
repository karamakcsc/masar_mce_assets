// Copyright (c) 2026, KCSC and contributors
// For license information, please see license.txt

masar_mce_assets.it_matrix.MOVEMENT_LOCATION_FIELD = "custom_default_target_location";
masar_mce_assets.it_matrix.MOVEMENT_MANDATORY_FIELDS = [
	"custom_approval_letter_no",
	"custom_approval_letter_date",
	"custom_default_target_location",
];

masar_mce_assets.it_matrix.apply_asset_movement = async function (frm) {
	const it_matrix = masar_mce_assets.it_matrix;
	const status = await it_matrix.get_status();
	frm.it_matrix_status = status;

	it_matrix.MOVEMENT_MANDATORY_FIELDS.forEach((fieldname) => {
		frm.set_df_property(fieldname, "hidden", 0);
		frm.set_df_property(fieldname, "reqd", status.applicable ? 1 : 0);
	});

	if (!status.applicable || frm.doc.docstatus !== 0) return;

	const purpose_df = frappe.meta.get_docfield(frm.doctype, "purpose");
	const purposes = (purpose_df.options || "")
		.split("\n")
		.filter((purpose) => status.allowed_asset_movement_purposes.includes(purpose));
	frm.set_df_property("purpose", "options", ["", ...purposes].join("\n"));
	if (frm.is_new() && frm.doc.purpose && !purposes.includes(frm.doc.purpose)) {
		frm.set_value("purpose", "");
	}

	// Runs after ERPNext's set_required_fields, which sets target_location per purpose.
	frm.fields_dict.assets.grid.update_docfield_property("target_location", "read_only", 1);
	it_matrix.sync_movement_target_location(frm);
};

masar_mce_assets.it_matrix.sync_movement_target_location = function (frm) {
	const status = frm.it_matrix_status;
	if (!status || !status.applicable || frm.doc.docstatus !== 0 || !frm.doc.assets) return;

	const location = frm.doc[masar_mce_assets.it_matrix.MOVEMENT_LOCATION_FIELD] || "";
	frm.doc.assets.forEach((row) => {
		if (row.target_location !== location) {
			frappe.model.set_value(row.doctype, row.name, "target_location", location);
		}
	});
};

frappe.ui.form.on("Asset Movement", {
	refresh(frm) {
		masar_mce_assets.it_matrix.apply_asset_movement(frm);
	},

	purpose(frm) {
		masar_mce_assets.it_matrix.apply_asset_movement(frm);
	},

	custom_default_target_location(frm) {
		masar_mce_assets.it_matrix.sync_movement_target_location(frm);
	},
});

frappe.ui.form.on("Asset Movement Item", {
	assets_add(frm) {
		masar_mce_assets.it_matrix.sync_movement_target_location(frm);
	},
});
