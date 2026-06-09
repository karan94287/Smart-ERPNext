import math

import frappe
from frappe import _
from frappe.utils import flt

DEFAULT_CAPACITY = 1000
MIN_HEIGHT = 1.2
GROUP_HEIGHT = 2.0
VALID_SHAPES = {"cube", "cylinder", "sphere", "pyramid"}

DISPLAY_MODES = {
	"all": "All Locations",
	"groups": "Groups Only",
	"storage": "Storage Locations Only",
}

SCOPE_MODES = {
	"company": "Entire Company",
	"under_warehouse": "Under Selected Warehouse",
	"direct_children": "Direct Children Only",
}


def _get_warehouse_3d_meta(warehouse_name: str) -> dict:
	meta = frappe.db.get_value(
		"Warehouse",
		warehouse_name,
		[
			"warehouse_capacity",
			"warehouse_3d_shape",
			"warehouse_3d_pos_x",
			"warehouse_3d_pos_z",
			"warehouse_3d_scale",
		],
		as_dict=True,
	) or {}

	shape = (meta.get("warehouse_3d_shape") or "cube").lower()
	if shape == "pyramid":
		shape = "pyramid"
	elif shape not in VALID_SHAPES:
		shape = "cube"

	return {
		"capacity": flt(meta.get("warehouse_capacity")),
		"shape": shape,
		"pos_x": meta.get("warehouse_3d_pos_x"),
		"pos_z": meta.get("warehouse_3d_pos_z"),
		"scale": flt(meta.get("warehouse_3d_scale")) or 1.0,
	}


def _custom_position(meta: dict) -> tuple[float, float] | None:
	"""Return manual X/Z only when explicitly set (not empty defaults)."""
	px, pz = meta.get("pos_x"), meta.get("pos_z")
	if px is None or pz is None:
		return None
	px, pz = flt(px), flt(pz)
	if px == 0 and pz == 0:
		return None
	return px, pz


def _get_capacity(warehouse_name: str) -> float:
	capacity = _get_warehouse_3d_meta(warehouse_name)["capacity"]
	return capacity if capacity > 0 else DEFAULT_CAPACITY


def _utilization_status(utilization: float, actual_qty: float) -> str:
	if actual_qty < 0:
		return "negative"
	if utilization >= 0.9:
		return "red"
	if utilization >= 0.7:
		return "yellow"
	if actual_qty <= 0:
		return "empty"
	return "green"


def _get_stock_summary(warehouse_names: list[str]) -> dict:
	if not warehouse_names:
		return {}

	rows = frappe.db.sql(
		"""
		SELECT
			warehouse,
			SUM(actual_qty) AS actual_qty,
			SUM(reserved_qty) AS reserved_qty,
			SUM(projected_qty) AS projected_qty,
			COUNT(DISTINCT item_code) AS items_count
		FROM `tabBin`
		WHERE warehouse IN %(warehouses)s
		GROUP BY warehouse
		""",
		{"warehouses": warehouse_names},
		as_dict=True,
	)

	return {row.warehouse: row for row in rows}


def _fetch_warehouses(company, warehouse, scope, display_mode):
	base_filters = {"company": company, "disabled": 0}

	if scope == "direct_children":
		if not warehouse:
			frappe.throw(_("Select a warehouse for Direct Children scope."))
		base_filters["parent_warehouse"] = warehouse
	elif scope == "under_warehouse":
		if not warehouse:
			frappe.throw(_("Select a warehouse for Under Selected Warehouse scope."))
		root = frappe.get_doc("Warehouse", warehouse)
		if root.is_group:
			base_filters["lft"] = [">=", root.lft]
			base_filters["rgt"] = ["<=", root.rgt]
		else:
			# Leaf selected: show this location + siblings under same parent
			parent = root.parent_warehouse
			if parent:
				siblings = frappe.get_all(
					"Warehouse",
					filters={"parent_warehouse": parent, "disabled": 0},
					pluck="name",
				)
				base_filters["name"] = ["in", siblings + [warehouse]]
			else:
				base_filters["name"] = warehouse

	warehouses = frappe.get_all(
		"Warehouse",
		filters=base_filters,
		fields=["name", "warehouse_name", "parent_warehouse", "is_group", "lft", "rgt"],
		order_by="lft asc",
	)

	if display_mode == "groups":
		warehouses = [row for row in warehouses if row.is_group]
	elif display_mode == "storage":
		warehouses = [row for row in warehouses if not row.is_group]

	return warehouses


