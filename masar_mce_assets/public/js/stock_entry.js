// Copyright (c) 2026, KCSC and contributors
// For license information, please see license.txt

masar_mce_assets.it_matrix.apply_stock_entry = async function (frm) {
	const status = await masar_mce_assets.it_matrix.get_status();
	frm.it_matrix_status = status;

	masar_mce_assets.it_matrix.set_naming_series(frm, status, status.stock_entry_naming_series);

	if (status.applicable && frm.is_new() && frm.doc.stock_entry_type !== status.allowed_stock_entry_type) {
		frm.set_value("stock_entry_type", status.allowed_stock_entry_type);
	}
};

frappe.ui.form.on("Stock Entry", {
	setup(frm) {
		frm.set_query("stock_entry_type", () => {
			const status = frm.it_matrix_status;
			return status && status.applicable
				? { filters: { name: status.allowed_stock_entry_type } }
				: {};
		});
	},

	refresh(frm) {
		masar_mce_assets.it_matrix.apply_stock_entry(frm);
	},
});
