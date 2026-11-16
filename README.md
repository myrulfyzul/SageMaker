# Sagemaker Asia Mobile Platform (independent university prototype)

> **Disclaimer.** This is an independent university prototype inspired by Sagemaker Asia. It is **not an official Sagemaker product**, has no access to any private Sagemaker system, and is not an authorised integration with Sagemaker's online shop. **All payments are simulated and no real money moves.** All products, prices, artisans, accounts and orders are demo data. Do not enter real personal, card or bank information, and do not deploy this publicly as is.

The repository has two parts:

- `backend/`: a modular FastAPI + SQLite service (Python). Modules live in `backend/app/modules/` (auth, users, categories, products, cart, checkout, payments, orders, inventory, artisans, production, custom_orders, notifications, analytics, settings, forecasting, legacy).
- `lib/`: a Flutter app (Riverpod, go_router) organised by feature folders in `lib/features/`. It serves customers, and sellers, admins and artisan users through role-based navigation.

## 0. Quick start: run the app on your PC (no APK needed)

The API is hosted at `https://sagemaker-api.onrender.com` (free tier: the first request after 15 idle minutes takes 30 to 60 seconds).

**Option A: Chrome (fastest).** From the repository root:

```powershell
flutter run -d chrome --web-port=5353 --dart-define=API_BASE_URL=https://sagemaker-api.onrender.com
```

Port 5353 matters: it is the origin allowed by `ALLOWED_ORIGINS` in `render.yaml`. Press `r` for hot reload, `R` for hot restart, `q` to quit. Use Chrome DevTools (F12, device toolbar) to view it at phone size.

**Option B: Android emulator (closest to a real phone).** An emulator named `Medium_Phone_API_37.0` is already set up:

```powershell
flutter emulators --launch Medium_Phone_API_37.0
flutter run -d emulator-5554 --dart-define=API_BASE_URL=https://sagemaker-api.onrender.com
```

To work fully offline, start the local backend (section 2) and use `API_BASE_URL=http://127.0.0.1:8000` for Chrome or `http://10.0.2.2:8000` for the emulator.

## 0.1 Keep data across Render restarts (Litestream + Backblaze B2, free)

Render's free disk is wiped on every restart. `backend/start.sh` can restore the SQLite database from Backblaze B2 on start-up and stream every change back while the API runs. Until you set it up, the database resets to the seed data on each restart.

1. Create a free account at https://www.backblaze.com/sign-up/cloud-storage (10 GB free, no card needed at the time of writing).
2. **Buckets > Create a Bucket**: name it e.g. `sagemaker-db-<yourname>`, keep it **Private**. Note the **Endpoint** shown on the bucket (e.g. `s3.us-east-005.backblazeb2.com`); the region is the middle part (`us-east-005`).
3. **Application Keys > Add a New Application Key**: allow access to that bucket only, Read and Write. Copy the `keyID` and `applicationKey` (shown once).
4. In Render: **sagemaker-api > Environment**, set:

   | Key | Value |
   | --- | --- |
   | `LITESTREAM_BUCKET` | your bucket name |
   | `LITESTREAM_ENDPOINT` | the endpoint, e.g. `s3.us-east-005.backblazeb2.com` |
   | `LITESTREAM_REGION` | e.g. `us-east-005` |
   | `LITESTREAM_ACCESS_KEY_ID` | the `keyID` |
   | `LITESTREAM_SECRET_ACCESS_KEY` | the `applicationKey` |

5. Save; Render redeploys. The log should show `Restoring database from replica` and then Litestream replicating. Create an account in the app, restart the service (**Manual Deploy > Restart**), and sign in again to confirm the data survived.

Uploaded product images (`MEDIA_DIR`) are not replicated and still reset on restart; product images that point to web URLs are unaffected.

## 1. Setup on Windows with VS Code (follow in order)

Run every command from the repository root (`D:\Documents\SAGEMAKER\sagemaker-flutter`) in a VS Code PowerShell terminal.

1. **Install the prerequisites.**
   - Python 3.10 or newer (`python --version`; use `py` if `python` is not recognised).
   - Flutter SDK with Dart 3.6 or newer (`flutter --version`), Google Chrome for web, and for Android: Android Studio with an emulator or a USB-debugging phone (`flutter doctor`).
   - VS Code with the Flutter and Python extensions (optional but recommended).