def _layout_tree(warehouses: list) -> list[dict]:
	"""Layout by warehouse tree — children spread around parent."""
	wh_map = {row.name: row for row in warehouses}
	children_map: dict[str | None, list] = {}

	for wh in warehouses:
		parent = wh.parent_warehouse if wh.parent_warehouse in wh_map else None
		children_map.setdefault(parent, []).append(wh)

	for siblings in children_map.values():
		siblings.sort(key=lambda row: row.lft)

	nodes = []
	spacing = 5.0

	def walk(parent_name, depth, angle_start, angle_span, radius):
		siblings = children_map.get(parent_name, [])
		if not siblings:
			return

		count = len(siblings)
		for idx, wh in enumerate(siblings):
			meta = _get_warehouse_3d_meta(wh.name)
			custom = _custom_position(meta)

			if custom:
				x, z = custom
			elif parent_name is None:
				angle = (idx - (count - 1) / 2) * 0.8
				x = math.sin(angle) * spacing * (depth + 1)
				z = math.cos(angle) * spacing * (depth + 1)
			else:
				t = (idx + 0.5) / count
				angle = angle_start + angle_span * t
				r = radius + depth * spacing * 0.8
				x = math.sin(angle) * r
				z = math.cos(angle) * r

			nodes.append({"warehouse": wh, "x": x, "z": z, "scale": meta["scale"]})
			walk(wh.name, depth + 1, angle_start, angle_span, radius + spacing * 0.5)

	roots = children_map.get(None, [])
	if not roots and len(warehouses) == 1:
		wh = warehouses[0]
		meta = _get_warehouse_3d_meta(wh.name)
		nodes.append({"warehouse": wh, "x": 0, "z": 0, "scale": meta["scale"]})
	elif roots:
		for ridx, root in enumerate(roots):
			meta = _get_warehouse_3d_meta(root.name)
			custom = _custom_position(meta)
			if custom:
				x, z = custom
			else:
				x = (ridx - (len(roots) - 1) / 2) * spacing * 2
				z = 0
			nodes.append({"warehouse": root, "x": x, "z": z, "scale": meta["scale"]})
			walk(root.name, 0, -math.pi / 3, math.pi * 2 / 3, spacing)

	if not nodes:
		nodes = _layout_grid(warehouses)

	return nodes


def _layout_grid(warehouses: list, spacing: float | None = None) -> list[dict]:
	warehouses = sorted(warehouses, key=lambda row: row.lft)
	count = len(warehouses)
	cols = max(1, math.ceil(math.sqrt(count)))
	if spacing is None:
		spacing = max(4.5, min(7.0, 36 / cols))

	nodes = []
	for index, wh in enumerate(warehouses):
		meta = _get_warehouse_3d_meta(wh.name)
		row, col = divmod(index, cols)
		custom = _custom_position(meta)

		if custom:
			x, z = custom
		else:
			x = (col - (cols - 1) / 2) * spacing
			z = row * spacing

		nodes.append({"warehouse": wh, "x": x, "z": z, "scale": meta["scale"]})

	return nodes


def _layout_nodes(warehouses: list, layout_mode: str = "grid") -> list[dict]:
	if layout_mode == "tree":
		return _layout_tree(warehouses)
	return _layout_grid(warehouses)


def _node_height(is_group: bool, actual_qty: float, capacity: float) -> float:
	if is_group:
		return GROUP_HEIGHT

	fill_ratio = max(flt(actual_qty), 0) / capacity if capacity else 0
	fill_ratio = min(fill_ratio, 1.0)
	return max(MIN_HEIGHT, MIN_HEIGHT + fill_ratio * 3.0)


