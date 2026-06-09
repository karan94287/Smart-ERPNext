import frappe


def after_install():
	_create_face_descriptor_field()
	_create_warehouse_3d_fields()


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


def _create_warehouse_3d_fields():
	fields = [
		{
			"fieldname": "warehouse_3d_section",
			"label": "3D Warehouse View",
			"fieldtype": "Section Break",
			"insert_after": "warehouse_type",
			"collapsible": 1,
		},
		{
			"fieldname": "warehouse_3d_shape",
			"label": "3D Shape",
			"fieldtype": "Select",
			"options": "Cube\nCylinder\nSphere\nPyramid",
			"default": "Cube",
			"insert_after": "warehouse_3d_section",
			"description": "Shape used in the 3D warehouse view.",
		},
		{
			"fieldname": "warehouse_capacity",
			"label": "Warehouse Capacity",
			"fieldtype": "Float",
			"insert_after": "warehouse_3d_shape",
			"description": "Maximum stock capacity for utilization in the 3D view.",
			"default": "1000",
		},
		{
			"fieldname": "warehouse_3d_pos_x",
			"label": "3D Position X",
			"fieldtype": "Float",
			"insert_after": "warehouse_capacity",
			"description": "Optional manual X position in the 3D layout.",
		},
		{
			"fieldname": "warehouse_3d_pos_z",
			"label": "3D Position Z",
			"fieldtype": "Float",
			"insert_after": "warehouse_3d_pos_x",
			"description": "Optional manual Z position in the 3D layout.",
		},
		{
			"fieldname": "warehouse_3d_scale",
			"label": "3D Scale",
			"fieldtype": "Float",
			"insert_after": "warehouse_3d_pos_z",
			"default": "1",
			"description": "Size multiplier for this warehouse in the 3D view.",
		},
	]

	for field in fields:
		if frappe.db.exists("Custom Field", {"dt": "Warehouse", "fieldname": field["fieldname"]}):
			continue
		frappe.get_doc({"doctype": "Custom Field", "dt": "Warehouse", **field}).insert(
			ignore_permissions=True
		)
