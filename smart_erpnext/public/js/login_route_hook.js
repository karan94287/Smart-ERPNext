// Register face-login route before Frappe login.js calls login.route().
(function () {
	let loginObject = null;

	function install_safe_route(login) {
		if (!login || login.__face_route_installed) {
			return;
		}

		login.__face_route_installed = true;

		login.face_login = function () {
			if (window.smart_erpnext && smart_erpnext.face_login) {
				smart_erpnext.face_login.show();
			}
		};

		let routeFn = function () {
			let route = window.location.hash.slice(1);
			if (!route) {
				route = "login";
			}
			route = route.replaceAll("-", "_");

			if (typeof login[route] === "function") {
				login[route]();
			}
		};

		Object.defineProperty(login, "route", {
			configurable: true,
			enumerable: true,
			get() {
				return routeFn;
			},
			set() {
				// Keep the safe route even when Frappe assigns login.route.
				routeFn = function () {
					let route = window.location.hash.slice(1);
					if (!route) {
						route = "login";
					}
					route = route.replaceAll("-", "_");

					if (typeof login[route] === "function") {
						login[route]();
					}
				};
			},
		});
	}

	Object.defineProperty(window, "login", {
		configurable: true,
		enumerable: true,
		get() {
			return loginObject;
		},
		set(value) {
			loginObject = value;
			install_safe_route(loginObject);
		},
	});
})();