@frappe.whitelist()
def get_warehouse_3d_data(
	warehouse=None,
	company=None,
	default_shape="cube",
	display_mode="all",
	scope="company",
	layout_mode="grid",
):
	default_shape = (default_shape or "cube").lower()
	if default_shape not in VALID_SHAPES:
		default_shape = "cube"

	display_mode = (display_mode or "all").lower()
	if display_mode not in DISPLAY_MODES:
		display_mode = "all"

	scope = (scope or "company").lower()
	if scope not in SCOPE_MODES:
		scope = "company"

	layout_mode = (layout_mode or "grid").lower()
	if layout_mode not in ("grid", "tree"):
		layout_mode = "grid"

	company = company or frappe.defaults.get_user_default("Company")
	if not company:
		frappe.throw(_("Please set a default Company."))

	warehouses = _fetch_warehouses(company, warehouse, scope, display_mode)

	if not warehouses:
		return {
			"company": company,
			"root": warehouse,
			"nodes": [],
			"node_count": 0,
			"shapes": sorted(VALID_SHAPES),
			"display_modes": DISPLAY_MODES,
			"scope_modes": SCOPE_MODES,
			"filter_summary": _("No warehouses match the current filters."),
		}

	layout = _layout_nodes(warehouses, layout_mode)
	warehouse_names = [row.name for row in warehouses]
	stock_map = _get_stock_summary(warehouse_names)

	nodes = []
	for entry in layout:
		wh = entry["warehouse"]
		meta = _get_warehouse_3d_meta(wh.name)
		stock = stock_map.get(wh.name, {})
		actual_qty = flt(stock.get("actual_qty"))
		reserved_qty = flt(stock.get("reserved_qty"))
		capacity = _get_capacity(wh.name) if not wh.is_group else 0
		scale = flt(entry.get("scale")) or 1.0

		if wh.is_group:
			utilization_pct = 0
			status = "group"
		else:
			utilization_pct = (actual_qty / capacity * 100) if capacity else 0
			utilization_ratio = max(flt(actual_qty), 0) / capacity if capacity else 0
			status = _utilization_status(utilization_ratio, actual_qty)

		base_height = _node_height(wh.is_group, actual_qty, capacity)
		base_width = (2.4 if wh.is_group else 2.0) * scale
		shape = meta["shape"] if meta["shape"] in VALID_SHAPES else default_shape

		nodes.append(
			{
				"name": wh.name,
				"label": wh.warehouse_name,
				"parent": wh.parent_warehouse,
				"is_group": wh.is_group,
				"shape": shape,
				"position": {"x": entry["x"], "y": base_height / 2, "z": entry["z"]},
				"size": {
					"width": base_width,
					"height": base_height,
					"depth": base_width,
					"radius": base_width / 2,
				},
				"actual_qty": actual_qty,
				"reserved_qty": reserved_qty,
				"projected_qty": flt(stock.get("projected_qty")),
				"items_count": int(stock.get("items_count") or 0),
				"capacity": capacity,
				"utilization": round(utilization_pct, 1),
				"status": status,
			}
		)

	group_count = sum(1 for n in nodes if n["is_group"])
	storage_count = len(nodes) - group_count

	return {
		"company": company,
		"root": warehouse or "",
		"nodes": nodes,
		"node_count": len(nodes),
		"group_count": group_count,
		"storage_count": storage_count,
		"shapes": sorted(VALID_SHAPES),
		"display_modes": DISPLAY_MODES,
		"scope_modes": SCOPE_MODES,
		"filter_summary": _filter_summary(display_mode, scope, warehouse, len(nodes)),
	}


def _filter_summary(display_mode, scope, warehouse, count):
	parts = [DISPLAY_MODES.get(display_mode, display_mode)]
	parts.append(SCOPE_MODES.get(scope, scope))
	if warehouse:
		parts.append(warehouse)
	return _("Showing {0} locations · {1} · {2}").format(
		count, parts[0], parts[1] if not warehouse else f"{parts[1]} ({warehouse})"
	)


@frappe.whitelist()
def find_item_location(item_code, company=None):
	item_code = (item_code or "").strip()
	if not item_code:
		frappe.throw(_("Item Code is required."))

	company = company or frappe.defaults.get_user_default("Company")
	filters = {"item_code": item_code, "actual_qty": ["!=", 0]}
	if company:
		warehouses = frappe.get_all("Warehouse", filters={"company": company}, pluck="name")
		if warehouses:
			filters["warehouse"] = ["in", warehouses]

	bins = frappe.get_all(
		"Bin",
		filters=filters,
		fields=["warehouse", "actual_qty", "reserved_qty"],
		order_by="actual_qty desc",
	)

	return {"item_code": item_code, "locations": bins}


@frappe.whitelist()
def get_warehouse_options(company=None):
	company = company or frappe.defaults.get_user_default("Company")
	filters = {"disabled": 0}
	if company:
		filters["company"] = company

	return frappe.get_all(
		"Warehouse",
		filters=filters,
		fields=["name", "warehouse_name", "is_group", "parent_warehouse"],
		order_by="lft asc",
	)
