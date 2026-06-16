frappe.provide("smart_erpnext.face_login");

smart_erpnext.face_login._starting = false;

smart_erpnext.face_login.init = function () {
	if (!window.location.pathname.includes("/login")) {
		return;
	}

	smart_erpnext.face_login.patch_login_route();
	smart_erpnext.face_login.ensure_section();
	smart_erpnext.face_login.add_button();
	smart_erpnext.face_login.bind_hash_route();
};

smart_erpnext.face_login.patch_login_route = function () {
	if (typeof login === "undefined" || login._face_login_patched) {
		return;
	}

	login._face_login_patched = true;

	if (typeof login.face_login !== "function") {
		login.face_login = function () {
			smart_erpnext.face_login.show();
		};
	}

	const original_reset = login.reset_sections;
	login.reset_sections = function (hide) {
		original_reset.call(this, hide);
		if (hide || hide === undefined) {
			$("section.for-face-login").toggle(false);
			smart_erpnext.face_login.stop_stream();
		}
	};
};

smart_erpnext.face_login.add_button = function () {
	if ($(".btn-face-login").length) {
		return;
	}

	const $button = $(`
		<button type="button" class="btn btn-sm btn-default btn-block btn-face-login mt-2">
			${__("Login with Face")}
		</button>
	`);

	const $socialLogins = $("section.for-login .social-logins").first();
	if ($socialLogins.length) {
		const $wrapper = $(`
			<div class="login-with-face social-login-buttons">
				<div class="login-button-wrapper"></div>
			</div>
		`);
		$wrapper.find(".login-button-wrapper").append($button);
		$socialLogins.append($wrapper);
	} else {
		$("section.for-login .page-card-actions").first().append($button);
	}

	$button.on("click", (event) => {
		event.preventDefault();
		window.location.hash = "face-login";
		smart_erpnext.face_login.show();
	});
};

smart_erpnext.face_login.bind_hash_route = function () {
	if (smart_erpnext.face_login._hash_bound) {
		return;
	}

	smart_erpnext.face_login._hash_bound = true;

	$(window).on("hashchange", () => {
		if (window.location.hash === "#face-login") {
			smart_erpnext.face_login.show();
		}
	});

	if (window.location.hash === "#face-login") {
		smart_erpnext.face_login.show();
	}
};

smart_erpnext.face_login.show = function () {
	if (typeof login !== "undefined" && login.reset_sections) {
		login.reset_sections();
	}

	$("section.for-face-login").toggle(true);
	smart_erpnext.face_login.refresh_status();
	smart_erpnext.face_login.start_scanner();
};

smart_erpnext.face_login.ensure_section = function () {
	if ($("section.for-face-login").length) {
		return;
	}

	const logo_src = $(".app-logo").first().attr("src") || "";
	const $section = $(`
		<section class="for-face-login" style="display: none;">
			<div class="page-card-head text-center">
				<img class="app-logo" src="${logo_src}">
				<h4>${__("Face Login")}</h4>
				<p class="text-muted">${__("Look at the camera to sign in")}</p>
			</div>
			<div class="login-content page-card face-login-card">
				<div class="face-login-body">
					<div class="form-group face-login-email-wrap">
						<label for="face-login-email">${__("Email or Username")}</label>
						<input
							type="text"
							id="face-login-email"
							class="form-control"
							placeholder="${__("Optional — leave blank to match any registered user")}"
							autocomplete="username"
						/>
						<p class="help-box small text-muted face-login-hint"></p>
					</div>
					<video id="face-login-video" autoplay muted playsinline></video>
					<p class="face-login-status text-muted">${__("Preparing camera...")}</p>
				</div>
				<div class="page-card-actions">
					<button type="button" class="btn btn-sm btn-primary btn-block btn-face-scan">
						${__("Scan Face")}
					</button>
					<p class="text-center sign-up-message mt-2">
						<a href="#login">${__("Back to Login")}</a>
					</p>
				</div>
			</div>
		</section>
	`);

	$("section.for-login").first().before($section);

	const login_email = ($("#login_email").val() || "").trim();
	if (login_email) {
		$("#face-login-email").val(login_email);
	}
};

smart_erpnext.face_login._get_user_hint = function () {
	return ($("#face-login-email").val() || $("#login_email").val() || "").trim();
};

