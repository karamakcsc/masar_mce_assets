// Copyright (c) 2026, KCSC and contributors
// For license information, please see license.txt

masar_mce_assets.it_matrix.PURCHASE_RECEIPT_FIELDS = [
	"custom_warranty_expiry",
	"custom_invoice_date",
	"custom_invoice_no",
	"custom_referral_decision_no",
	"custom_approval_letter_date",
	"custom_approval_letter_no",
];

masar_mce_assets.it_matrix.apply_purchase_receipt = async function (frm) {
	const status = await masar_mce_assets.it_matrix.get_status_after_buying_cycle(frm);

	masar_mce_assets.it_matrix.set_naming_series(frm, status, status.purchase_receipt_naming_series);

	// masar_mce hides every custom field in the normal cycle, which IT users get by default.
	if (frm.fields_dict.custom_auto_submit_assets) {
		frm.set_df_property("custom_auto_submit_assets", "hidden", 0);
	}
	if (status.member) {
		masar_mce_assets.it_matrix.PURCHASE_RECEIPT_FIELDS.forEach((fieldname) => {
			if (!frm.fields_dict[fieldname]) return;
			frm.set_df_property(fieldname, "depends_on", "");
			frm.set_df_property(fieldname, "hidden", 0);
		});
		const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
		if (grid && grid.get_docfield("custom_serial_numbers_it")) {
			grid.update_docfield_property("custom_serial_numbers_it", "hidden", 0);
		}
	}

	// Normal cycle is checked by default for IT asset users; they can still uncheck it.
	if (status.applicable && frm.is_new() && !frm.it_matrix_defaults_applied) {
		frm.it_matrix_defaults_applied = true;
		if (frm.fields_dict.custom_normal_cycle && !cint(frm.doc.custom_normal_cycle)) {
			frm.set_value("custom_normal_cycle", 1);
		}
	}
};

frappe.ui.form.on("Purchase Receipt", {
	refresh(frm) {
		masar_mce_assets.it_matrix.apply_purchase_receipt(frm);
	},
});
