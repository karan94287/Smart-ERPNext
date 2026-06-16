frappe.provide("smart_erpnext.face_login");

smart_erpnext.face_login._starting = false;
smart_erpnext.face_login._initialized = false;

smart_erpnext.face_login.init = function () {
	if (!window.location.pathname.includes("/login")) {
		return;
	}

	if (smart_erpnext.face_login._initialized) {
		return;
	}

	smart_erpnext.face_login._initialized = true;
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

	login.face_login = function () {
		smart_erpnext.face_login.open();
	};

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
		smart_erpnext.face_login.open();
	});
};

smart_erpnext.face_login.bind_hash_route = function () {
	if (smart_erpnext.face_login._hash_bound) {
		return;
	}

	smart_erpnext.face_login._hash_bound = true;

	$(window).on("hashchange", () => {
		if (window.location.hash === "#face-login") {
			smart_erpnext.face_login.open();
		}
	});
};

smart_erpnext.face_login.open = function () {
	smart_erpnext.face_login.init();
	smart_erpnext.face_login.show();
};

smart_erpnext.face_login.show = function () {
	smart_erpnext.face_login.ensure_section();

	if (typeof login !== "undefined" && login.reset_sections) {
		login.reset_sections();
	}

	const $section = $("section.for-face-login");
	$section.toggle(true);

	const $email = $("#face-login-email");
	if ($email.length) {
		$email.trigger("focus");
	}

	smart_erpnext.face_login.refresh_status();

	// Wait for the section to be visible before attaching the camera stream.
	requestAnimationFrame(() => {
		smart_erpnext.face_login.start_scanner();
	});
};

smart_erpnext.face_login.ensure_section = function () {
	const $existing = $("section.for-face-login");
	if ($existing.length && $existing.find("#face-login-video").length) {
		return;
	}

	if ($existing.length) {
		$existing.remove();
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
						<label for="face-login-email">${__("Email or Username")} <span class="text-danger">*</span></label>
						<input
							type="text"
							id="face-login-email"
							class="form-control"
							placeholder="${__("Enter the account you registered face login for")}"
							autocomplete="username"
							required
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

	const $anchor = $("section.for-login").first();
	if ($anchor.length) {
		$anchor.before($section);
	} else {
		$(".page-content-wrapper").first().append($section);
	}
};

smart_erpnext.face_login.get_video_element = function () {
	return document.getElementById("face-login-video");
};

smart_erpnext.face_login._get_user_hint = function () {
	return ($("#face-login-email").val() || "").trim();
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
					"Face not registered yet. Sign in with password → open User → Save photo → click Register Face from Camera."
				)
			);
			return;
		}

		if (!data.any_registered) {
			hint.text(
				__(
					"No face login registered yet. An admin must register from User → Register Face from Camera."
				)
			);
			return;
		}

		hint.text(
			user
				? __("Face login will sign in as {0} only.", [user])
				: __("Type the exact username or email for the account you want to sign in to.")
		);
	} catch (error) {
		hint.text("");
	}
};

smart_erpnext.face_login.start_scanner = async function () {
	if (smart_erpnext.face_login._starting) {
		return;
	}

	smart_erpnext.face_login.ensure_section();
	const video = smart_erpnext.face_login.get_video_element();
	const status = $(".face-login-status");

	if (!video) {
		const message = __("Face login screen failed to load. Please refresh the page.");
		if (status.length) {
			status.text(message);
		}
		smart_erpnext.face_login.show_error(__("Face Login"), message);
		return;
	}

	smart_erpnext.face_login._starting = true;
	smart_erpnext.face_login.stop_stream();

	try {
		if (status.length) {
			status.text(__("Loading face scanner..."));
		}
		await smart_erpnext.face.load_models();

		if (status.length) {
			status.text(__("Starting camera..."));
		}
		const stream = await smart_erpnext.face.get_camera_stream();

		const active_video = smart_erpnext.face_login.get_video_element();
		if (!active_video) {
			throw new Error(__("Camera preview is not available. Please refresh and try again."));
		}

		smart_erpnext.face_login._stream = stream;
		active_video.srcObject = stream;
		await active_video.play();

		if (status.length) {
			status.text(__("Position your face in the frame, then tap Scan Face."));
		}
	} catch (error) {
		const message =
			error?.message || __("Camera access is required for face login.");
		if (status.length) {
			status.text(message);
		}
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

	const video = smart_erpnext.face_login.get_video_element();
	if (video) {
		video.srcObject = null;
	}
};

smart_erpnext.face_login.verify = async function () {
	const video = smart_erpnext.face_login.get_video_element();
	const status = $(".face-login-status");
	const $button = $(".btn-face-scan");

	if (!video || !smart_erpnext.face_login._stream) {
		smart_erpnext.face_login.show_error(
			__("Camera Not Ready"),
			__("Allow camera permission and try again.")
		);
		return;
	}

	$button.prop("disabled", true);
	status.text(__("Scanning face..."));

	try {
		const user = smart_erpnext.face_login._get_user_hint();
		if (!user) {
			throw new Error(
				__("Enter your email or username first. Face login only works for that specific account.")
			);
		}

		const descriptor = await smart_erpnext.face.get_descriptor_from_video(video, 5);
		if (!descriptor) {
			throw new Error(__("No face detected. Center your face and try again."));
		}

		const detection_score = smart_erpnext.face._last_detection_score;
		if (detection_score != null && detection_score < 0.7) {
			throw new Error(__("Face not clear enough. Move closer to the camera and try again."));
		}

		status.text(__("Verifying face for {0}...", [user]));

		const response = await frappe.call({
			method: "smart_erpnext.api.face_login.verify_and_login",
			args: {
				descriptor,
				user,
			},
			freeze: true,
		});

		const data = response.message || {};
		if (data.message === "Logged In" || data.message === "No App") {
			status.text(__("Signed in as {0}", [data.user || user]));
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
	if (window.location.hash === "#face-login") {
		smart_erpnext.face_login.open();
	}
});
