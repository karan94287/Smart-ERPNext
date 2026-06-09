frappe.pages["warehouse-3d"].on_page_load = function (wrapper) {
	frappe.require(
		[
			"/assets/smart_erpnext/lib/three.min.js",
			"/assets/smart_erpnext/lib/OrbitControls.js",
			"/assets/smart_erpnext/js/warehouse_3d_scene.js",
		],
		() => {
			const page = frappe.ui.make_app_page({
				parent: wrapper,
				title: __("3D Warehouse"),
				single_column: true,
			});

			smart_erpnext.warehouse_3d_page = new smart_erpnext.Warehouse3DPage(
				$(wrapper).find(".layout-main-section"),
				page
			);
		}
	);
};

frappe.provide("smart_erpnext");

smart_erpnext.Warehouse3DPage = class Warehouse3DPage {
	constructor(wrapper, page) {
		this.wrapper = wrapper;
		this.page = page;
		this.scene = null;
		this.setup_page();
		this.make_layout();
		this.load_data();
	}

	setup_page() {
		this.page.add_menu_item(__("Refresh"), () => this.load_data());
		this.page.set_primary_action(__("Refresh"), () => this.load_data());

		this.company_field = this.page.add_field({
			fieldtype: "Link",
			fieldname: "company",
			label: __("Company"),
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			change: () => {
				this.warehouse_field.set_value("");
				this.load_data();
			},
		});

		this.display_mode_field = this.page.add_field({
			fieldtype: "Select",
			fieldname: "display_mode",
			label: __("Show"),
			options: [
				{ value: "all", label: __("All Locations") },
				{ value: "groups", label: __("Groups Only") },
				{ value: "storage", label: __("Storage Only") },
			],
			default: "all",
			change: () => this.load_data(),
		});

		this.scope_field = this.page.add_field({
			fieldtype: "Select",
			fieldname: "scope",
			label: __("Scope"),
			options: [
				{ value: "company", label: __("Entire Company") },
				{ value: "under_warehouse", label: __("Under Warehouse") },
				{ value: "direct_children", label: __("Direct Children Only") },
			],
			default: "company",
			change: () => {
				this._update_warehouse_field_hint();
				this.load_data();
			},
		});

		this.warehouse_field = this.page.add_field({
			fieldtype: "Link",
			fieldname: "warehouse",
			label: __("Warehouse"),
			options: "Warehouse",
			description: __("Optional — leave empty to show every warehouse in the company."),
			get_query: () => ({
				filters: {
					company: this.company_field.get_value(),
				},
			}),
			change: () => this.load_data(),
		});

		this.layout_mode_field = this.page.add_field({
			fieldtype: "Select",
			fieldname: "layout_mode",
			label: __("Layout"),
			options: [
				{ value: "grid", label: __("Grid") },
				{ value: "tree", label: __("Tree by Group") },
			],
			default: "grid",
			change: () => this.load_data(),
		});

		this.item_field = this.page.add_field({
			fieldtype: "Link",
			fieldname: "item_code",
			label: __("Find Item"),
			options: "Item",
		});

		this.page.add_inner_button(__("Find Item"), () => this.search_item());
		this._update_warehouse_field_hint();
	}

	_update_warehouse_field_hint() {
		const scope = this.scope_field.get_value() || "company";
		const $field = this.warehouse_field?.$wrapper;

		if (scope === "company") {
			this.warehouse_field.df.reqd = 0;
			this.warehouse_field.df.description = __(
				"Optional — leave empty to show every warehouse in the company."
			);
		} else {
			this.warehouse_field.df.reqd = 1;
			this.warehouse_field.df.description = __(
				"Required for this scope — pick a group or location to filter under."
			);
		}

		if ($field) {
			$field.find(".help-box").text(this.warehouse_field.df.description || "");
		}
	}

	make_layout() {
		this.wrapper.html(`
			<div class="warehouse-3d-summary-bar">
				<span class="warehouse-3d-summary-pill locations-pill">
					${__("Locations")}: <strong>0</strong>
				</span>
				<span class="warehouse-3d-summary-pill groups-pill hidden">
					${__("Groups")}: <strong>0</strong>
				</span>
				<span class="warehouse-3d-summary-pill storage-pill hidden">
					${__("Storage")}: <strong>0</strong>
				</span>
				<span class="warehouse-3d-summary-pill filter-summary-pill">
					${__("Loading...")}
				</span>
			</div>
			<div class="warehouse-3d-page">
				<div class="warehouse-3d-view-col"></div>
				<div class="warehouse-3d-sidebar">
					<div class="warehouse-3d-details panel panel-default">
						<div class="panel-heading">${__("Location Details")}</div>
						<div class="panel-body details-body">
							<p class="details-empty">${__(
								"Click a warehouse block in the 3D view to inspect stock, capacity, and utilization."
							)}</p>
						</div>
					</div>
				</div>
			</div>
		`);

		this.view_col = this.wrapper.find(".warehouse-3d-view-col");
		this.details_body = this.wrapper.find(".details-body");
		this.locations_pill = this.wrapper.find(".locations-pill strong");
		this.groups_pill = this.wrapper.find(".groups-pill");
		this.storage_pill = this.wrapper.find(".storage-pill");
		this.filter_summary_pill = this.wrapper.find(".filter-summary-pill");

		this.scene = new smart_erpnext.warehouse_3d.WarehouseScene({
			wrapper: this.view_col,
			on_select: (node) => this.render_details(node),
		});

		this.scene.on_shape_change = (shape) => this.load_data(shape);
		this.default_shape = "cube";
	}

	load_data(default_shape) {
		if (default_shape) {
			this.default_shape = default_shape;
			this.scene.set_default_shape(default_shape);
		}

		const scope = this.scope_field.get_value() || "company";
		const warehouse = this.warehouse_field.get_value();

		if (scope !== "company" && !warehouse) {
			this._render_empty_filter_state(
				__("Select a warehouse for this scope, or switch Scope to Entire Company.")
			);
			return;
		}

		frappe.call({
			method: "smart_erpnext.api.warehouse_3d.get_warehouse_3d_data",
			args: {
				warehouse,
				company: this.company_field.get_value(),
				default_shape: this.default_shape || "cube",
				display_mode: this.display_mode_field.get_value() || "all",
				scope,
				layout_mode: this.layout_mode_field.get_value() || "grid",
			},
			freeze: true,
			freeze_message: __("Loading 3D warehouse..."),
			callback: (r) => {
				const data = r.message || {};
				this.scene.render_nodes(data.nodes || []);
				this._update_summary(data);

				if (!data.nodes?.length) {
					this._render_empty_filter_state(
						data.filter_summary ||
							__(
								"No warehouses match these filters. Try Show: All Locations, Scope: Entire Company, and leave Warehouse empty."
							)
					);
				}
			},
		});
	}

	_update_summary(data) {
		const count = data.node_count || 0;
		this.locations_pill.text(count);
		this.filter_summary_pill.text(data.filter_summary || "");

		if (data.group_count != null) {
			this.groups_pill.removeClass("hidden").find("strong").text(data.group_count);
			this.storage_pill.removeClass("hidden").find("strong").text(data.storage_count || 0);
		}
	}

	_render_empty_filter_state(message) {
		this.scene.render_nodes([]);
		this.locations_pill.text(0);
		this.groups_pill.addClass("hidden");
		this.storage_pill.addClass("hidden");
		this.filter_summary_pill.text(message);
		this.details_body.html(`<p class="details-empty">${frappe.utils.escape_html(message)}</p>`);
	}

	search_item() {
		const item_code = this.item_field.get_value();
		if (!item_code) {
			frappe.msgprint(__("Select an item to find."));
			return;
		}

		frappe.call({
			method: "smart_erpnext.api.warehouse_3d.find_item_location",
			args: {
				item_code,
				company: this.company_field.get_value(),
			},
			callback: (r) => {
				const locations = r.message?.locations || [];
				if (!locations.length) {
					frappe.msgprint({
						title: __("Not Found"),
						message: __("No stock found for {0}", [item_code]),
						indicator: "orange",
					});
					return;
				}

				this.scene.highlight_warehouse(locations[0].warehouse);
				this.render_item_locations(item_code, locations);
			},
		});
	}

	render_details(node) {
		if (node.is_group) {
			this.details_body.html(`
				<h3 class="details-title">${frappe.utils.escape_html(node.label)}</h3>
				<p class="details-subtitle">${__("Group warehouse")}</p>
				<span class="warehouse-3d-status-badge group">${__("group")}</span>
			`);
			return;
		}

		this.details_body.html(`
			<h3 class="details-title">${frappe.utils.escape_html(node.label)}</h3>
			<p class="details-subtitle">${frappe.utils.escape_html(node.name)}</p>
			<div class="warehouse-3d-metrics">
				<div class="warehouse-3d-metric">
					<span class="metric-label">${__("Actual Qty")}</span>
					<span class="metric-value">${node.actual_qty}</span>
				</div>
				<div class="warehouse-3d-metric">
					<span class="metric-label">${__("Reserved")}</span>
					<span class="metric-value">${node.reserved_qty}</span>
				</div>
				<div class="warehouse-3d-metric">
					<span class="metric-label">${__("Capacity")}</span>
					<span class="metric-value">${node.capacity}</span>
				</div>
				<div class="warehouse-3d-metric">
					<span class="metric-label">${__("Items")}</span>
					<span class="metric-value">${node.items_count}</span>
				</div>
				<div class="warehouse-3d-metric wide">
					<span class="metric-label">${__("Utilization")}</span>
					<span class="metric-value">${node.utilization}%</span>
				</div>
			</div>
			<span class="warehouse-3d-status-badge ${node.status}">${__(node.status)}</span>
			<p class="details-subtitle" style="margin-top:14px">${__(
				"Shape"
			)}: ${__(node.shape || "cube")} · ${__(
				"Customize in Warehouse form → 3D Warehouse View"
			)}</p>
		`);
	}

	render_item_locations(item_code, locations) {
		const rows = locations
			.map(
				(row) =>
					`<li><strong>${frappe.utils.escape_html(row.warehouse)}</strong> — ${row.actual_qty}</li>`
			)
			.join("");

		this.details_body.html(`
			<h3 class="details-title">${frappe.utils.escape_html(item_code)}</h3>
			<p class="details-subtitle">${__("Found in {0} location(s)", [locations.length])}</p>
			<ul class="item-location-list">${rows}</ul>
		`);
	}
};
