import json
import math

import frappe
from frappe import _
from frappe.apps import get_default_path
from frappe.auth import LoginManager
from frappe.rate_limiter import rate_limit
from frappe.utils import slug

DESCRIPTOR_LENGTH = 128
MATCH_THRESHOLD = 0.65


def _parse_descriptor(descriptor):
	if isinstance(descriptor, str):
		descriptor = json.loads(descriptor)

	if not isinstance(descriptor, (list, tuple)) or len(descriptor) != DESCRIPTOR_LENGTH:
		frappe.throw(_("Invalid face data."))

	return [float(value) for value in descriptor]


def _parse_stored_descriptors(stored_value) -> list[list[float]]:
	if not stored_value:
		return []

	try:
		data = json.loads(stored_value)
	except (TypeError, json.JSONDecodeError):
		return []

	if isinstance(data, list) and data and isinstance(data[0], (int, float)):
		return [_parse_descriptor(data)]

	if isinstance(data, list):
		return [_parse_descriptor(item) for item in data if item]

	return []


def _euclidean_distance(first, second):
	return math.sqrt(sum((a - b) ** 2 for a, b in zip(first, second)))


def _resolve_user(user: str) -> str | None:
	user = (user or "").strip()
	if not user:
		return None

	if frappe.db.exists("User", user):
		return user

	return frappe.db.get_value(
		"User",
		{"enabled": 1, "username": user},
		"name",
	) or frappe.db.get_value(
		"User",
		{"enabled": 1, "email": user},
		"name",
	) or frappe.db.get_value(
		"User",
		{"enabled": 1, "mobile_no": user},
		"name",
	)


def _get_candidate_users(user: str | None = None) -> list[dict]:
	filters = {"enabled": 1, "face_descriptor": ["is", "set"]}
	if user:
		filters["name"] = user

	return frappe.get_all(
		"User",
		filters=filters,
		fields=["name", "face_descriptor", "user_type", "default_workspace", "user_image"],
	)


def _descriptor_distance(descriptor: list[float], stored_value) -> float | None:
	best_distance = None

	for stored_descriptor in _parse_stored_descriptors(stored_value):
		try:
			distance = _euclidean_distance(descriptor, stored_descriptor)
		except Exception:
			continue

		if best_distance is None or distance < best_distance:
			best_distance = distance

	return best_distance


def _find_best_match(descriptor: list[float], user: str | None = None) -> tuple[dict | None, float | None]:
	best_match = None
	best_distance = None

	for candidate in _get_candidate_users(user):
		distance = _descriptor_distance(descriptor, candidate.face_descriptor)
		if distance is None:
			continue

		if distance <= MATCH_THRESHOLD and (best_distance is None or distance < best_distance):
			best_distance = distance
			best_match = candidate

	return best_match, best_distance


def _login_user(user: str):
	frappe.local.login_manager = LoginManager()
	frappe.local.login_manager.login_as(user)

	response = frappe.local.response
	user_info = frappe.get_cached_value(
		"User",
		user,
		["user_type", "default_workspace"],
		as_dict=True,
	)

	if user_info.user_type == "Website User":
		response["message"] = "No App"
		response["home_page"] = get_default_path() or "/"
	else:
		response["message"] = "Logged In"
		if user_info.default_workspace:
			response["home_page"] = "/app/" + slug(user_info.default_workspace)
		else:
			response["home_page"] = get_default_path() or "/app"


def _registration_hint(user: str | None = None) -> str:
	if user:
		has_image = frappe.db.get_value("User", user, "user_image")
		if not has_image:
			return _(
				"No profile photo found for {0}. Upload a photo on the User form, then click Register Face for Login."
			).format(user)
		return _(
			"Face is not registered for {0}. Open that User record and click Register Face for Login."
		).format(user)

	return _(
		"No faces are registered yet. Sign in with password, open User, upload a profile photo, and click Register Face for Login."
	)


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=10, seconds=60 * 5)
def verify_and_login(descriptor, user=None):
	"""Verify a browser-generated face descriptor and log the user in."""
	parsed_descriptor = _parse_descriptor(descriptor)
	resolved_user = _resolve_user(user) if user else None

	if resolved_user and not frappe.db.get_value("User", resolved_user, "face_descriptor"):
		frappe.throw(_registration_hint(resolved_user), frappe.AuthenticationError)

	if not _get_candidate_users():
		frappe.throw(_registration_hint(), frappe.AuthenticationError)

	match, distance = _find_best_match(parsed_descriptor, resolved_user)

	if not match:
		message = _("Face not recognized. Try again or use password login.")
		if resolved_user:
			message = _(
				"Face not recognized for {0}. Re-register your face from the User form and try again."
			).format(resolved_user)
		elif distance:
			frappe.logger().debug({"face_login_best_distance": distance, "threshold": MATCH_THRESHOLD})
		frappe.throw(message, frappe.AuthenticationError)

	_login_user(match.name)
	return {
		"message": frappe.local.response.get("message"),
		"home_page": frappe.local.response.get("home_page"),
		"user": match.name,
	}


@frappe.whitelist()
def save_face_descriptor(descriptor, user=None, append=0):
	"""Store a face descriptor for the current or specified user."""
	parsed_descriptor = _parse_descriptor(descriptor)
	target_user = _resolve_user(user) if user else frappe.session.user

	if target_user == "Guest":
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	if target_user != frappe.session.user and not frappe.has_permission("User", "write", target_user):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	existing = _parse_stored_descriptors(
		frappe.db.get_value("User", target_user, "face_descriptor")
	)

	if int(append) and existing:
		# Keep up to 3 descriptors (photo + webcam samples) for better matching.
		descriptors = existing[:2] + [parsed_descriptor]
	else:
		descriptors = [parsed_descriptor]

	frappe.db.set_value(
		"User",
		target_user,
		"face_descriptor",
		json.dumps(descriptors if len(descriptors) > 1 else descriptors[0]),
	)
	frappe.db.commit()

	return {"ok": True, "user": target_user, "samples": len(descriptors)}


@frappe.whitelist(allow_guest=True)
def face_login_available():
	return bool(_get_candidate_users())


@frappe.whitelist(allow_guest=True)
def get_face_login_status(user=None):
	"""Tell the login page whether a user has registered face login."""
	resolved_user = _resolve_user(user) if user else None
	registered_users = _get_candidate_users()

	return {
		"any_registered": bool(registered_users),
		"user": resolved_user,
		"user_registered": bool(_get_candidate_users(resolved_user)) if resolved_user else False,
		"user_exists": bool(resolved_user and frappe.db.exists("User", resolved_user)),
		"has_profile_image": bool(
			resolved_user and frappe.db.get_value("User", resolved_user, "user_image")
		),
	}
