import json
import math

import frappe
from frappe import _
from frappe.apps import get_default_path
from frappe.auth import LoginManager
from frappe.rate_limiter import rate_limit
from frappe.utils import slug

DESCRIPTOR_LENGTH = 128
MATCH_THRESHOLD = 0.6


def _parse_descriptor(descriptor):
	if isinstance(descriptor, str):
		descriptor = json.loads(descriptor)

	if not isinstance(descriptor, (list, tuple)) or len(descriptor) != DESCRIPTOR_LENGTH:
		frappe.throw(_("Invalid face data."))

	return [float(value) for value in descriptor]


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
		fields=["name", "face_descriptor", "user_type", "default_workspace"],
	)


def _find_best_match(descriptor: list[float], user: str | None = None) -> dict | None:
	best_match = None
	best_distance = MATCH_THRESHOLD

	for candidate in _get_candidate_users(user):
		try:
			stored_descriptor = _parse_descriptor(candidate.face_descriptor)
		except Exception:
			continue

		distance = _euclidean_distance(descriptor, stored_descriptor)
		if distance < best_distance:
			best_distance = distance
			best_match = candidate

	return best_match


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


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=10, seconds=60 * 5)
def verify_and_login(descriptor, user=None):
	"""Verify a browser-generated face descriptor and log the user in."""
	parsed_descriptor = _parse_descriptor(descriptor)
	resolved_user = _resolve_user(user) if user else None
	match = _find_best_match(parsed_descriptor, resolved_user)

	if not match:
		frappe.throw(
			_("Face not recognized. Upload your profile photo and register your face first."),
			frappe.AuthenticationError,
		)

	_login_user(match.name)
	return {
		"message": frappe.local.response.get("message"),
		"home_page": frappe.local.response.get("home_page"),
		"user": match.name,
	}


@frappe.whitelist()
def save_face_descriptor(descriptor, user=None):
	"""Store a face descriptor for the current or specified user."""
	parsed_descriptor = _parse_descriptor(descriptor)
	target_user = _resolve_user(user) if user else frappe.session.user

	if target_user == "Guest":
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	if target_user != frappe.session.user and not frappe.has_permission("User", "write", target_user):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	frappe.db.set_value("User", target_user, "face_descriptor", json.dumps(parsed_descriptor))
	frappe.db.commit()

	return {"ok": True, "user": target_user}


@frappe.whitelist(allow_guest=True)
def face_login_available():
	return bool(_get_candidate_users())
