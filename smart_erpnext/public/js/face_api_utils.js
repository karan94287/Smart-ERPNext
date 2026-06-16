frappe.provide("smart_erpnext.face");

smart_erpnext.face.MODEL_URL = "/assets/smart_erpnext/models";
smart_erpnext.face._models_loaded = false;
smart_erpnext.face._loading_promise = null;

smart_erpnext.face.DETECTOR_OPTIONS = () =>
	new faceapi.TinyFaceDetectorOptions({ inputSize: 416, scoreThreshold: 0.5 });

smart_erpnext.face.load_models = function () {
	if (smart_erpnext.face._models_loaded) {
		return Promise.resolve();
	}

	if (smart_erpnext.face._loading_promise) {
		return smart_erpnext.face._loading_promise;
	}

	if (typeof faceapi === "undefined") {
		return Promise.reject(new Error(__("Face scanner library failed to load.")));
	}

	smart_erpnext.face._loading_promise = Promise.all([
		faceapi.nets.tinyFaceDetector.loadFromUri(smart_erpnext.face.MODEL_URL),
		faceapi.nets.faceLandmark68Net.loadFromUri(smart_erpnext.face.MODEL_URL),
		faceapi.nets.faceRecognitionNet.loadFromUri(smart_erpnext.face.MODEL_URL),
	])
		.then(() => {
			smart_erpnext.face._models_loaded = true;
		})
		.catch(() => {
			smart_erpnext.face._loading_promise = null;
			throw new Error(
				__(
					"Could not load face scanner models. Run bench build --app smart_erpnext and hard refresh."
				)
			);
		});

	return smart_erpnext.face._loading_promise;
};

smart_erpnext.face._resolve_url = function (url) {
	if (!url) {
		return "";
	}
	if (url.startsWith("http://") || url.startsWith("https://")) {
		return encodeURI(url);
	}

	const path = url.startsWith("/") ? url : `/${url}`;
	const encoded_path = path
		.split("/")
		.map((segment, index) => (index === 0 ? segment : encodeURIComponent(segment)))
		.join("/");

	return `${window.location.origin}${encoded_path}`;
};

smart_erpnext.face.load_image = async function (url) {
	const image_url = smart_erpnext.face._resolve_url(url);
	if (!image_url) {
		throw new Error(__("Image URL is missing."));
	}

	const load_from_blob = (blob) =>
		new Promise((resolve, reject) => {
			const image = new Image();
			const object_url = URL.createObjectURL(blob);
			image.onload = () => {
				URL.revokeObjectURL(object_url);
				resolve(image);
			};
			image.onerror = () => {
				URL.revokeObjectURL(object_url);
				reject(new Error(__("Could not decode profile image.")));
			};
			image.src = object_url;
		});

	// Private ERPNext files need authenticated fetch — crossOrigin breaks this.
	if (url.includes("/private/") || url.includes("/files/")) {
		const response = await fetch(image_url, {
			credentials: "include",
			headers: frappe.csrf_token ? { "X-Frappe-CSRF-Token": frappe.csrf_token } : {},
		});
		if (!response.ok) {
			throw new Error(__("Could not load profile image. Check file permissions."));
		}
		return load_from_blob(await response.blob());
	}

	return new Promise((resolve, reject) => {
		const image = new Image();
		image.crossOrigin = "anonymous";
		image.onload = () => resolve(image);
		image.onerror = () => reject(new Error(__("Could not load profile image.")));
		image.src = image_url;
	});
};

smart_erpnext.face.get_descriptor_from_image = async function (image_element) {
	await smart_erpnext.face.load_models();

	const detection = await faceapi
		.detectSingleFace(image_element, smart_erpnext.face.DETECTOR_OPTIONS())
		.withFaceLandmarks()
		.withFaceDescriptor();

	if (!detection) {
		throw new Error(__("No face detected. Use a clear front-facing photo."));
	}

	return Array.from(detection.descriptor);
};

smart_erpnext.face.get_descriptor_from_video = async function (video_element, attempts = 3) {
	await smart_erpnext.face.load_models();

	let best_detection = null;

	for (let attempt = 0; attempt < attempts; attempt++) {
		const detection = await faceapi
			.detectSingleFace(video_element, smart_erpnext.face.DETECTOR_OPTIONS())
			.withFaceLandmarks()
			.withFaceDescriptor();

		if (!detection) {
			await smart_erpnext.face._wait(200);
			continue;
		}

		if (!best_detection || detection.detection.score > best_detection.detection.score) {
			best_detection = detection;
		}

		if (detection.detection.score >= 0.85) {
			break;
		}

		await smart_erpnext.face._wait(150);
	}

	if (!best_detection) {
		return null;
	}

	return Array.from(best_detection.descriptor);
};

smart_erpnext.face._wait = function (ms) {
	return new Promise((resolve) => setTimeout(resolve, ms));
};

smart_erpnext.face.get_camera_stream = async function () {
	if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
		throw new Error(__("Camera is not supported in this browser."));
	}

	return navigator.mediaDevices.getUserMedia({
		video: {
			facingMode: "user",
			width: { ideal: 640 },
			height: { ideal: 480 },
		},
		audio: false,
	});
};
