### Smart ERPNext

Smart ERPNext

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app smart_erpnext
bench build --app smart_erpnext
bench --site your-site clear-cache
```

No extra Python packages or system libraries are required. Face recognition runs in the browser using the bundled [face-api.js](https://github.com/justadudewhohacks/face-api.js) models.

### Face Login Setup

1. Open a **User** record (for example, Administrator).
2. Upload a clear front-facing **profile photo**.
3. Click **Register Face for Login**.
4. On the login page, click **Login with Face** and allow camera access.

Users can optionally enter their email/username before face login to narrow matching. If left blank, the system matches against all registered users.

### Troubleshooting

- If face login shows **Camera Required**, allow browser camera permission for your site.
- On **WSL**, the browser may not see a webcam unless Windows camera access is enabled for WSL.
- If the console shows a **404 for face_recognition_model-shard2**, run `bench build --app smart_erpnext` and hard refresh the page.

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/smart_erpnext
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
