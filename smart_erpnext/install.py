import frappe


def after_install():
	_create_face_descriptor_field()


def _create_face_descriptor_field():
	if frappe.db.exists("Custom Field", {"dt": "User", "fieldname": "face_descriptor"}):
		return

	frappe.get_doc(
		{
			"doctype": "Custom Field",
			"dt": "User",
			"fieldname": "face_descriptor",
			"label": "Face Descriptor",
			"fieldtype": "Long Text",
			"hidden": 1,
			"read_only": 1,
			"insert_after": "user_image",
			"description": "Auto-generated face descriptor used for face login.",
		}
	).insert(ignore_permissions=True)
