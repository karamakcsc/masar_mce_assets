// Copyright (c) 2026, KCSC and contributors
// For license information, please see license.txt

// Form behaviour of the IT asset role matrix. The server enforces every rule;
// this only mirrors them in the form.
frappe.provide("masar_mce_assets.it_matrix");

masar_mce_assets.it_matrix.get_status = function () {
	const it_matrix = masar_mce_assets.it_matrix;
	if (!it_matrix.status) {
		it_matrix.status = frappe
			.xcall("masar_mce_assets.it_asset_role_matrix.get_current_user_status")
			.catch(() => {
				it_matrix.status = null;
				return {};
			});
	}
	return it_matrix.status;
};

// Resolves after masar_mce's buying cycle customizations are applied, so the
// properties set by the IT matrix are not overwritten by them.
masar_mce_assets.it_matrix.get_status_after_buying_cycle = async function (frm) {
	const buying_cycle = window.masar_mce && masar_mce.buying_cycle;
	const [status] = await Promise.all([
		masar_mce_assets.it_matrix.get_status(),
		buying_cycle ? buying_cycle.get_customizations(frm.doctype) : null,
	]);
	return status;
};

masar_mce_assets.it_matrix.set_naming_series = function (frm, status, series) {
	if (!frm.fields_dict.naming_series) return;

	const meta_df = frappe.meta.get_docfield(frm.doctype, "naming_series");
	const options = (meta_df.options || "").split("\n").filter(Boolean);

	let allowed;
	if (status.applicable) {
		allowed = [series];
	} else if (status.member) {
		allowed = options.includes(series) ? options : [...options, series];
	} else {
		allowed = options.filter((option) => option !== series);
	}

	frm.set_df_property("naming_series", "options", allowed.join("\n"));
	frm.set_df_property("naming_series", "read_only", status.applicable ? 1 : meta_df.read_only);

	if (frm.is_new() && !allowed.includes(frm.doc.naming_series)) {
		frm.set_value("naming_series", allowed[0] || "");
	}
};
