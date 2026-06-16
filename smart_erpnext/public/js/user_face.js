frappe.ui.form.on("User", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.name === "Guest") {
			return;
		}

		frm.add_custom_button(__("Register Face from Photo"), () => {
			smart_erpnext.user_face.register_from_photo(frm);
		});

		frm.add_custom_button(__("Register Face from Camera"), () => {
			smart_erpnext.user_face.register_from_camera(frm);
		});

		smart_erpnext.user_face.update_status_banner(frm);
	},

	user_image(frm) {
		smart_erpnext.user_face.update_status_banner(frm);
	},

	after_save(frm) {
		if (frm.doc.user_image && !frm.doc.face_descriptor) {
			frappe.show_alert(
				{
					message: __(
						"Profile photo saved. Now click Register Face from Camera to enable face login."
					),
					indicator: "blue",
				},
				8
			);
		}
	},
});

frappe.provide("smart_erpnext.user_face");

smart_erpnext.user_face.update_status_banner = function (frm) {
	if (!frm.doc.user_image) {
		frm.dashboard.set_headline_alert(
			__(
				"Step 1: Upload a clear front-facing profile photo and click Save."
			),
			"orange"
		);
		return;
	}

	if (frm.is_dirty()) {
		frm.dashboard.set_headline_alert(
			__(
				"Step 2: Click Save first, then use Register Face from Photo or Camera."
			),
			"orange"
		);
		return;
	}

	if (!frm.doc.face_descriptor) {
		frm.dashboard.set_headline_alert(
			__(
				"Step 3: Photo is saved. Click Register Face from Camera (recommended) to finish setup."
			),
			"orange"
		);
		return;
	}

	frm.dashboard.set_headline_alert(__("Face login is registered for this user."), "green");
};

smart_erpnext.user_face._ensure_saved = async function (frm) {
	if (!frm.is_dirty()) {
		return;
	}

	await frm.save();
};

smart_erpnext.user_face._save_descriptor = async function (frm, descriptor, append = 0) {
	await frappe.call({
		method: "smart_erpnext.api.face_login.save_face_descriptor",
		args: {
			descriptor,
			user: frm.doc.name,
			append,
		},
	});

	await frm.reload_doc();
	smart_erpnext.user_face.update_status_banner(frm);
	frappe.show_alert({
		message: __("Face registered for login."),
		indicator: "green",
	});
};

smart_erpnext.user_face.register_from_photo = async function (frm) {
	if (!frm.doc.user_image) {
		frappe.msgprint(__("Upload a profile photo first."));
		return;
	}

	try {
		await smart_erpnext.user_face._ensure_saved(frm);
	} catch (error) {
		return;
	}

	frappe.dom.freeze(__("Registering face from photo..."));

	try {
		await smart_erpnext.face.load_models();
		const image = await smart_erpnext.face.load_image(frm.doc.user_image);
		const descriptor = await smart_erpnext.face.get_descriptor_from_image(image);
		await smart_erpnext.user_face._save_descriptor(frm, descriptor, 0);
	} catch (error) {
		frappe.msgprint({
			title: __("Face Registration Failed"),
			message:
				error.message ||
				__(
					"Could not register face from this photo. Try Register Face from Camera instead."
				),
			indicator: "red",
		});
	} finally {
		frappe.dom.unfreeze();
	}
};

smart_erpnext.user_face.register_from_camera = async function (frm) {
	try {
		await smart_erpnext.user_face._ensure_saved(frm);
	} catch (error) {
		return;
	}

	const dialog = new frappe.ui.Dialog({
		title: __("Register Face from Camera"),
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "camera_preview",
				options: `
					<div class="face-register-camera-wrap">
						<video id="face-register-video" autoplay muted playsinline style="width:100%;border-radius:8px;background:#111;min-height:220px;"></video>
						<p class="text-muted small face-register-status">${__("Starting camera...")}</p>
					</div>
				`,
			},
		],
		primary_action_label: __("Capture Face"),
		primary_action: async () => {
			const video = dialog.$wrapper.find("#face-register-video")[0];
			const status = dialog.$wrapper.find(".face-register-status");

			try {
				status.text(__("Scanning face..."));
				const descriptor = await smart_erpnext.face.get_descriptor_from_video(video, 5);
				if (!descriptor) {
					throw new Error(__("No face detected. Look at the camera and try again."));
				}

				const append = !!frm.doc.face_descriptor;
				await smart_erpnext.user_face._save_descriptor(frm, descriptor, append ? 1 : 0);
				smart_erpnext.user_face._stop_stream(dialog._stream);
				dialog.hide();
			} catch (error) {
				status.text(error.message || __("Could not capture face."));
				frappe.msgprint({
					title: __("Face Registration Failed"),
					message: error.message || __("Could not capture face."),
					indicator: "red",
				});
			}
		},
	});

	dialog.onhide = () => {
		smart_erpnext.user_face._stop_stream(dialog._stream);
	};

	dialog.show();

	try {
		await smart_erpnext.face.load_models();
		dialog._stream = await smart_erpnext.face.get_camera_stream();
		const video = dialog.$wrapper.find("#face-register-video")[0];
		video.srcObject = dialog._stream;
		await video.play();
		dialog.$wrapper.find(".face-register-status").text(
			__("Look at the camera, then click Capture Face.")
		);
	} catch (error) {
		dialog.$wrapper.find(".face-register-status").text(
			error.message || __("Camera access is required.")
		);
	}
};

smart_erpnext.user_face._stop_stream = function (stream) {
	if (stream) {
		stream.getTracks().forEach((track) => track.stop());
	}
};
