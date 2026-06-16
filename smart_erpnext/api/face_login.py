import json
import math

import frappe
from frappe import _
from frappe.apps import get_default_path
from frappe.auth import LoginManager
from frappe.rate_limiter import rate_limit
from frappe.utils import slug

DESCRIPTOR_LENGTH = 128
MATCH_THRESHOLD = 0.45
DUPLICATE_DESCRIPTOR_DISTANCE = 0.05


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


def _get_user_face_meta(user_name: str) -> dict | None:
	if not user_name or not frappe.db.exists("User", user_name):
		return None

	return frappe.db.get_value(
		"User",
		user_name,
		["name", "enabled", "user_image", "face_descriptor", "face_registered_image"],
		as_dict=True,
	)


def _has_active_face_login(user_name: str) -> bool:
	meta = _get_user_face_meta(user_name)
	if not meta or not meta.enabled:
		return False
	if not meta.user_image:
		return False
	if not meta.face_descriptor or not str(meta.face_descriptor).strip():
		return False
	return bool(_parse_stored_descriptors(meta.face_descriptor))


def _clear_face_login(user_name: str, commit: bool = False):
	frappe.db.set_value(
		"User",
		user_name,
		{"face_descriptor": None, "face_registered_image": None},
		update_modified=False,
	)
	if commit:
		frappe.db.commit()


def clear_stale_face_logins():
	"""Remove face login data when profile photo is missing or registration image changed."""
	users = frappe.get_all(
		"User",
		filters={"face_descriptor": ["is", "set"]},
		fields=["name", "user_image", "face_registered_image", "face_descriptor"],
	)

	for row in users:
		should_clear = False

		if not row.user_image:
			should_clear = True
		elif row.face_registered_image and row.user_image != row.face_registered_image:
			should_clear = True
		elif not _parse_stored_descriptors(row.face_descriptor):
			should_clear = True

		if should_clear:
			_clear_face_login(row.name)


def on_user_validate(doc, method=None):
	"""Invalidate face login when profile photo is removed or replaced."""
	if doc.is_new():
		return

	previous = frappe.db.get_value(
		"User",
		doc.name,
		["user_image", "face_registered_image"],
		as_dict=True,
	) or {}

	if not doc.user_image:
		doc.face_descriptor = None
		doc.face_registered_image = None
		return

	if doc.user_image != previous.get("user_image"):
		doc.face_descriptor = None
		doc.face_registered_image = None


def _get_candidate_users(user: str | None = None) -> list[dict]:
	if user:
		meta = _get_user_face_meta(user)
		if not meta or not _has_active_face_login(user):
			return []
		return [meta]

	users = frappe.get_all(
		"User",
		filters={"enabled": 1, "face_descriptor": ["is", "set"]},
		fields=["name", "face_descriptor", "user_image", "face_registered_image"],
	)
	return [row for row in users if _has_active_face_login(row.name)]


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


def _ensure_descriptor_not_used_by_other_user(descriptor: list[float], target_user: str):
	for candidate in _get_candidate_users():
		if candidate.name == target_user:
			continue

		distance = _descriptor_distance(descriptor, candidate.face_descriptor)
		if distance is not None and distance <= DUPLICATE_DESCRIPTOR_DISTANCE:
			frappe.throw(
				_(
					"This face is already registered for user {0}. Each user must register their own unique face."
				).format(candidate.name)
			)


def _find_best_match(
	descriptor: list[float], user: str | None = None, *, strict_user: bool = True
) -> tuple[dict | None, float | None]:
	if strict_user and not user:
		return None, None

	best_match = None
	best_distance = None
	match_distance = None

	for candidate in _get_candidate_users(user):
		distance = _descriptor_distance(descriptor, candidate.face_descriptor)
		if distance is None:
			continue

		if best_distance is None or distance < best_distance:
			best_distance = distance

		if distance <= MATCH_THRESHOLD and (match_distance is None or distance < match_distance):
			best_match = candidate
			match_distance = distance

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
		meta = _get_user_face_meta(user)
		if not meta:
			return _("User {0} was not found.").format(user)
		if not meta.user_image:
			return _(
				"Profile photo removed for {0}. Upload a new photo and register face login again."
			).format(user)
		return _(
			"Face login is not active for {0}. Open that User and click Register Face from Camera."
		).format(user)

	return _("No active face logins found. Register face login from the User form first.")


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=10, seconds=60 * 5)
def verify_and_login(descriptor, user=None):
	"""Verify a browser-generated face descriptor and log the user in."""
	parsed_descriptor = _parse_descriptor(descriptor)

	if not (user or "").strip():
		frappe.throw(
			_("Enter your email or username on the face login screen before scanning."),
			frappe.AuthenticationError,
		)

	resolved_user = _resolve_user(user)
	if not resolved_user:
		frappe.throw(_("User not found."), frappe.AuthenticationError)

	if not _has_active_face_login(resolved_user):
		frappe.throw(_registration_hint(resolved_user), frappe.AuthenticationError)

	match, distance = _find_best_match(parsed_descriptor, resolved_user, strict_user=True)

	if not match or match.name != resolved_user:
		message = _(
			"Face does not match {0}. Only the person who registered for this account can sign in."
		).format(resolved_user)
		if distance is not None:
			frappe.logger().info(
				{
					"face_login_rejected": resolved_user,
					"distance": round(distance, 4),
					"threshold": MATCH_THRESHOLD,
				}
			)
		frappe.throw(message, frappe.AuthenticationError)

	_login_user(resolved_user)
	return {
		"message": frappe.local.response.get("message"),
		"home_page": frappe.local.response.get("home_page"),
		"user": resolved_user,
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

	user_image = frappe.db.get_value("User", target_user, "user_image")
	if not user_image:
		frappe.throw(_("Upload and save a profile photo before registering face login."))

	_ensure_descriptor_not_used_by_other_user(parsed_descriptor, target_user)

	existing = _parse_stored_descriptors(
		frappe.db.get_value("User", target_user, "face_descriptor")
	)

	if int(append) and existing:
		descriptors = existing[:2] + [parsed_descriptor]
	else:
		descriptors = [parsed_descriptor]

	frappe.db.set_value(
		"User",
		target_user,
		{
			"face_descriptor": json.dumps(descriptors if len(descriptors) > 1 else descriptors[0]),
			"face_registered_image": user_image,
		},
	)
	frappe.db.commit()

	return {"ok": True, "user": target_user, "samples": len(descriptors)}


@frappe.whitelist()
def clear_face_descriptor(user=None):
	target_user = _resolve_user(user) if user else frappe.session.user

	if target_user == "Guest":
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	if target_user != frappe.session.user and not frappe.has_permission("User", "write", target_user):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	_clear_face_login(target_user, commit=True)
	return {"ok": True, "user": target_user}


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
		"user_registered": _has_active_face_login(resolved_user) if resolved_user else False,
		"user_exists": bool(resolved_user and frappe.db.exists("User", resolved_user)),
		"has_profile_image": bool(
			resolved_user and frappe.db.get_value("User", resolved_user, "user_image")
		),
	}
