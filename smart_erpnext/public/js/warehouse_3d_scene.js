frappe.provide("smart_erpnext.warehouse_3d");

smart_erpnext.warehouse_3d.STATUS_COLORS = {
	green: 0x4caf50,
	yellow: 0xffc107,
	red: 0xf44336,
	negative: 0xff5722,
	group: 0x607d8b,
	empty: 0xb0bec5,
	highlight: 0x2196f3,
};

smart_erpnext.warehouse_3d.WarehouseScene = class WarehouseScene {
	constructor({ wrapper, on_select }) {
		this.wrapper = wrapper;
		this.on_select = on_select;
		this.nodes = [];
		this.meshes = {};
		this.auto_rotate = false;
		this._fly_animation = null;
		this._highlight_mesh = null;
		this.default_shape = "cube";

		this._build_dom();
		this._init_three();
		this._bind_events();
		this._animate();
	}

	set_default_shape(shape) {
		this.default_shape = shape || "cube";
	}

	_build_dom() {
		this.wrapper.html(`
			<div class="warehouse-3d-root">
				<div class="warehouse-3d-toolbar">
					<div class="warehouse-3d-toolbar-row primary-row">
						<div class="toolbar-group views-group">
							<span class="toolbar-title">${__("View")}</span>
							<button type="button" class="btn btn-default btn-xs btn-view active" data-view="perspective">${__(
								"3D"
							)}</button>
							<button type="button" class="btn btn-default btn-xs btn-view" data-view="top">${__(
								"Top"
							)}</button>
							<button type="button" class="btn btn-default btn-xs btn-view" data-view="front">${__(
								"Front"
							)}</button>
							<button type="button" class="btn btn-default btn-xs btn-view" data-view="side">${__(
								"Side"
							)}</button>
						</div>
						<div class="toolbar-group">
							<button type="button" class="btn btn-default btn-xs btn-auto-rotate">${__(
								"Auto Rotate"
							)}</button>
							<button type="button" class="btn btn-default btn-xs btn-reset-view">${__(
								"Reset"
							)}</button>
						</div>
					</div>
					<div class="warehouse-3d-toolbar-row">
						<div class="toolbar-group shape-selector-group">
							<label class="shape-label">${__("Default Shape")}</label>
							<select class="form-control input-xs default-shape-select">
								<option value="cube">${__("Cube")}</option>
								<option value="cylinder">${__("Cylinder")}</option>
								<option value="sphere">${__("Sphere")}</option>
								<option value="pyramid">${__("Pyramid")}</option>
							</select>
						</div>
						<div class="toolbar-legend">
							<span class="legend-item"><i class="dot green"></i>${__("Available")}</span>
							<span class="legend-item"><i class="dot yellow"></i>${__("Nearly Full")}</span>
							<span class="legend-item"><i class="dot red"></i>${__("Full")}</span>
							<span class="legend-item"><i class="dot negative"></i>${__("Negative")}</span>
						</div>
					</div>
				</div>
				<div class="warehouse-3d-canvas-wrap"></div>
				<div class="warehouse-3d-hint">${__(
					"Drag to rotate · Scroll to zoom · Click a location to inspect"
				)}</div>
			</div>
		`);

		this.canvas_wrap = this.wrapper.find(".warehouse-3d-canvas-wrap")[0];
		this.shape_select = this.wrapper.find(".default-shape-select");
	}

	_init_three() {
		const width = this.canvas_wrap.clientWidth || 900;
		const height = this.canvas_wrap.clientHeight || 560;

		this.scene = new THREE.Scene();
		this.scene.background = null;
		this.scene.fog = new THREE.FogExp2(0x0b1020, 0.012);

		this.camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 500);
		this.camera.position.set(14, 12, 18);

		this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
		this.renderer.setClearColor(0x000000, 0);
		this.renderer.setSize(width, height);
		this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
		this.renderer.shadowMap.enabled = true;
		this.canvas_wrap.appendChild(this.renderer.domElement);

		this._create_environment();

		this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
		this.controls.enableDamping = true;
		this.controls.dampingFactor = 0.08;
		this.controls.maxPolarAngle = Math.PI / 2.05;
		this.controls.minDistance = 4;
		this.controls.maxDistance = 80;
		this.controls.target.set(0, 1.5, 0);

		this._default_camera = {
			position: this.camera.position.clone(),
			target: this.controls.target.clone(),
		};

		this.raycaster = new THREE.Raycaster();
		this.pointer = new THREE.Vector2();
	}

	_create_environment() {
		// Starfield
		const star_count = 800;
		const star_geo = new THREE.BufferGeometry();
		const positions = new Float32Array(star_count * 3);
		for (let i = 0; i < star_count; i++) {
			positions[i * 3] = (Math.random() - 0.5) * 200;
			positions[i * 3 + 1] = Math.random() * 80 + 5;
			positions[i * 3 + 2] = (Math.random() - 0.5) * 200;
		}
		star_geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
		const stars = new THREE.Points(
			star_geo,
			new THREE.PointsMaterial({ color: 0xa5b4fc, size: 0.35, transparent: true, opacity: 0.85 })
		);
		this.scene.add(stars);
		this._stars = stars;

		// Floor glow ring
		const ring = new THREE.Mesh(
			new THREE.RingGeometry(18, 22, 64),
			new THREE.MeshBasicMaterial({
				color: 0x3b82f6,
				transparent: true,
				opacity: 0.15,
				side: THREE.DoubleSide,
			})
		);
		ring.rotation.x = -Math.PI / 2;
		ring.position.y = 0.02;
		this.scene.add(ring);

		const ambient = new THREE.AmbientLight(0x404080, 0.6);
		const key = new THREE.DirectionalLight(0xffffff, 1.1);
		key.position.set(14, 28, 14);
		key.castShadow = true;
		const fill = new THREE.DirectionalLight(0x6366f1, 0.45);
		fill.position.set(-12, 10, -10);
		const rim = new THREE.DirectionalLight(0x22d3ee, 0.25);
		rim.position.set(0, 8, -16);
		const hemi = new THREE.HemisphereLight(0x818cf8, 0x0f172a, 0.5);
		this.scene.add(ambient, key, fill, rim, hemi);

		const floor = new THREE.Mesh(
			new THREE.CircleGeometry(28, 64),
			new THREE.MeshStandardMaterial({
				color: 0x1e293b,
				roughness: 0.85,
				metalness: 0.35,
				transparent: true,
				opacity: 0.92,
			})
		);
		floor.rotation.x = -Math.PI / 2;
		floor.receiveShadow = true;
		this.scene.add(floor);

		const grid = new THREE.GridHelper(56, 28, 0x3b82f6, 0x1e3a5f);
		grid.material.opacity = 0.35;
		grid.material.transparent = true;
		this.scene.add(grid);
	}

	_bind_events() {
		this.wrapper.find(".btn-view").on("click", (event) => {
			this.wrapper.find(".btn-view").removeClass("active");
			$(event.currentTarget).addClass("active");
			this.snap_view($(event.currentTarget).data("view"));
		});

		this.wrapper.find(".btn-auto-rotate").on("click", (event) => {
			this.auto_rotate = !this.auto_rotate;
			$(event.currentTarget).toggleClass("btn-primary", this.auto_rotate);
		});

		this.wrapper.find(".btn-reset-view").on("click", () => {
			this.fly_to(this._default_camera.position, this._default_camera.target);
		});

		this.shape_select.on("change", () => {
			this.default_shape = this.shape_select.val();
			if (this.on_shape_change) {
				this.on_shape_change(this.default_shape);
			}
		});

		this.renderer.domElement.addEventListener("click", (event) => this._on_click(event));
		this._resize_handler = () => this._on_resize();
		window.addEventListener("resize", this._resize_handler);
	}

	_on_resize() {
		const width = this.canvas_wrap.clientWidth;
		const height = this.canvas_wrap.clientHeight || 560;
		if (!width) return;
		this.camera.aspect = width / height;
		this.camera.updateProjectionMatrix();
		this.renderer.setSize(width, height);
	}

	_on_click(event) {
		const rect = this.renderer.domElement.getBoundingClientRect();
		this.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
		this.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

		this.raycaster.setFromCamera(this.pointer, this.camera);
		const hits = this.raycaster.intersectObjects(Object.values(this.meshes), true);

		if (!hits.length) {
			return;
		}

		let target = hits[0].object;
		while (target && !target.userData.node) {
			target = target.parent;
		}

		const node = target?.userData?.node;
		if (!node) {
			return;
		}

		this.focus_on_node(node);
		if (this.on_select) {
			this.on_select(node);
		}
	}

	_clear_scene_nodes() {
		Object.values(this.meshes).forEach((mesh) => {
			this.scene.remove(mesh);
			mesh.traverse((child) => {
				if (child.geometry) child.geometry.dispose();
				if (child.material) child.material.dispose();
			});
		});
		this.meshes = {};
		if (this._highlight_mesh) {
			this.scene.remove(this._highlight_mesh);
			this._highlight_mesh.geometry.dispose();
			this._highlight_mesh.material.dispose();
			this._highlight_mesh = null;
		}
	}

	_create_geometry(node) {
		const shape = (node.shape || this.default_shape || "cube").toLowerCase();
		const w = Math.max(node.size.width, 0.8);
		const h = Math.max(node.size.height, 0.8);
		const d = Math.max(node.size.depth || w, 0.8);
		const radius = Math.max(node.size.radius || w / 2, 0.5);

		switch (shape) {
			case "cylinder":
				return new THREE.CylinderGeometry(radius, radius, h, 24);
			case "sphere":
				return new THREE.SphereGeometry(radius, 24, 24);
			case "pyramid":
				return new THREE.ConeGeometry(radius, h, 4);
			default:
				return new THREE.BoxGeometry(w, h, d);
		}
	}

	_create_material(node) {
		const color =
			smart_erpnext.warehouse_3d.STATUS_COLORS[node.status] ||
			smart_erpnext.warehouse_3d.STATUS_COLORS.empty;

		return new THREE.MeshStandardMaterial({
			color,
			roughness: 0.35,
			metalness: 0.18,
			transparent: node.is_group,
			opacity: node.is_group ? 0.72 : 1,
			emissive: color,
			emissiveIntensity: node.is_group ? 0.05 : 0.12,
		});
	}

	_create_rack_group(node) {
		const group = new THREE.Group();
		group.userData.node = node;

		const pad = new THREE.Mesh(
			new THREE.CylinderGeometry(
				Math.max(node.size.width, 1.2) * 0.65,
				Math.max(node.size.width, 1.2) * 0.65,
				0.12,
				32
			),
			new THREE.MeshStandardMaterial({ color: 0x374151, roughness: 0.8, metalness: 0.2 })
		);
		pad.position.y = 0.06;
		pad.receiveShadow = true;
		group.add(pad);

		const geometry = this._create_geometry(node);
		const material = this._create_material(node);
		const mesh = new THREE.Mesh(geometry, material);
		mesh.position.y = Math.max(node.size.height, 0.8) / 2 + 0.12;
		mesh.castShadow = true;
		mesh.receiveShadow = true;
		group.add(mesh);

		const edges = new THREE.LineSegments(
			new THREE.EdgesGeometry(geometry),
			new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.35 })
		);
		edges.position.copy(mesh.position);
		group.add(edges);

		const label = this._create_label(node.label);
		label.position.set(0, Math.max(node.size.height, 0.8) + 1.1, 0);
		group.add(label);

		return group;
	}

	render_nodes(nodes) {
		this.nodes = nodes || [];
		this._clear_scene_nodes();

		if (!this.nodes.length) {
			return;
		}

		const bounds = new THREE.Box3();

		this.nodes.forEach((node) => {
			const group = this._create_rack_group(node);
			group.position.set(node.position.x, 0, node.position.z);
			this.scene.add(group);
			this.meshes[node.name] = group;
			bounds.expandByObject(group);
		});

		this._frame_bounds(bounds);
	}

	_frame_bounds(bounds) {
		if (bounds.isEmpty()) {
			this.snap_view("perspective", false);
			return;
		}

		const center = bounds.getCenter(new THREE.Vector3());
		const size = bounds.getSize(new THREE.Vector3());
		const max_dim = Math.max(size.x, size.y, size.z, 4);
		const distance = max_dim * 2.2;

		const position = new THREE.Vector3(
			center.x + distance * 0.7,
			center.y + distance * 0.55,
			center.z + distance * 0.7
		);

		this._default_camera = { position: position.clone(), target: center.clone() };
		this.camera.position.copy(position);
		this.controls.target.copy(center);
		this.controls.update();
	}

	_create_label(text) {
		const display = (text || "").substring(0, 14);
		const canvas = document.createElement("canvas");
		const context = canvas.getContext("2d");
		canvas.width = 320;
		canvas.height = 72;

		const gradient = context.createLinearGradient(0, 0, canvas.width, 0);
		gradient.addColorStop(0, "#111827");
		gradient.addColorStop(1, "#1f2937");
		context.fillStyle = gradient;
		context.fillRect(8, 8, canvas.width - 16, canvas.height - 16);

		context.fillStyle = "#ffffff";
		context.font = "600 28px Inter, Arial, sans-serif";
		context.textAlign = "center";
		context.textBaseline = "middle";
		context.fillText(display, canvas.width / 2, canvas.height / 2);

		const texture = new THREE.CanvasTexture(canvas);
		const material = new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false });
		const sprite = new THREE.Sprite(material);
		sprite.scale.set(2.4, 0.54, 1);
		sprite.renderOrder = 999;
		return sprite;
	}

	snap_view(view, animate = true) {
		const center = this.controls.target.clone();
		const distance = 20;
		let position;

		switch (view) {
			case "top":
				position = new THREE.Vector3(center.x, center.y + distance + 10, center.z + 0.01);
				break;
			case "front":
				position = new THREE.Vector3(center.x, center.y + 6, center.z + distance);
				break;
			case "side":
				position = new THREE.Vector3(center.x + distance, center.y + 6, center.z);
				break;
			default:
				position = new THREE.Vector3(
					center.x + 14,
					center.y + 12,
					center.z + 18
				);
		}

		if (animate) {
			this.fly_to(position, center);
		} else {
			this.camera.position.copy(position);
			this.controls.target.copy(center);
			this.controls.update();
		}
	}

	focus_on_node(node) {
		const mesh = this.meshes[node.name];
		if (!mesh) {
			return;
		}

		const target = mesh.position.clone();
		const position = target.clone().add(new THREE.Vector3(7, 5, 9));
		this.fly_to(position, target);
		this._set_highlight(mesh, node);
	}

	highlight_warehouse(warehouse_name) {
		const mesh = this.meshes[warehouse_name];
		if (!mesh) {
			return;
		}
		this.focus_on_node(mesh.userData.node);
	}

	_set_highlight(mesh, node) {
		if (this._highlight_mesh) {
			this.scene.remove(this._highlight_mesh);
			this._highlight_mesh.geometry.dispose();
			this._highlight_mesh.material.dispose();
		}

		const geometry = this._create_geometry({
			...node,
			size: {
				...node.size,
				width: node.size.width + 0.2,
				height: node.size.height + 0.2,
				depth: (node.size.depth || node.size.width) + 0.2,
				radius: (node.size.radius || node.size.width / 2) + 0.15,
			},
		});

		const material = new THREE.MeshBasicMaterial({
			color: smart_erpnext.warehouse_3d.STATUS_COLORS.highlight,
			wireframe: true,
			transparent: true,
			opacity: 0.95,
		});

		this._highlight_mesh = new THREE.Mesh(geometry, material);
		this._highlight_mesh.position.set(
			mesh.position.x,
			Math.max(node.size.height, 0.8) / 2 + 0.12,
			mesh.position.z
		);
		this.scene.add(this._highlight_mesh);
	}

	fly_to(position, target) {
		this._fly_animation = {
			start: performance.now(),
			duration: 900,
			from_pos: this.camera.position.clone(),
			to_pos: position.clone ? position.clone() : new THREE.Vector3(position.x, position.y, position.z),
			from_target: this.controls.target.clone(),
			to_target: target.clone ? target.clone() : new THREE.Vector3(target.x, target.y, target.z),
		};
	}

	_animate() {
		requestAnimationFrame(() => this._animate());

		if (this._stars) {
			this._stars.rotation.y += 0.00008;
		}

		this.controls.autoRotate = this.auto_rotate && !this._fly_animation;
		if (this.auto_rotate) {
			this.controls.autoRotateSpeed = 0.8;
		}

		if (this._fly_animation) {
			const elapsed = performance.now() - this._fly_animation.start;
			const t = Math.min(elapsed / this._fly_animation.duration, 1);
			const eased = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;

			this.camera.position.lerpVectors(
				this._fly_animation.from_pos,
				this._fly_animation.to_pos,
				eased
			);
			this.controls.target.lerpVectors(
				this._fly_animation.from_target,
				this._fly_animation.to_target,
				eased
			);

			if (t >= 1) {
				this._fly_animation = null;
			}
		}

		this.controls.update();
		this.renderer.render(this.scene, this.camera);
	}

	destroy() {
		window.removeEventListener("resize", this._resize_handler);
		this._clear_scene_nodes();
		this.renderer.dispose();
	}
};
