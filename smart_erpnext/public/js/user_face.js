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

		if (frm.doc.user_image && !frm.doc.face_descriptor) {
			frm.dashboard.set_headline_alert(
				__(
					"Face login is not set up yet. Upload a clear photo, save, then click Register Face from Photo or Camera."
				),
				"orange"
			);
		} else if (frm.doc.face_descriptor) {
			frm.dashboard.set_headline_alert(__("Face login is registered for this user."), "green");
		}
	},

	user_image(frm) {
		if (frm.doc.user_image && !frm.doc.face_descriptor) {
			frm.dashboard.set_headline_alert(
				__(
					"Save the user and click Register Face from Photo or Camera to enable face login."
				),
				"blue"
			);
		}
	},
});

frappe.provide("smart_erpnext.user_face");

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

	frappe.dom.freeze(__("Registering face from photo..."));

	try {
		await smart_erpnext.face.load_models();
		const image = await smart_erpnext.face.load_image(frm.doc.user_image);
		const descriptor = await smart_erpnext.face.get_descriptor_from_image(image);
		await smart_erpnext.user_face._save_descriptor(frm, descriptor, 0);
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

smart_erpnext.user_face.register_from_camera = async function (frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Register Face from Camera"),
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "camera_preview",
				options: `
					<div class="face-register-camera-wrap">
						<video id="face-register-video" autoplay muted playsinline style="width:100%;border-radius:8px;background:#111;"></video>
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