smart_erpnext.face_login.refresh_status = async function () {
	const user = smart_erpnext.face_login._get_user_hint();
	const hint = $(".face-login-hint");

	if (!hint.length) {
		return;
	}

	try {
		const response = await frappe.call({
			method: "smart_erpnext.api.face_login.get_face_login_status",
			args: { user: user || undefined },
		});
		const data = response.message || {};

		if (user && !data.user_exists) {
			hint.text(__("This user was not found on this site."));
			return;
		}

		if (user && data.user_exists && !data.user_registered) {
			hint.text(
				__(
					"Face login is not registered for this user yet. Sign in with password and register from the User form."
				)
			);
			return;
		}

		if (!data.any_registered) {
			hint.text(
				__(
					"No face login registered yet. An admin must register from User → Register Face from Photo/Camera."
				)
			);
			return;
		}

		hint.text(
			user
				? __("Face login is set up for this user.")
				: __("Leave blank to match against all registered users.")
		);
	} catch (error) {
		hint.text("");
	}
};

smart_erpnext.face_login.start_scanner = async function () {
	if (smart_erpnext.face_login._starting) {
		return;
	}

	smart_erpnext.face_login._starting = true;
	smart_erpnext.face_login.stop_stream();

	const video = document.getElementById("face-login-video");
	const status = $(".face-login-status");

	try {
		status.text(__("Loading face scanner..."));
		await smart_erpnext.face.load_models();

		status.text(__("Starting camera..."));
		const stream = await smart_erpnext.face.get_camera_stream();

		smart_erpnext.face_login._stream = stream;
		video.srcObject = stream;
		await video.play();
		status.text(__("Position your face in the frame, then tap Scan Face."));
	} catch (error) {
		const message =
			error?.message || __("Camera access is required for face login.");
		status.text(message);
		smart_erpnext.face_login.show_error(__("Face Login"), message);
	} finally {
		smart_erpnext.face_login._starting = false;
	}
};

smart_erpnext.face_login.show_error = function (title, message) {
	if (smart_erpnext.face_login._last_error === message) {
		return;
	}

	smart_erpnext.face_login._last_error = message;
	frappe.msgprint({
		title,
		message,
		indicator: "red",
	});
};

smart_erpnext.face_login.stop_stream = function () {
	if (smart_erpnext.face_login._stream) {
		smart_erpnext.face_login._stream.getTracks().forEach((track) => track.stop());
		smart_erpnext.face_login._stream = null;
	}
};

smart_erpnext.face_login.verify = async function () {
	const video = document.getElementById("face-login-video");
	const status = $(".face-login-status");
	const $button = $(".btn-face-scan");

	if (!smart_erpnext.face_login._stream) {
		smart_erpnext.face_login.show_error(
			__("Camera Not Ready"),
			__("Allow camera permission and try again.")
		);
		return;
	}

	$button.prop("disabled", true);
	status.text(__("Scanning face..."));

	try {
		const descriptor = await smart_erpnext.face.get_descriptor_from_video(video);
		if (!descriptor) {
			throw new Error(__("No face detected. Center your face and try again."));
		}

		const user = smart_erpnext.face_login._get_user_hint();
		status.text(__("Verifying face..."));

		const response = await frappe.call({
			method: "smart_erpnext.api.face_login.verify_and_login",
			args: {
				descriptor,
				user: user || undefined,
			},
			freeze: true,
		});

		const data = response.message || {};
		if (data.message === "Logged In" || data.message === "No App") {
			status.text(__("Success"));
			window.location.href =
				frappe.utils.sanitise_redirect(frappe.utils.get_url_arg("redirect-to")) ||
				data.home_page ||
				"/app";
			return;
		}

		throw new Error(__("Face not recognized."));
	} catch (error) {
		let message = __("Face not recognized. Try again or use password login.");

		if (error?._server_messages) {
			try {
				message = JSON.parse(JSON.parse(error._server_messages)[0]).message || message;
			} catch (parse_error) {
				// keep default message
			}
		} else if (error?.message) {
			message = error.message;
		}

		status.text(message);
		smart_erpnext.face_login.show_error(__("Face Login Failed"), message);
	} finally {
		$button.prop("disabled", false);
	}
};

$(document).on("click", ".btn-face-scan", () => {
	smart_erpnext.face_login.verify();
});

$(document).on("input", "#face-login-email", () => {
	smart_erpnext.face_login.refresh_status();
});

$(document).on("login_rendered", () => {
	smart_erpnext.face_login.init();
});
