frappe.provide("smart_erpnext.face");

smart_erpnext.face.MODEL_URL = "/assets/smart_erpnext/models";
smart_erpnext.face._models_loaded = false;
smart_erpnext.face._loading_promise = null;

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
		.catch((error) => {
			smart_erpnext.face._loading_promise = null;
			throw new Error(
				__("Could not load face scanner models. Run bench build --app smart_erpnext and refresh.")
			);
		});

	return smart_erpnext.face._loading_promise;
};

smart_erpnext.face.get_descriptor_from_image = async function (image_element) {
	await smart_erpnext.face.load_models();

	const detection = await faceapi
		.detectSingleFace(image_element, new faceapi.TinyFaceDetectorOptions())
		.withFaceLandmarks()
		.withFaceDescriptor();

	if (!detection) {
		throw new Error(__("No face detected. Use a clear front-facing photo."));
	}

	return Array.from(detection.descriptor);
};

smart_erpnext.face.get_descriptor_from_video = async function (video_element) {
	await smart_erpnext.face.load_models();

	const detection = await faceapi
		.detectSingleFace(video_element, new faceapi.TinyFaceDetectorOptions())
		.withFaceLandmarks()
		.withFaceDescriptor();

	if (!detection) {
		return null;
	}

	return Array.from(detection.descriptor);
};

smart_erpnext.face.load_image = function (url) {
	return new Promise((resolve, reject) => {
		const image = new Image();
		image.crossOrigin = "anonymous";
		image.onload = () => resolve(image);
		image.onerror = () => reject(new Error(__("Could not load profile image.")));
		image.src = url;
	});
};

smart_erpnext.face.get_camera_stream = async function () {
	if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
		throw new Error(__("Camera is not supported in this browser."));
	}

	return navigator.mediaDevices.getUserMedia({
		video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } },
		audio: false,
	});
};