2. **Create and activate a Python virtual environment.**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
   If PowerShell blocks the script, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned` first.
3. **Install the backend dependencies.**
   ```powershell
   python -m pip install -r backend\requirements.txt
   ```
   For the tests also run `python -m pip install -r backend\requirements-dev.txt`.
4. **Add the Flutter platform folders (one time).** The repository does not contain `android/` or `web/`. Generate them without touching `lib/`:
   ```powershell
   flutter create --platforms=android,web .
   ```
5. **Install the Flutter dependencies.**
   ```powershell
   flutter pub get
   ```
6. **Set the backend environment variables for this terminal.** The backend reads real environment variables only; it does not load a `.env` file. `backend\.env.example` lists every variable with placeholder values.
   ```powershell
   $env:DATABASE_PATH = "backend\demo_orders.sqlite3"
   $env:DEMO_MODE = "1"
   $env:ALLOWED_ORIGINS = "http://localhost:5353,http://127.0.0.1:5353"
   ```
   | Variable | Required | Meaning |
   | --- | --- | --- |
   | `DATABASE_PATH` | yes | SQLite file. Start-up and the CLI scripts exit with code 1 naming the variable if it is missing or invalid. |
   | `ALLOWED_ORIGINS` | no | Comma-separated http(s) origins allowed by CORS. Unset or empty sends no CORS headers. |
   | `TOKEN_LIFETIME_SECONDS` | no | Session lifetime, 3600 to 2592000. Default 604800. |
   | `DEMO_MODE` | no | Exactly `1` enables simulated payments. Anything else makes payment requests return 503. |
   | `MEDIA_DIR` | no | Folder for uploaded images. Default: `media` next to the database file. |
   | `APP_TIMEZONE` | no | IANA time zone for month buckets. Default `Asia/Kuala_Lumpur`. |
   | `DEMO_CUSTOMER_PASSWORD`, `DEMO_SELLER_PASSWORD`, `DEMO_ADMIN_PASSWORD`, `DEMO_ARTISAN_PASSWORD` | no | Override the demo account passwords used by the seed script (see section 4). |
7. **Check and apply the database migrations.**
   ```powershell
   python -m backend.migrate status
   python -m backend.migrate up
   ```
   Migrations are applied in version order, each in its own transaction. Before the first migration of an existing database file, a one-time `.bak` copy is written. The backend also applies pending migrations when it starts. Orders created by the earlier prototype are kept.
8. **Seed the demo data.**
   ```powershell
   python -m backend.seed
   ```
   The seed runs in one transaction. Exit codes: `0` success, `1` failure (everything rolled back), `2` `Seeded data already exists` (nothing changed), `3` `Reset cancelled`. To delete only demo rows and seed again, run `python -m backend.seed --reset` and type `RESET-DEMO` when asked. Any other answer changes nothing.

## 2. Run the backend and the app

Terminal 1 (backend, with the step 6 variables set and the virtual environment active):

```powershell
python backend\server.py
```

The API listens on `http://127.0.0.1:8000`. Check `http://127.0.0.1:8000/api/health`. Interactive API documentation is at `http://127.0.0.1:8000/docs` and the schema at `http://127.0.0.1:8000/openapi.json`.

Terminal 2 (app). The base URL comes from `--dart-define=API_BASE_URL=...`. Without it the app uses `http://localhost:8000` on web and desktop and `http://10.0.2.2:8000` on Android. The URL can also be overridden in the app's connection settings screen.

**Web (Chrome).** Use port 5353, which is the port in `ALLOWED_ORIGINS`:

```powershell
flutter run -d chrome --web-port=5353 --dart-define=API_BASE_URL=http://127.0.0.1:8000
```

**Android emulator.** `10.0.2.2` is the emulator's alias for your PC's `127.0.0.1`, so the backend command above works unchanged:

```powershell
flutter emulators --launch <emulator-id>
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

**Physical Android phone.** The phone and the PC must be on the same network. Start the backend so that it listens on all interfaces, then give the app your PC's LAN address (find it with `ipconfig`) and allow port 8000 through Windows Firewall when prompted:

```powershell
python -m uvicorn app.main:application --app-dir backend --host 0.0.0.0 --port 8000
flutter run -d <device-id> --dart-define=API_BASE_URL=http://<PC-LAN-IP>:8000
```

Both terminals must stay running. If the app shows an unreachable error, it displays the base URL in use with a retry action.

## 3. Build an APK

1. Complete section 1, including the `flutter create --platforms=android,web .` step.
2. Android blocks network access in release builds unless the manifest allows it. In `android\app\src\main\AndroidManifest.xml` make sure `<uses-permission android:name="android.permission.INTERNET"/>` is present above `<application>`. Because the demo backend uses plain `http`, also add `android:usesCleartextTraffic="true"` to the `<application>` tag (demo only; see section 7 for HTTPS).
3. Build, pointing the app at the backend the phone will reach:
   ```powershell
   flutter build apk --release --dart-define=API_BASE_URL=http://<PC-LAN-IP>:8000
   ```
4. The APK is written to `build\app\outputs\flutter-apk\app-release.apk`. Copy it to the phone and install it (allow installs from your file manager).

No APK is committed to this repository and none has been built as part of writing this README.

## 4. Demo credentials (demo-only)

The seed script creates these accounts. **They are demo-only credentials. Never use them, or any password derived from them, in production.** Each password can be changed by setting the matching environment variable before seeding (section 1, step 6).

| Role | E-mail | Password (demo-only) | Override variable |
| --- | --- | --- | --- |
| Customer | `demo.customer1@example.com` (also `demo.customer2@example.com`, `demo.customer3@example.com`) | `DemoCustomer1!` | `DEMO_CUSTOMER_PASSWORD` |
| Seller | `demo.seller@example.com` | `DemoSeller1!` | `DEMO_SELLER_PASSWORD` |
| Admin | `demo.admin@example.com` | `DemoAdmin1!` | `DEMO_ADMIN_PASSWORD` |
| Artisan user | `demo.artisan@example.com` | `DemoArtisan1!` | `DEMO_ARTISAN_PASSWORD` |

What the seed creates (all marked as demo data): 15 products across tote bags, fabric books, toys, gifts and accessories (the 4 products from `assets/products.json` keep their ids), 4 artisan profiles, one order in each fulfilment status, one production job in each production status, 2 custom orders, 4 notifications, and 12 months of synthetic sales history.

## 5. Try the demo scenario

1. Log in as the customer, browse **Shop**, add products to the cart, and check out with a simulated payment method.
2. Log in as the seller (or admin). The same order appears under **Orders**. Confirm it and assign a production job to an artisan.
3. Log in as the artisan user and update the job progress. The customer sees the production label on the order tracking screen.
4. As the seller, mark the order `shipped` with a shipping reference. The **Dashboard** KPIs and best sellers include the order.

An automated end-to-end test of this scenario is in ackend/tests/e2e (see requirement 30 in the checklist).

The earlier prototype's admin script still works against the legacy endpoint: set `SAGEMAKER_ADMIN_KEY` to a private value of your choice in your terminal, then run `python backend\admin_update.py <ORDER-ID> packing|shipped|delivered [tracking_code]`.

## 6. Tests

Backend (pytest, Hypothesis, httpx; uses a temporary database per run):

```powershell
python -m pip install -r backend\requirements-dev.txt
python -m pytest backend -q
```

Flutter:

```powershell
flutter test
```

### Test results

Recorded from runs executed on 2026-11-13 (Windows, Python 3.15.0, Flutter 3.47.7). The Flutter suite and `flutter analyze` were run again after the final edit and are the numbers below.

| Suite | Command | Passed | Failed | Skipped | Date |
| --- | --- | --- | --- | --- | --- |
| Backend (unit, property, API contract, architecture, end-to-end and `test_server.py`) | `python -m pytest backend -q --durations=25` | 493 | 0 | 6 | 2026-11-13 |
| Flutter | `flutter test` | 241 | 0 | 0 | 2026-11-13 |
| Flutter static analysis | `flutter analyze` | no issues found | | | 2026-11-13 |

Notes on these runs:

- The backend run took 7 min 16 s (436.73 s). The slowest tests are property tests: the concurrent checkout stock-conservation test (about 20 s), the two login-lockout tests (about 19 s each) and the notification scoping and address-default tests (about 14 to 16 s). No property test was reduced; the full suite fits in one run.
- The 6 skips are in `backend/tests/architecture/test_module_boundaries.py`: the repository table-ownership check is skipped for modules that have no `repository.py` (analytics, checkout, forecasting, legacy, payments, settings). This is by design.
- Earlier, one full backend run failed `test_access_matrix` and `test_foreign_resources_look_like_missing_ones_and_nothing_changes`, and an even earlier run timed out at 15 minutes. The cause of that failure was not found. In this run both tests passed in the full suite, and they also passed in a second targeted run together with `test_server.py`, the end-to-end and the API contract tests. I could not reproduce the failure, so I changed no test code for it. If it recurs, treat it as an open issue.
- `flutter analyze` initially reported one info-level lint (an unnecessary import in `test/prop_role_navigation_test.dart`). I removed the import and re-ran both Flutter commands; they are clean.
- Not run: an Android APK build, and the manual demo scenario on a device or emulator.

## 7. Feature completion checklist

Status is based on the implementation tasks in `.kiro/specs/sagemaker-asia-mobile-platform/tasks.md` and on inspecting the code. Test evidence is recorded in the Test results section above (run on 2026-11-13).

| Req | Requirement | Status | Notes |
| --- | --- | --- | --- |
| 1 | Project stabilisation and non-destructive refactor | partial | Modules, migrations, legacy compatibility and integer money are in place. The rule that modules touch other modules only through their `api` is not fully met: some modules import another module's `service` or `schemas` types (for example `auth.service.SessionInfo`, `orders.schemas`, `payments.schemas`). The automated architecture test (ackend/tests/architecture) exists and passes in the recorded run. |
| 2 | Configurable API connection | complete | |
| 3 | Branding, theme and demo disclosure | complete | |
| 4 | Registration | complete | |
| 5 | Login, logout and persistent sessions | complete | |
| 6 | Role-based access control | complete | The access-control matrix property test passes in the recorded run. |
| 7 | Profile and address management | complete | |
| 8 | Home screen | complete | |
| 9 | Product catalogue browsing | complete | |
| 10 | Favourites | complete | |
| 11 | Server-validated cart | complete | |
| 12 | Checkout and delivery details | complete | |
| 13 | Demo payment | complete | Simulated only. |
| 14 | Order creation, stock deduction and duplicate prevention | complete | |
| 15 | Order history and tracking | complete | |
| 16 | Custom orders (customer side) | complete | |
| 17 | Notifications | complete | In-app only. |
| 18 | Customer navigation | complete | |
| 19 | Seller/admin navigation and dashboard | complete | |
| 20 | Product management | complete | |
| 21 | Inventory management | complete | |
| 22 | Order management | complete | |
| 23 | Artisan management | complete | |
| 24 | Production tracking | complete | |
| 25 | Custom-order management (seller side) | complete | |
| 26 | Sales analytics | complete | |
| 27 | AI demand forecasting | complete | A small statistical model on synthetic data; see limitations. |
| 28 | API quality and error handling | complete | The OpenAPI and money-field contract tests (ackend/tests/api) pass in the recorded run. |
| 29 | Demo data and seed script | complete | |
| 30 | End-to-end demo scenario | partial | The scenario can be followed by hand (section 5). The automated end-to-end test (ackend/tests/e2e) passes in the recorded run. |
| 31 | Automated testing | complete | Backend and Flutter suites exist, including access-control, ownership, architecture, end-to-end and contract tests. Executed results are recorded in section 6: backend 493 passed, 6 skipped, 0 failed; Flutter 241 passed, 0 failed. One earlier unexplained failure of two property tests is noted there. |
| 32 | Documentation and deliverables | partial | This README covers setup, run, APK steps, credentials, checklist, limitations and commercial-use changes. The APK steps are written but not executed, and the `android/` and `web/` folders are not in the repository. |
| 33 | Security and privacy | complete | Prototype-level protections only; see commercial-use changes. |

## 8. Limitations

- **Simulated payments.** No card, bank or wallet data is collected and no gateway is called. The server records a simulated outcome (paid, pending cash on delivery, failed or cancelled) for the chosen method.
- **No courier integration.** Shipping status and shipping references are typed in by staff; nothing is sent to or read from a courier. Delivery is a flat RM 8.00 demo fee.
- **No e-mail delivery.** Notifications are rows shown inside the app. No e-mail is sent.
- **No push delivery.** There are no push messages and no SMS. Users see notifications only when they open the app.
- **Synthetic forecasting data.** The seeded sales history is generated with a fixed random seed. Forecasts and their accuracy figures (MAE, RMSE) are labelled as synthetic and are not evidence of real demand.
- **SQLite scale limits.** One SQLite file with one writer at a time is meant for a single demo server. It is not designed for many concurrent users or multiple server instances.
- **Demo data and images.** Prices are fictional. Product photos and names come from public Sagemaker site URLs and are used here only for demonstration.

## 9. Changes needed for commercial use

- **Real payment gateway.** Integrate a licensed gateway with server-side verification and webhooks, plus refunds and fraud checks. Keep card data off your servers and out of the app.
- **Courier APIs.** Replace manual shipping references with courier integrations for rates, labels, tracking and delivery confirmation.
- **Production database.** Move from SQLite to a managed server database with backups, monitoring and a tested migration process.
- **Hosted secrets management.** Keep keys and passwords in a secrets manager rather than shell variables; rotate them and remove the demo accounts and their passwords.
- **Image rights and permissions.** Obtain written permission or licences for all product photos, names and brand material before any distribution.
- **PDPA compliance.** Put in place consent, privacy notice, access and deletion handling, retention rules and breach procedures that satisfy Malaysia's Personal Data Protection Act.
- **HTTPS.** Serve the API over HTTPS only and remove the cleartext-traffic setting from the Android build.
- **Independent security review.** Commission a penetration test and code review before handling real customers.

## 10. Repository notes

- `backend/server.py` is a thin shim that starts the new app; the original routes live under `/api/legacy/*` with unchanged request and response shapes.
- `backend/demo_orders.sqlite3` is the default development database. Back it up before experiments.
- `CHANGES.md` describes the earlier prototype versions.
