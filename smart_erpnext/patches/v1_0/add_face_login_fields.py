import frappe

from smart_erpnext.install import _create_face_descriptor_field, _cleanup_face_login_data


def execute():
	_create_face_descriptor_field()
	_cleanup_face_login_data()
	frappe.db.commit()
