frappe.ui.form.on("User", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.name === "Guest") {
			return;
		}

		frm.add_custom_button(__("Register Face for Login"), () => {
			smart_erpnext.user_face.register(frm);
		});
	},

	user_image(frm) {
		if (frm.doc.user_image && !frm.doc.face_descriptor) {
			frm.dashboard.set_headline_alert(
				__("Save the user and click 'Register Face for Login' to enable face login."),
				"blue"
			);
		}
	},
});

frappe.provide("smart_erpnext.user_face");

smart_erpnext.user_face.register = async function (frm) {
	if (!frm.doc.user_image) {
		frappe.msgprint(__("Upload a profile photo first."));
		return;
	}

	frappe.dom.freeze(__("Registering face..."));

	try {
		await smart_erpnext.face.load_models();
		const image = await smart_erpnext.face.load_image(frm.doc.user_image);
		const descriptor = await smart_erpnext.face.get_descriptor_from_image(image);

		await frappe.call({
			method: "smart_erpnext.api.face_login.save_face_descriptor",
			args: {
				descriptor,
				user: frm.doc.name,
			},
		});

		await frm.reload_doc();
		frappe.show_alert({
			message: __("Face registered for login."),
			indicator: "green",
		});
	} catch (error) {
		frappe.msgprint({
			title: __("Face Registration Failed"),
			message: error.message || __("Could not register face from this photo."),
			indicator: "red",
		});
	} finally {
		frappe.dom.unfreeze();
	}
};
