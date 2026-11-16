# Requirements Document

## Introduction

The Sagemaker Asia Mobile Platform is an independent university prototype inspired by Sagemaker Asia, a Malaysian social enterprise that sells handcrafted products made by women artisans. It is not an official Sagemaker product. It has no access to any private Sagemaker backend. All payments are simulated, no real money moves, and all demo data is labelled as demo data.

The platform has two parts: a Flutter (Material 3) mobile and web client with a customer experience and a separate seller/admin experience, and a modular Python FastAPI REST backend backed by SQLite (kept migratable to PostgreSQL). The backend also provides production tracking, analytics and AI demand forecasting.

Starting point (inspected in the workspace): `lib/main.dart` is a single 52 KB file with guest checkout, favourites, cart and orders; `backend/server.py` is a single-file FastAPI app with `orders` table, demo orders and an `X-Admin-Key` status endpoint; `backend/requirements.txt` lists only fastapi and uvicorn; `assets/products.json` holds 4+ demo products with `demoPriceSen`; `pubspec.yaml` depends on `http` and `shared_preferences`. `lib/admin_page.dart` does not exist. Existing working features (catalogue, favourites, cart persistence, demo order creation with idempotency key, order token, flat RM8 delivery, `backend/test_server.py`) are to be refactored non-destructively into the new structure, and existing order data in `backend/demo_orders.sqlite3` is to be preserved.

## Glossary

- **Platform**: The complete system made of the Mobile_App and the Backend_API.
- **Mobile_App**: The Flutter client, using Material 3, a feature-based folder structure and Riverpod for state management.
- **Backend_API**: The FastAPI REST service exposing JSON endpoints under `/api`.
- **Database**: The SQLite database used by the Backend_API.
- **Migration_Runner**: The Backend_API component that applies versioned, non-destructive schema changes to the Database.
- **Seed_Script**: The repeatable command-line script that loads demo data into the Database.
- **User**: Any authenticated account holder with exactly one Role.
- **Role**: One of `customer`, `seller`, `admin` or `artisan`.
- **Customer**: A User with Role `customer`.
- **Seller**: A User with Role `seller`.
- **Admin**: A User with Role `admin`.
- **Artisan_User**: A User with Role `artisan`.
- **Staff_User**: A Seller or an Admin.
- **Auth_Service**: The Backend_API module handling registration, login, logout and session validation.
- **Session_Token**: A random bearer token issued at login and stored server-side only as a hash.
- **RBAC_Guard**: The Backend_API component that checks a User's Role against the Role required by an endpoint.
- **Catalogue_Service**: The Backend_API module managing products, categories, variations and images.
- **Product**: A sellable item with name, description, category, price, images, stock, active flag and optional Artisan link.
- **Variation**: A selectable option of a Product (for example size or colour) with its own stock.
- **Cart_Service**: The Backend_API module that stores and validates carts.
- **Cart**: The persisted list of Product and Variation lines with quantities belonging to one User.
- **Checkout_Service**: The Backend_API module that turns a Cart plus delivery details into an Order.
- **Order**: A persisted purchase record with unique ID, lines, totals, payment, fulfilment status and history.
- **Fulfilment_Status**: The delivery state of an Order: `placed`, `confirmed`, `preparing`, `shipped`, `delivered`, `cancelled` or `payment_failed`.
- **Payment_Service**: The Backend_API module that simulates payment and stores Payment_Records.
- **Payment_Record**: A persisted record of one simulated payment attempt with method, outcome and Order link.
- **Payment_Outcome**: One of `success`, `failed` or `cancelled`.
- **Payment_Method**: One of `card`, `fpx`, `ewallet` or `cod`.
- **Inventory_Service**: The Backend_API module managing stock levels, thresholds, alerts and adjustments.
- **Low_Stock_Threshold**: The per-Product stock quantity at or below which a low-stock alert is raised.
- **Stock_Adjustment**: A persisted record of one change in stock with delta, reason, actor and timestamp.
- **Artisan**: A profile of a woman maker with specialisation, availability, assigned products and job counts.
- **Artisan_Service**: The Backend_API module managing Artisan profiles.
- **Production_Service**: The Backend_API module managing Production_Jobs.
- **Production_Job**: A work item linked to an Order and Product with assigned Artisan, quantity, deadline, priority, progress and notes.
- **Production_Status**: One of `order_confirmed`, `production_assigned`, `in_production`, `quality_checking`, `completed` or `ready_for_fulfilment`. It is independent of Fulfilment_Status.
- **Custom_Order**: A customer request for a bespoke item with product type, description, quantity, preferred date, optional reference image and status.
- **Custom_Order_Service**: The Backend_API module managing Custom_Orders.
- **Custom_Order_Status**: One of `submitted`, `accepted`, `rejected`, `in_progress`, `completed`.
- **Notification_Service**: The Backend_API module creating and serving in-app notifications.
- **Notification**: A persisted message addressed to one User with read or unread state.
- **Analytics_Service**: The Backend_API module computing KPIs and chart series from Database records.
- **AOV**: Average order value, equal to total revenue of non-cancelled, paid Orders divided by their count.
- **Forecasting_Service**: The Python module that produces demand forecasts using pandas and NumPy.
- **Baseline_Model**: A naive forecasting model (moving average of recent periods).
- **Candidate_Model**: A simple regression-based forecasting model (for example linear trend with seasonality via NumPy or scikit-learn).
- **Backtest**: An evaluation that trains on earlier periods and predicts held-out later periods.
- **Synthetic_Data**: Generated sales history clearly marked as not real.
- **Demo_Label**: A visible text marker stating that data, prices, images or payments are demo or simulated.
- **API_Base_URL**: The configurable address of the Backend_API used by the Mobile_App.
- **Money_Sen**: A monetary amount stored as an integer number of sen (RM 1.00 = 100 sen).

## Requirements

### Requirement 1: Project Stabilisation and Non-Destructive Refactor

**User Story:** As a developer, I want the existing working prototype stabilised and reorganised, so that new features build on tested code without losing data.

#### Acceptance Criteria

1. WHEN the refactor is complete, THE Platform SHALL provide the catalogue, favourites, cart persistence, demo order creation and order tracking features, and each feature SHALL pass the same functional checks (inputs and expected outputs) that the feature passed before the refactor.
2. WHEN the Backend_API starts against a Database created by the earlier prototype, THE Migration_Runner SHALL apply all pending migrations, and the row count and field values of every row in the existing `orders` table SHALL be identical before and after the migrations.
3. WHEN the Migration_Runner applies a migration successfully, THE Migration_Runner SHALL record the migration version in the `schema_migrations` table in the same transaction as the migration.
4. IF a migration version is already recorded in `schema_migrations`, THEN THE Migration_Runner SHALL skip that migration so that each version is applied at most once.
5. IF a migration fails, THEN THE Migration_Runner SHALL roll back all changes of that migration, SHALL NOT record its version, and SHALL stop Backend_API start-up with a non-zero exit code and an error message containing the failed version identifier.
6. THE Backend_API SHALL be organised into separate modules for auth, users, products, categories, cart and checkout, payments, orders, inventory, artisans, production, custom orders, notifications, analytics and forecasting, and no module SHALL read or write the tables of another module directly, only through the public interface of that module.
7. THE Mobile_App SHALL be organised into feature folders, each containing its own screens, state and data access code.
8. WHEN the Backend_API starts, THE Backend_API SHALL read the database path, allowed origins, token lifetime in seconds and demo mode from environment variables.
9. IF a required environment variable is missing or invalid, THEN THE Backend_API SHALL stop start-up with a non-zero exit code and an error message naming the variable, and THE Backend_API SHALL NOT fall back to a hard-coded secret.
10. THE Mobile_App SHALL contain no secret keys, passwords or admin keys in source code or bundled assets, and a repository scan for such values SHALL return zero matches.
11. THE Backend_API SHALL store every Money_Sen value as an integer and SHALL return every Money_Sen value as a JSON integer without a decimal point or quotation marks.

### Requirement 2: Configurable API Connection

**User Story:** As a developer, I want to point the app at different backend addresses, so that it runs on web, Android emulator and a physical phone.

#### Acceptance Criteria

1. THE Mobile_App SHALL read the default API_Base_URL from the compile-time define `API_BASE_URL`.
2. IF no `API_BASE_URL` define is supplied, THEN THE Mobile_App SHALL use `http://localhost:8000` on web and desktop and `http://10.0.2.2:8000` on Android.
3. WHEN a Staff_User or developer saves a new API_Base_URL on the connection settings screen, THE Mobile_App SHALL validate that the value is an absolute http or https URL with a non-empty host and a maximum length of 2048 characters, persist the value, and use the value for all subsequent requests without a restart.
4. IF validation of a new API_Base_URL fails, THEN THE Mobile_App SHALL show an error stating that the value is not a valid URL, keep the previous value and keep the connection settings screen open.
5. WHILE a persisted API_Base_URL override exists, THE Mobile_App SHALL use the override in preference to the compile-time define and the platform defaults; WHEN the user clears the override, THE Mobile_App SHALL revert to the default API_Base_URL.
6. IF the Backend_API cannot be reached or does not respond within 10 seconds, THEN THE Mobile_App SHALL show an unreachable error that displays the API_Base_URL in use and a retry action that re-sends the failed request.
7. WHEN a request from an origin listed in the comma-separated `ALLOWED_ORIGINS` environment variable arrives, THE Backend_API SHALL respond with cross-origin headers permitting that origin.
8. IF the request origin is not listed in `ALLOWED_ORIGINS` or `ALLOWED_ORIGINS` is unset or empty, THEN THE Backend_API SHALL omit cross-origin permission headers from the response.
9. WHERE the request origin is allowed, THE Backend_API SHALL permit the methods GET, POST, PUT, PATCH and DELETE and the headers Content-Type and Authorization only.

### Requirement 3: Branding, Theme and Demo Disclosure

**User Story:** As a user, I want a consistent premium look and clear demo labelling, so that I understand this is a prototype.

#### Acceptance Criteria

1. THE Mobile_App SHALL use Material 3 with Primary #123D32, Secondary #87A999, Background #F8F5EE, Accent #E9C879, Text #26332E and white (#FFFFFF) card surfaces on every screen.
2. THE Mobile_App SHALL render cards, buttons and inputs with a corner radius of 12 to 16 logical pixels.
3. WHILE the Mobile_App waits for the Backend_API, THE Mobile_App SHALL show a loading indicator and SHALL remove the indicator within 500 ms after a response or an error is received.
4. WHEN a list screen receives an empty result, THE Mobile_App SHALL show an empty state with a message and one next-step action button that navigates to another screen.
5. IF a request fails or does not respond within 15 seconds, THEN THE Mobile_App SHALL show an error state with the reason (network unavailable, timeout or server error) and a retry action, and SHALL keep user-entered input.
6. WHEN the retry action is tapped, THE Mobile_App SHALL resend the request, show the loading indicator and replace the error state with the result.
7. THE Mobile_App SHALL show a Demo_Label stating that the app is an independent university prototype and not officially Sagemaker, visible without scrolling on the About screen and the login screen.
8. THE Mobile_App SHALL show a Demo_Label stating that payments are simulated on the payment screen and the order confirmation screen.
9. WHEN a demo product, price or order is displayed, THE Mobile_App SHALL show a Demo_Label adjacent to the displayed item.
10. THE Mobile_App SHALL render body text with a contrast ratio of at least 4.5:1 and text of 18 points or larger with a contrast ratio of at least 3:1 against the background.
11. THE Mobile_App SHALL provide a non-empty semantic label for every icon-only button.

### Requirement 4: Registration

**User Story:** As a new customer, I want to create an account, so that my cart, favourites and orders are saved.

#### Acceptance Criteria

1. WHEN a registration request with a name of 1 to 100 characters, a unique email of 3 to 254 characters in valid format, and a password of 8 to 128 characters with at least one letter and one digit is received, THE Auth_Service SHALL create a User with Role `customer` and return the id, name, email and Role within 2 seconds.
2. THE Auth_Service SHALL store the password only as a salted hash produced by bcrypt or argon2.
3. IF the email of a registration request is already registered (compared case-insensitively), THEN THE Auth_Service SHALL reject the request with HTTP 409 and an error message, and SHALL create or modify no User.
4. IF the name is missing, empty or longer than 100 characters, the email format is invalid, the email is longer than 254 characters, or the password is shorter than 8 characters, longer than 128 characters or lacks a letter or a digit, THEN THE Auth_Service SHALL reject the request with HTTP 422 listing each invalid field and SHALL create no User.
5. WHEN a public registration request supplies a Role, THE Auth_Service SHALL ignore the supplied Role and assign Role `customer`.
6. THE Backend_API SHALL exclude every password and password hash from every response, including error responses.
7. IF User creation fails internally, THEN THE Auth_Service SHALL reject the request with HTTP 500 and a message stating that registration failed, and SHALL persist no partial User.

### Requirement 5: Login, Logout and Persistent Sessions

**User Story:** As a user, I want to log in and stay logged in, so that I do not re-enter credentials each time.

#### Acceptance Criteria

1. WHEN a login request with a matching email and password is received, THE Auth_Service SHALL return a Session_Token, its expiry time and the Role of the User within 2 seconds for at least 95% of requests.
2. IF a login request has an unknown email or a wrong password, THEN THE Auth_Service SHALL reject the request with HTTP 401 and the same generic message for both cases, and SHALL issue no token.
3. IF five consecutive failed logins occur for one email within 10 minutes, THEN THE Auth_Service SHALL reject every further login attempt for that email, including attempts with correct credentials, for 5 minutes from the fifth failure with HTTP 429 and the remaining wait time in seconds.
4. THE Auth_Service SHALL store only a hash of each Session_Token and SHALL NOT store the token in plaintext.
5. WHEN the Mobile_App starts with a stored Session_Token, THE Mobile_App SHALL validate the token with the Backend_API and, if the token is valid, open the area for the Role of the User without showing the login screen.
6. IF the stored Session_Token is expired or revoked, THEN THE Mobile_App SHALL delete the token from the device and show the login screen.
7. WHEN a logout request with a valid Session_Token is received, THE Auth_Service SHALL revoke the token so that later use of the token is rejected with HTTP 401.
8. WHERE secure storage is available on the platform, THE Mobile_App SHALL store the Session_Token in secure storage.
9. WHEN a customer login succeeds, THE Mobile_App SHALL open the customer navigation.
10. WHEN a Seller, Admin or Artisan_User login succeeds, THE Mobile_App SHALL open the seller/admin navigation.
11. IF the Backend_API is unreachable or gives no response within 10 seconds during start-up token validation, THEN THE Mobile_App SHALL keep the stored Session_Token, show the login screen and show an error that the server could not be reached.

### Requirement 6: Role-Based Access Control

**User Story:** As a business owner, I want each role limited to its own functions, so that data and operations stay protected.

#### Acceptance Criteria

1. IF a request to a protected endpoint has a missing, malformed, expired or revoked Session_Token, THEN THE RBAC_Guard SHALL reject the request with HTTP 401, change no data and return no protected data.
2. IF an authenticated User lacks the Role required by an endpoint, THEN THE RBAC_Guard SHALL reject the request with HTTP 403, change no data and return no protected data.
3. WHEN a Customer requests a profile, address, cart, favourite, order, payment, custom order or notification resource, THE RBAC_Guard SHALL allow access only to resources owned by that Customer.
4. WHEN a Staff_User requests a product management, inventory, order management, production, custom-order management, artisan management, analytics, forecasting or settings endpoint, THE RBAC_Guard SHALL allow the request.
5. IF a Staff_User or Customer requests a role change or account deactivation, THEN THE RBAC_Guard SHALL reject the request with HTTP 403 and leave the target User unchanged.
6. WHEN an Admin requests a role change or account deactivation, THE RBAC_Guard SHALL allow the request.
7. WHEN an Artisan_User views or updates the progress of a Production_Job, THE RBAC_Guard SHALL allow the request only if the Production_Job is assigned to the Artisan profile of that Artisan_User.
8. IF an Artisan_User requests an unassigned Production_Job or any other endpoint, THEN THE RBAC_Guard SHALL reject the request with HTTP 403 and leave all data unchanged.
9. IF a Customer requests an Order, Payment_Record or Custom_Order owned by another User, THEN THE Backend_API SHALL respond with HTTP 404 and a body identical to the body for a non-existent resource, and SHALL leave the resource unchanged.
10. WHILE a User is signed in, THE Mobile_App SHALL show only the navigation destinations permitted for the Role of the User.
11. WHEN the Role of the User changes or the User signs out, THE Mobile_App SHALL update the displayed navigation within 2 seconds of the next successful session refresh or sign-out.

### Requirement 7: Profile and Address Management

**User Story:** As a customer, I want to manage my profile and delivery addresses, so that checkout is quick.

#### Acceptance Criteria

1. WHEN a Customer requests the profile, THE Backend_API SHALL return the name, email, phone and Role of the Customer within 2 seconds.
2. WHEN a valid profile update with a name of 1 to 100 characters and a phone of 8 to 15 digits is submitted, THE Backend_API SHALL save the update and return the updated profile.
3. IF the name is missing or longer than 100 characters, or the phone is not 8 to 15 digits, THEN THE Backend_API SHALL reject the update with HTTP 422 listing the invalid fields and SHALL leave the profile unchanged.
4. WHEN an address with a recipient name of 1 to 100 characters, a phone of 8 to 15 digits, address line 1 of 1 to 200 characters, optional address line 2 of 0 to 200 characters, a 5-digit Malaysian postcode, a city of 1 to 100 characters and a state is submitted, THE Backend_API SHALL save the address to the address book of the Customer and return the address.
5. IF the postcode is not exactly 5 digits, a required field is missing or a field exceeds its maximum length, THEN THE Backend_API SHALL reject the address with HTTP 422 listing the invalid fields and SHALL change no address.
6. WHEN an address is marked as default, THE Backend_API SHALL ensure that exactly one address of that Customer is the default and SHALL clear the default flag on the other addresses of that Customer.
7. WHEN an address is deleted, THE Backend_API SHALL remove the address without altering the delivery details of existing Orders.
8. IF a Customer updates, sets as default or deletes an address that does not exist or belongs to another Customer, THEN THE Backend_API SHALL reject the request with HTTP 404 and leave all addresses unchanged.
9. WHEN a Customer opens the Profile tab, THE Mobile_App SHALL show the profile details, the address list, links to My Orders, Custom Orders, Notifications and About, and a logout action.
10. IF loading the profile or the addresses fails, THEN THE Mobile_App SHALL show an error indication and a retry action.

### Requirement 8: Home Screen

**User Story:** As a customer, I want an engaging home screen, so that I discover products and the Sagemaker story.

#### Acceptance Criteria

1. WHEN a Customer opens Home, THE Mobile_App SHALL show branding, a banner, collections, categories, best sellers, new arrivals, recommendations, a storytelling section and a search field.
2. THE Backend_API SHALL provide best sellers as up to 10 active Products ranked by units sold in non-cancelled Orders in the preceding 90 days in descending order, with ties ordered by creation time newest first.
3. THE Backend_API SHALL provide new arrivals as up to 10 active Products ordered by creation time newest first.
4. WHEN a signed-in Customer with at least one favourite or past purchase requests recommendations, THE Backend_API SHALL return up to 10 active Products from the categories of the favourited and purchased Products, excluding Products the Customer already purchased.
5. WHEN a visitor who is not signed in, or a Customer with no favourites and no purchases, requests recommendations, THE Backend_API SHALL return the same Products in the same order as best sellers.
6. WHEN non-empty text of 1 to 100 characters is submitted in the Home search field, THE Mobile_App SHALL open the Shop screen with the text as the search query.
7. IF the Home search field is empty or contains only whitespace on submission, THEN THE Mobile_App SHALL stay on Home, SHALL NOT open the Shop screen and SHALL keep the search field focused.
8. IF a Home section request fails or returns zero Products, THEN THE Mobile_App SHALL show an empty-state or error indicator in that section within 10 seconds, keep the other sections displayed and offer a retry action for a failed section.
9. THE Mobile_App SHALL show the Demo_Label adjacent to each demo image and demo price on Home.

### Requirement 9: Product Catalogue Browsing

**User Story:** As a customer, I want to search, filter and sort products, so that I find what I want.

#### Acceptance Criteria

1. WHEN a Customer or visitor lists Products, THE Catalogue_Service SHALL return only active Products and SHALL exclude inactive Products from the results and from the total.
2. WHEN a search query of 1 to 100 characters is supplied, THE Catalogue_Service SHALL return Products whose name or description contains the query, compared case-insensitively.
3. IF the search query exceeds 100 characters, THEN THE Catalogue_Service SHALL reject the request with a validation error and return no Products.
4. WHEN a category filter is supplied, THE Catalogue_Service SHALL return only Products in that category.
5. IF the category filter does not match any existing category, THEN THE Catalogue_Service SHALL return an empty list with a total of 0.
6. WHEN a price sort is supplied, THE Catalogue_Service SHALL order the results by price ascending or descending as requested, with Products of equal price ordered by name ascending.
7. WHEN search, category and sort parameters are combined, THE Catalogue_Service SHALL apply search and category as an intersection and then apply the sort.
8. THE Catalogue_Service SHALL support pagination with an integer `limit` of 1 to 100 (default 20) and an integer `offset` of 0 or more (default 0), and SHALL return the total of all matches regardless of `limit` and `offset`.
9. IF `limit` is outside 1 to 100, or `offset` is negative or not an integer, THEN THE Catalogue_Service SHALL reject the request with a validation error identifying the parameter.
10. WHEN a Customer opens a product detail, THE Mobile_App SHALL show images, name, description, category, price in RM with 2 decimals, Variations, stock status and the public name of the Artisan when an Artisan is linked.
11. THE Mobile_App SHALL show the stock status "In stock" when stock is above the Low_Stock_Threshold, "Low stock: N left" when stock is at or below the Low_Stock_Threshold and above zero, and "Out of stock" when stock is zero.
12. IF a Product is out of stock, THEN THE Mobile_App SHALL disable the add-to-cart action for that Product.
13. THE Catalogue_Service SHALL include the categories tote bags, fabric books, toys, gifts and accessories.
14. IF a Product does not exist, or is inactive and the requester is not a Staff_User, THEN THE Catalogue_Service SHALL respond with HTTP 404 and no Product data.

### Requirement 10: Favourites

**User Story:** As a customer, I want to save favourite products, so that I can find them later on any device.

#### Acceptance Criteria

1. WHEN a signed-in Customer adds an active Product to favourites, THE Backend_API SHALL store the association and succeed within 2 seconds.
2. WHEN a signed-in Customer adds a Product that is already a favourite, THE Backend_API SHALL leave the favourites unchanged, create no duplicate and succeed within 2 seconds.
3. WHEN a signed-in Customer removes a favourite, THE Backend_API SHALL delete the association and succeed within 2 seconds.
4. WHEN a signed-in Customer removes a Product that is not a favourite, THE Backend_API SHALL leave the favourites unchanged and succeed (idempotent).
5. IF the Product does not exist or is inactive, THEN THE Backend_API SHALL reject the add request with an unavailable error and leave the favourites unchanged.
6. IF a favourites request is unauthenticated or the session has expired, THEN THE Backend_API SHALL reject the request with an authentication-required error and leave the favourites unchanged.
7. WHEN a Customer signs in on another device, THE Mobile_App SHALL load and display the same favourites within 3 seconds on a connection of at least 1 Mbps.
8. IF loading favourites fails because of a network error or a 10-second timeout, THEN THE Mobile_App SHALL show an error and a retry action.
9. WHEN a favourite Product becomes inactive, THE Backend_API SHALL omit the Product from subsequent favourites lists and SHALL retain the association so that the Product returns if reactivated.
10. WHERE favourites were saved locally by the earlier prototype, THE Mobile_App SHALL upload them on the first successful sign-in, merge them without duplicates, and clear the local copy only after the upload is confirmed successful.
11. IF the upload of local favourites fails, THEN THE Mobile_App SHALL retain the local copy and retry at the next successful sign-in.

### Requirement 11: Server-Validated Cart

**User Story:** As a customer, I want a cart that always reflects true prices and stock, so that checkout has no surprises.

#### Acceptance Criteria

1. WHEN a Customer adds a Product or Variation with an integer quantity of 1 to 20, THE Cart_Service SHALL add a line or increase the existing line by that amount and return the updated Cart within 2 seconds.
2. IF the quantity is not an integer from 1 to 20, THEN THE Cart_Service SHALL reject the request with an error stating the allowed range and leave the Cart unchanged.
3. IF a change would make the quantity of a single line exceed 20, THEN THE Cart_Service SHALL reject the change with an error indicating the maximum of 20 per line and leave the Cart unchanged.
4. WHEN a Cart is requested or modified, THE Cart_Service SHALL compute line totals, subtotal, delivery fee and grand total on the server from current Database prices in integer sen and SHALL ignore client-supplied prices.
5. WHILE a Cart has at least 1 available line, THE Cart_Service SHALL apply a flat delivery fee of 800 sen; WHILE the Cart is empty, THE Cart_Service SHALL apply a delivery fee of 0 sen.
6. IF a requested quantity exceeds the available stock, THEN THE Cart_Service SHALL reject the change with HTTP 409 stating the available quantity and leave the Cart unchanged.
7. IF a Product or Variation in the Cart becomes inactive or has 0 stock, THEN THE Cart_Service SHALL flag the line as unavailable and exclude the line from the subtotal and the grand total.
8. WHEN a quantity is set to 0 or a line is removed, THE Cart_Service SHALL delete the line and return the updated Cart.
9. THE Cart_Service SHALL persist each Cart by User so that the Cart survives restarts and device changes, and a read after a successful change SHALL reflect the change.
10. FOR ALL carts, the grand total SHALL equal the sum of available line totals plus the delivery fee (invariant).
11. FOR ALL cart operations, adding a line and then removing the same line SHALL return the Cart to its previous contents (round-trip property).
12. WHEN a Customer logs in with a guest local Cart, THE Mobile_App SHALL merge the local Cart into the server Cart by summing quantities for matching lines, capped at 20 per line and at available stock, and SHALL clear the local Cart after a successful merge.
13. IF the merge fails or any line is capped or rejected, THEN THE Mobile_App SHALL keep the login successful, retain the unmerged items locally and show which items were not merged.

### Requirement 12: Checkout and Delivery Details

**User Story:** As a customer, I want a clear checkout flow, so that I can review and place my order.

#### Acceptance Criteria

1. WHEN checkout starts, THE Mobile_App SHALL present exactly four steps in order: cart review, delivery details, payment method, confirmation.
2. THE Mobile_App SHALL collect name, phone, email, address, postcode and state as required fields and notes of at most 500 characters as an optional field in the delivery details step.
3. IF the name is shorter than 2 or longer than 100 characters, the phone is not a valid Malaysian number, the email is malformed or longer than 254 characters, the address is shorter than 10 or longer than 255 characters, the postcode is not exactly 5 digits, or the state is not one of the 16 Malaysian states and federal territories, THEN THE Mobile_App SHALL show an inline error next to each invalid field, block progress to payment and retain the entered values.
4. IF the Backend_API receives a checkout request with any delivery field failing criterion 3 or notes longer than 500 characters, THEN THE Checkout_Service SHALL reject the request with HTTP 422 identifying each invalid field and leave the Cart and Orders unchanged.
5. WHERE a default address exists, THE Mobile_App SHALL prefill name, phone, address, postcode and state from the default address and allow editing.
6. IF the idempotency key of a checkout request is missing, shorter than 10 characters or longer than 80 characters, THEN THE Checkout_Service SHALL reject the request with HTTP 422 and leave the Cart and Orders unchanged.
7. IF the Cart has zero items at checkout, THEN THE Checkout_Service SHALL reject the request with HTTP 400 and create no Order.
8. WHEN checkout succeeds, THE Checkout_Service SHALL remove all items from the Cart.
9. WHEN the idempotency key of a checkout request matches a previous successful checkout by the same Customer, THE Checkout_Service SHALL return the original Order result and create no additional Order.

### Requirement 13: Demo Payment

**User Story:** As a tester, I want simulated payment methods and outcomes, so that I can test all payment paths safely.

#### Acceptance Criteria

1. THE Payment_Service SHALL support exactly four Payment_Methods: `card`, `fpx`, `ewallet` and `cod`.
2. WHERE the Payment_Method is `card`, `fpx` or `ewallet`, THE Mobile_App SHALL let the tester choose exactly one simulated Payment_Outcome of `success`, `failed` or `cancelled` before submission.
3. WHEN the Payment_Method is `cod` and the tester confirms, THE Payment_Service SHALL record the payment as `pending_cod`, and THE Checkout_Service SHALL create the Order with payment status `pending_cod` and Fulfilment_Status `placed`.
4. WHEN a payment attempt is submitted, THE Payment_Service SHALL store one Payment_Record with Order ID, method, outcome (or `pending_cod`), amount in sen as a positive integer, UTC timestamp and a Demo_Label flag set to true.
5. WHEN the Payment_Outcome is `success`, THE Checkout_Service SHALL set the payment status to `paid` and the Fulfilment_Status to `placed`, and the reserved stock SHALL stay committed.
6. WHEN the Payment_Outcome is `failed`, THE Checkout_Service SHALL set the payment status to `failed` and the Fulfilment_Status to `payment_failed`, and SHALL release all reserved stock.
7. WHEN the Payment_Outcome is `cancelled`, THE Checkout_Service SHALL set the payment status to `cancelled` and the Fulfilment_Status to `cancelled`, and SHALL release all reserved stock.
8. THE Mobile_App SHALL NOT collect real card numbers, bank credentials or e-wallet credentials.
9. IF a card number field is shown, THEN THE Mobile_App SHALL label the field as a non-functional demo field, SHALL NOT transmit its value and SHALL NOT persist its value after the payment screen closes.
10. WHEN a payment attempt ends, THE Mobile_App SHALL show a result screen within 2 seconds that matches the outcome and carries the Demo_Label, offering "retry payment" only for `failed` and "return to shop" for all outcomes.
11. WHEN a Customer retries payment for an Order in `payment_failed`, THE Payment_Service SHALL create a new Payment_Record without modifying earlier Payment_Records and, on `success`, SHALL re-validate stock for every line before marking the Order paid.
12. IF the stock re-validation fails, THEN THE Payment_Service SHALL keep the Order in `payment_failed`, SHALL NOT mark the Order paid, and THE Mobile_App SHALL show which items are out of stock.
13. IF a payment submission fails because the Backend_API is unreachable or returns an error, THEN THE Mobile_App SHALL show a could-not-process error and leave the Order status and reserved stock unchanged.

### Requirement 14: Order Creation, Stock Deduction and Duplicate Prevention

**User Story:** As a business owner, I want orders created atomically with correct stock, so that we never oversell.

#### Acceptance Criteria

1. WHEN checkout is accepted, THE Checkout_Service SHALL create the Order with an ID of the form `SM-` followed by 10 uppercase alphanumeric characters (A-Z, 0-9) that is unique across all Orders.
2. THE Checkout_Service SHALL create the Order, its lines, its Payment_Record, the stock deductions and the Stock_Adjustments within a single database transaction so that all are created or none are created.
3. IF any line quantity exceeds the available stock, THEN THE Checkout_Service SHALL roll back the transaction, create nothing, leave stock unchanged and respond with HTTP 409 listing each short Product with its available quantity.
4. IF concurrent checkouts compete and the total requested quantity exceeds stock, THEN THE Checkout_Service SHALL fulfil only up to the available stock, reject the remaining checkouts with HTTP 409 and keep stock at 0 or more.
5. FOR ALL Products, stock after successful checkouts SHALL equal initial stock minus the sum of ordered quantities and SHALL never be less than 0 (invariant).
6. IF an idempotency key already used by the same User is repeated, THEN THE Checkout_Service SHALL return the original Order unchanged, create no second Order, deduct no stock and create no new Stock_Adjustments.
7. THE Checkout_Service SHALL copy the product name and unit price into each Order line.
8. WHEN an Order is created, THE Notification_Service SHALL create one Notification for the Customer and one Notification for each Staff_User.
9. WHEN an Order moves to `cancelled` or `payment_failed`, THE Inventory_Service SHALL restore the full quantity of each line to stock and record one Stock_Adjustment per line.
10. IF stock was already restored for an Order and the Order moves to `cancelled` or `payment_failed` again, THEN THE Inventory_Service SHALL change nothing.

### Requirement 15: Order History and Tracking

**User Story:** As a customer, I want to see my orders and their progress, so that I know when to expect delivery.

#### Acceptance Criteria

1. WHEN a Customer opens My Orders, THE Backend_API SHALL return only the Orders of that Customer, newest first, in pages of 20 by default and at most 50, with an indication of a further page.
2. IF the Customer has no Orders, THEN THE Backend_API SHALL return an empty list and THE Mobile_App SHALL show an empty state.
3. WHEN a Customer opens an Order, THE Mobile_App SHALL show lines, delivery details, payment method, payment status, Fulfilment_Status, totals, shipping reference (or an empty placeholder) and the tracking timeline.
4. IF the requested Order does not belong to the Customer or does not exist, THEN THE Backend_API SHALL reject the request with a not-found response and disclose nothing about the Order.
5. WHEN the Fulfilment_Status changes, THE Backend_API SHALL record an order history entry with the new status, actor and timestamp and SHALL retain the entry unmodified.
6. THE Mobile_App SHALL render the timeline Placed, Confirmed, Preparing, Shipped, Delivered from the order history entries, showing reached steps with local date and time and unreached steps as not yet reached.
7. WHEN the Order is `cancelled` or `payment_failed`, THE Mobile_App SHALL show that terminal state with its timestamp in place of the unreached steps and keep the reached steps.
8. WHEN the Customer pulls to refresh or reopens the order screen, THE Mobile_App SHALL reload the status and history and update the display within 3 seconds under normal conditions.
9. IF the reload fails, THEN THE Mobile_App SHALL keep the last loaded data and show a refresh-failed indication with a retry action.
10. WHERE the Order has a Production_Job, THE Backend_API SHALL expose the Production_Status to the Customer as a read-only label separate from the Fulfilment_Status, and THE Mobile_App SHALL display the label separately from the timeline.

### Requirement 16: Custom Orders (Customer Side)

**User Story:** As a customer, I want to request a bespoke handcrafted item, so that artisans can make something for me.

#### Acceptance Criteria

1. WHEN a Customer submits a Custom_Order with a product type of 1 to 100 characters, a description of 10 to 2000 characters, a whole-number quantity of 1 to 500 and a preferred date of today or later, THE Custom_Order_Service SHALL create the Custom_Order with Custom_Order_Status `submitted` and return it within 3 seconds.
2. WHERE reference images are attached, THE Custom_Order_Service SHALL accept up to 5 images, each PNG, JPEG or WebP and at most 5 MB, and SHALL store each under a unique generated filename.
3. IF an image has another type, exceeds 5 MB, or would exceed 5 attachments, THEN THE Custom_Order_Service SHALL reject the request with HTTP 422 stating the violated rule and SHALL create and store nothing.
4. WHEN a Custom_Order is created, THE Notification_Service SHALL create one unread Notification per Staff_User within 10 seconds.
5. WHEN a Customer opens Custom Orders, THE Mobile_App SHALL list only the Custom_Orders of that Customer, newest first, showing product type, quantity, preferred date and status.
6. WHEN a Staff_User sets an estimated price or a status, THE Mobile_App SHALL show the estimate and the latest status in the Customer's list.
7. IF the Customer has no Custom_Orders, THEN THE Mobile_App SHALL show an empty state.
8. IF the preferred date is earlier than today, the quantity is outside 1 to 500 or not whole, the description is shorter than 10 characters, or a required field is missing, THEN THE Custom_Order_Service SHALL reject the request with HTTP 422 identifying each invalid field and SHALL create nothing.

### Requirement 17: Notifications

**User Story:** As a user, I want in-app notifications, so that I stay informed about orders and requests.

#### Acceptance Criteria

1. THE Notification_Service SHALL persist each Notification with recipient, title of 1 to 100 characters, body of 1 to 500 characters, type, optional related entity, created time and a read flag that defaults to unread.
2. WHEN the Fulfilment_Status of an Order changes, THE Notification_Service SHALL create exactly one order-type Notification for the owning Customer referencing the Order within 5 seconds.
3. WHEN the Custom_Order_Status of a Custom_Order changes, THE Notification_Service SHALL create exactly one custom-order Notification for the owner within 5 seconds.
4. IF a status is set to the value it already holds, THEN THE Notification_Service SHALL create no Notification.
5. WHEN the stock of a Product falls to or below its Low_Stock_Threshold, THE Notification_Service SHALL create one low-stock Notification per Staff_User, except for Staff_Users who already have an unread low-stock Notification for that Product.
6. WHEN a User opens the notifications list, THE Backend_API SHALL return only the Notifications of that User, newest first, with the unread count.
7. WHEN a User marks one Notification or all Notifications as read, THE Backend_API SHALL set the read flag only on the targeted Notifications of that User, persist the flag across restarts and return the updated unread count.
8. IF a Notification does not exist or belongs to another User, THEN THE Backend_API SHALL reject the request with a not-found response and leave all read flags unchanged.
9. WHILE the unread count is greater than 0, THE Mobile_App SHALL show a badge with the count on the notifications entry of each navigation, and SHALL show "99+" when the count is above 99.
10. WHILE the unread count is 0, THE Mobile_App SHALL hide the badge.
11. THE Notification_Service SHALL NOT send e-mail, SMS or push messages in this prototype.

### Requirement 18: Customer Navigation

**User Story:** As a customer, I want simple navigation, so that I reach every customer feature.

#### Acceptance Criteria

1. WHILE a Customer uses the Mobile_App, THE Mobile_App SHALL show a bottom bar with exactly five destinations in the order Home, Shop, Favourites, Cart, Profile.
2. WHEN a destination is selected, THE Mobile_App SHALL show its screen within 300 ms and mark it as the single selected destination.
3. THE Mobile_App SHALL provide a navigable route for product details, checkout, payment, order confirmation, My Orders, order tracking, notifications, custom orders and About.
4. WHILE the Cart contains 1 to 99 items, THE Mobile_App SHALL show the item count as a numeric badge on the Cart destination.
5. WHILE the Cart contains more than 99 items, THE Mobile_App SHALL show "99+" on the Cart badge.
6. WHILE the Cart is empty, THE Mobile_App SHALL hide the Cart badge.
7. WHEN a signed-out Customer selects Favourites, Cart checkout, Profile or My Orders, THE Mobile_App SHALL open the login screen and, after sign-in, show the requested destination.
8. IF the Customer cancels or exits the login screen, THEN THE Mobile_App SHALL return to the previous screen and SHALL NOT show the restricted destination.

### Requirement 19: Seller/Admin Navigation and Dashboard

**User Story:** As a seller, I want a dashboard of live business numbers, so that I can run daily operations.

#### Acceptance Criteria

1. WHILE a Staff_User is signed in, THE Mobile_App SHALL show a bottom bar with exactly five items in the order Dashboard, Orders, Products, Production, More, where More lists exactly Inventory, Artisans, Analytics, Forecasting, Notifications and Settings in that order.
2. WHEN Dashboard opens, THE Analytics_Service SHALL return within 3 seconds the KPIs total revenue, order count, pending orders, AOV (0 if there are no Orders), low-stock count and open production jobs, computed from Database records.
3. THE Analytics_Service SHALL return the chart series sales by month (last 12 calendar months, months with zero sales included), orders by status (one value per Fulfilment_Status), best-selling products (top 5 by units, excluding Orders in `cancelled` or `payment_failed`) and inventory distribution by category.
4. THE Mobile_App SHALL render each series as a chart with labelled axes or a legend and SHALL expose the values as text for screen readers.
5. WHEN a new Order is placed, THE Analytics_Service SHALL include the Order in every Dashboard response requested after the Order is saved.
6. THE Analytics_Service SHALL exclude Orders with Fulfilment_Status `cancelled` or `payment_failed` from revenue, AOV and sales by month.
7. WHERE demo data exists, THE Mobile_App SHALL show a Demo_Label on the Dashboard.
8. IF Analytics fails or does not respond within 10 seconds, THEN THE Mobile_App SHALL show a could-not-load error with a retry action and keep the previously displayed values.
9. IF no Orders, products or production jobs exist, THEN THE Mobile_App SHALL show every KPI as 0 (displayed as RM 0.00 for revenue and AOV) and an empty state in place of each chart.

### Requirement 20: Product Management

**User Story:** As a seller, I want to manage products, so that the shop catalogue stays accurate.

#### Acceptance Criteria

1. WHEN a Staff_User submits a valid new Product (name of 1 to 200 characters, description of 0 to 2000 characters, existing category, price as integer sen from 1 to 99,999,999, stock as integer from 0 to 999,999, Low_Stock_Threshold as integer from 0 to 999,999, 0 to 20 optional Variations and an optional Artisan link), THE Catalogue_Service SHALL create the Product and return it within 2 seconds.
2. WHEN a Staff_User updates a Product with valid values, THE Catalogue_Service SHALL save the changes, set the update time and return the Product within 2 seconds.
3. WHEN a Staff_User deactivates an active Product, THE Catalogue_Service SHALL hide the Product from customer listings and search while retaining the Product in existing Orders and reports.
4. WHEN a Staff_User reactivates a Product, THE Catalogue_Service SHALL show the Product in customer listings and search again.
5. WHERE a Staff_User uploads a product image, THE Catalogue_Service SHALL accept PNG, JPEG or WebP files of at most 5 MB and associate the image with the Product.
6. IF the uploaded image has another type or exceeds 5 MB, THEN THE Catalogue_Service SHALL reject the upload with an error and leave the existing images unchanged.
7. IF the price is 0 or less, the stock is negative, the threshold is negative, the name is missing or too long, or the category is unknown, THEN THE Catalogue_Service SHALL reject the request with HTTP 422 identifying each invalid field and leave data unchanged.
8. WHEN a Staff_User deletes a Product that appears in no Order, THE Catalogue_Service SHALL permanently delete the Product.
9. IF a Staff_User deletes a Product that appears in at least 1 Order, THEN THE Catalogue_Service SHALL respond with HTTP 409 recommending deactivation and retain the Product.
10. IF a non-Staff User calls a product management endpoint, THEN THE RBAC_Guard SHALL respond with HTTP 403 and change nothing.
11. THE Mobile_App SHALL provide Staff_Users with a product list, a name search field, a create form and an edit form.
12. IF the Backend_API rejects a product create or edit, THEN THE Mobile_App SHALL show the reason, retain the form values and keep the form open.

### Requirement 21: Inventory Management

**User Story:** As a seller, I want to track and adjust stock, so that I can avoid stock-outs.

#### Acceptance Criteria

1. WHEN a Staff_User requests inventory for a Product, THE Inventory_Service SHALL return the stock, the Low_Stock_Threshold and a low-stock flag that is true if stock is at or below the threshold.
2. WHEN a Stock_Adjustment with a non-zero integer delta from -999,999,999 to 999,999,999 and a reason of 1 to 255 characters is submitted, THE Inventory_Service SHALL update the stock and store the delta, reason, actor and timestamp.
3. IF a Stock_Adjustment would make stock negative, THEN THE Inventory_Service SHALL reject the request with HTTP 409 stating insufficient stock, leave stock unchanged and store nothing.
4. IF the delta is 0, not an integer or out of range, or the reason is missing, empty or longer than 255 characters, THEN THE Inventory_Service SHALL reject the request identifying the invalid field and change nothing.
5. WHEN a Low_Stock_Threshold is updated to an integer from 0 to 999,999,999, THE Inventory_Service SHALL save the threshold and apply the threshold to all subsequent flags.
6. IF the threshold is negative, not an integer or above 999,999,999, THEN THE Inventory_Service SHALL reject the request identifying the field and keep the previous threshold.
7. WHEN a Staff_User opens the adjustment history of a Product, THE Inventory_Service SHALL return the Stock_Adjustments newest first, including those created by orders and cancellations, or an empty list if none exist.
8. FOR ALL Products, current stock SHALL equal opening stock plus the sum of all Stock_Adjustment deltas (invariant).
9. WHILE any Product has the low-stock flag set, THE Mobile_App SHALL show a low-stock alert for each such Product on the Inventory screen and an indicator with the count on the Dashboard.

### Requirement 22: Order Management

**User Story:** As a seller, I want to process orders through fulfilment, so that customers receive their items.

#### Acceptance Criteria

1. WHEN the Orders screen opens, THE Backend_API SHALL return a paginated list of Orders (default 20, maximum 100) newest first.
2. WHERE a Fulfilment_Status filter is supplied, THE Backend_API SHALL return only the matching Orders.
3. WHERE a text search of 1 to 100 characters is supplied, THE Backend_API SHALL return Orders whose Order ID or customer name contains the text, compared case-insensitively.
4. IF the filter value is not one of `placed`, `confirmed`, `preparing`, `shipped`, `delivered`, `cancelled` or `payment_failed`, THEN THE Backend_API SHALL reject the request with an invalid-filter error and return no Orders.
5. WHEN a Staff_User confirms a `placed` Order, THE Backend_API SHALL set the Fulfilment_Status to `confirmed`.
6. THE Backend_API SHALL allow Fulfilment_Status transitions only in the sequence `placed` → `confirmed` → `preparing` → `shipped` → `delivered`, and cancellation from `placed`, `confirmed` or `preparing`.
7. IF a requested transition is outside the allowed sequence, THEN THE Backend_API SHALL reject the request with HTTP 409 naming the current and requested statuses and leave the status unchanged.
8. WHEN a Staff_User sets an Order to `shipped`, THE Backend_API SHALL require a shipping reference of 3 to 80 characters.
9. IF the shipping reference is missing or outside 3 to 80 characters, THEN THE Backend_API SHALL reject the request with a length-requirement error and leave the Order unchanged.
10. IF a Staff_User cancels an Order that is `shipped`, `delivered` or already `cancelled`, THEN THE Backend_API SHALL reject the request with HTTP 409 and leave the status and the stock unchanged.
11. WHEN a Staff_User cancels an Order, THE Backend_API SHALL require a reason of 3 to 500 characters, record the reason and restore stock under Requirement 14.9.
12. WHEN the Fulfilment_Status changes, THE Backend_API SHALL append an order history record with the previous status, new status, acting Staff_User and time, and THE Notification_Service SHALL create the Customer Notification per Requirement 17.2.
13. WHEN a status update is requested for an Order created by the earlier prototype with stored status `packing`, THE Backend_API SHALL treat the stored status as `preparing` when validating the transition.

### Requirement 23: Artisan Management

**User Story:** As an admin, I want to manage artisan profiles, so that work can be assigned fairly while privacy is protected.

#### Acceptance Criteria

1. WHEN a Staff_User creates or edits an Artisan with a name of 1 to 100 characters, a specialisation of 1 to 100 characters and an availability of `available`, `busy` or `unavailable`, THE Artisan_Service SHALL save the profile and return it within 2 seconds.
2. IF the name or specialisation is missing or empty, the availability is invalid, or a field exceeds its maximum length, THEN THE Artisan_Service SHALL reject the request indicating each invalid field and leave data unchanged.
3. WHEN a Staff_User requests the profile of an Artisan, THE Artisan_Service SHALL return the assigned Products and the counts (integers of 0 or more) of open and completed Production_Jobs.
4. THE Artisan_Service SHALL store private contact details (phone, email, address) of Artisans and SHALL return them only to Staff_Users.
5. WHEN a Customer or visitor requests an Artisan, THE Artisan_Service SHALL return only the public name, specialisation and story text (0 to 2000 characters) and SHALL omit phone, email, address, availability and job counts.
6. IF an Artisan with at least 1 open Production_Job is set to `unavailable`, THEN THE Artisan_Service SHALL save the change and return a warning listing the identifier of each open job.
7. WHEN a Staff_User links or unlinks a Product and an Artisan, THE Catalogue_Service SHALL save the association and return the updated assigned Products.
8. IF a Customer or visitor requests private contact details of an Artisan, THEN THE RBAC_Guard SHALL deny the request with HTTP 403 and return no phone, email or address.

### Requirement 24: Production Tracking

**User Story:** As a seller, I want to track production separately from delivery, so that I know what is being made and when.

#### Acceptance Criteria

1. WHEN an Order is confirmed, THE Production_Service SHALL create one Production_Job with Production_Status `order_confirmed` per order line whose Product is made to order or whose quantity exceeds the available finished stock.
2. WHEN a Staff_User manually creates a job for an order line, THE Production_Service SHALL create the Production_Job with Production_Status `order_confirmed`.
3. WHEN a Staff_User assigns an Artisan to a Production_Job in `order_confirmed`, THE Production_Service SHALL set Production_Status `production_assigned` and store the quantity (1 to 999,999), deadline, priority (`low`, `normal`, `high` or `urgent`, default `normal`) and notes (0 to 1000 characters).
4. THE Production_Service SHALL allow Production_Status transitions only in the sequence `order_confirmed` → `production_assigned` → `in_production` → `quality_checking` → `completed` → `ready_for_fulfilment`, plus the return from `quality_checking` to `in_production`.
5. IF a requested Production_Status transition is outside the allowed sequence, THEN THE Production_Service SHALL reject the request with HTTP 409 indicating the current and requested statuses and leave the status unchanged.
6. WHEN a Staff_User or the assigned Artisan_User submits progress, THE Production_Service SHALL accept a whole-number percentage from 0 to 100 and store it with a server timestamp and a note of 0 to 500 characters.
7. IF the percentage is outside 0 to 100 or not whole, or is submitted by an unassigned Artisan_User, THEN THE Production_Service SHALL reject the request (HTTP 422 for an invalid percentage, HTTP 403 for an unassigned Artisan_User) and leave the progress unchanged.
8. IF a deadline is earlier than the current date in the time zone of the Seller, THEN THE Production_Service SHALL reject the request with HTTP 422 naming the deadline field and leave the Production_Job unchanged.
9. WHILE the current date is later than the deadline of a Production_Job and the Production_Status is neither `completed` nor `ready_for_fulfilment`, THE Production_Service SHALL flag the job as overdue in list responses.
10. THE Production_Service SHALL store Production_Status and Fulfilment_Status as separate fields, and a change to one SHALL NOT automatically change the other.
11. WHEN a Production_Job changes to `ready_for_fulfilment`, THE Notification_Service SHALL create one Notification for staff suggesting that the Order may move to `preparing` or `shipped`, and THE Production_Service SHALL leave the Fulfilment_Status unchanged.
12. THE Mobile_App SHALL display Production_Jobs in a list view and in a board view grouped by Production_Status, filterable by status, Artisan and priority combined with AND.
13. IF no Production_Job matches the filters, THEN THE Mobile_App SHALL show an empty state with an action to clear the filters.

### Requirement 25: Custom-Order Management (Seller Side)

**User Story:** As a seller, I want to review and fulfil custom requests, so that bespoke work is priced and made.

#### Acceptance Criteria

1. WHEN a Staff_User opens custom orders, THE Custom_Order_Service SHALL list all Custom_Orders newest first in pages of 20, or an empty list with a total of 0 if none exist.
2. WHEN a status filter is selected, THE Custom_Order_Service SHALL list only the Custom_Orders with the matching Custom_Order_Status.
3. WHEN a Staff_User accepts a Custom_Order in status `submitted` with an estimated price as integer sen from 1 to 99,999,999, THE Custom_Order_Service SHALL set the status `accepted`, store the estimate and respond within 2 seconds.
4. IF the estimated price is missing, not an integer, less than 1 or greater than 99,999,999, THEN THE Custom_Order_Service SHALL reject the request with a validation error and leave the status and estimate unchanged.
5. WHEN a Staff_User rejects a Custom_Order in status `submitted` with a reason of 5 to 500 characters after trimming, THE Custom_Order_Service SHALL set the status `rejected` and store the reason.
6. IF the rejection reason is missing or outside 5 to 500 characters after trimming, THEN THE Custom_Order_Service SHALL reject the request with a validation error and leave the status unchanged.
7. WHEN a Staff_User assigns an active Artisan to a Custom_Order in status `accepted` that has no existing assignment, THE Custom_Order_Service SHALL store the assignment and create exactly one linked Production_Job, persisting both or neither.
8. IF the Artisan does not exist or is not active, or the Custom_Order is not in status `accepted`, THEN THE Custom_Order_Service SHALL reject the request with an error, create no Production_Job and leave the Custom_Order unchanged.
9. WHEN the progress of the linked Production_Job changes, THE Mobile_App SHALL show the updated progress label in the Customer's view within 5 seconds.
10. THE Custom_Order_Service SHALL allow only the transitions `submitted` → `accepted`, `submitted` → `rejected`, `accepted` → `in_progress` and `in_progress` → `completed`, and SHALL respond to any other transition (for example `rejected` → `accepted`) with HTTP 409 and a not-allowed error and leave the status unchanged.

### Requirement 26: Sales Analytics

**User Story:** As a seller, I want sales analytics, so that I can see trends and top and weak performers.

#### Acceptance Criteria

1. WHEN analytics for a date range are requested, THE Analytics_Service SHALL return total revenue, order count and AOV, where AOV is total revenue divided by order count, as integer sen, and RM formatting with 2 decimals is a display concern only.
2. THE Analytics_Service SHALL return revenue and order count for each calendar month overlapping the range, including months with zero values, in chronological order.
3. THE Analytics_Service SHALL return the top 5 and the bottom 5 Products by units sold, with the top list in descending order, the bottom list in ascending order, and ties ordered by name ascending.
4. IF the start of the range is after the end, THEN THE Analytics_Service SHALL reject the request with HTTP 422 and an invalid-range error and return no data.
5. IF no Orders exist in the range, THEN THE Analytics_Service SHALL return revenue 0, order count 0, AOV 0, zero-valued monthly entries and empty top and bottom lists without error.
6. IF the range exceeds 24 months, THEN THE Analytics_Service SHALL reject the request with a validation error indicating the maximum and return no data.
7. FOR ALL valid ranges, the sum of monthly revenue SHALL equal total revenue exactly (invariant).

### Requirement 27: AI Demand Forecasting

**User Story:** As a seller, I want a demand forecast with honest accuracy figures, so that I can plan replenishment.

#### Acceptance Criteria

1. WHEN a forecast is requested for a Product, THE Forecasting_Service SHALL build the monthly unit-sales history from Order records using pandas and NumPy, summing units per calendar month and recording 0 for months between the first and last month that have no Orders.
2. THE Forecasting_Service SHALL produce forecasts for the next 3 calendar months from both the Baseline_Model and the Candidate_Model.
3. WHEN a Product has at least 6 months of history, THE Forecasting_Service SHALL run a Backtest that holds out the most recent 2 months, trains on the remaining months, and reports MAE and RMSE for both models in units rounded to 2 decimals.
4. IF a Product has fewer than 6 months of history, THEN THE Forecasting_Service SHALL return the Baseline_Model forecast only, with no Candidate_Model forecast, no MAE and no RMSE, and SHALL indicate that evaluation is unavailable due to insufficient history.
5. WHEN a Backtest completes, THE Forecasting_Service SHALL select the model with the lower MAE (the Baseline_Model if the MAE values are equal) and report the name of the selected model.
6. WHERE the history comes from the Seed_Script, THE Forecasting_Service SHALL include `synthetic: true` in the response, and THE Mobile_App SHALL show a Synthetic_Data notice on the forecast screen.
7. IF current stock is less than the forecast demand for the next month plus the Low_Stock_Threshold, THEN THE Forecasting_Service SHALL flag the Product for replenishment; otherwise THE Forecasting_Service SHALL NOT flag the Product.
8. THE Forecasting_Service SHALL return a methodology description stating the data used, the models, the evaluation approach and the limitations, each as a separate non-empty statement.
9. THE Forecasting_Service SHALL include no accuracy figure other than the Backtest MAE and RMSE computed for the same response.
10. WHEN the forecast response is received, THE Mobile_App SHALL show history and predictions together in one chart, the MAE and RMSE, the replenishment flag and the methodology text.
11. IF no Order history exists or the calculation fails, THEN THE Forecasting_Service SHALL return an error indicating the reason, and THE Mobile_App SHALL show an error and no chart or metrics.
12. FOR ALL forecast outputs, every predicted quantity SHALL be greater than or equal to 0.
13. FOR ALL equal inputs, THE Forecasting_Service SHALL return equal outputs, including forecasts, MAE, RMSE and the selected model (determinism).

### Requirement 28: API Quality and Error Handling

**User Story:** As a client developer, I want consistent, documented API behaviour, so that the app handles errors predictably.

#### Acceptance Criteria

1. THE Backend_API SHALL validate the request body and every query parameter against typed schemas before processing.
2. IF validation fails, THEN THE Backend_API SHALL reject the request without changing data and return JSON with `error.code`, `error.message` and `error.details` listing each failing field with a reason.
3. IF an error other than a validation error occurs, THEN THE Backend_API SHALL return JSON with `error.code` and `error.message`.
4. IF an unexpected exception occurs, THEN THE Backend_API SHALL log the exception server-side, roll back uncommitted changes and respond with HTTP 500 and a generic message that contains no stack trace, file path, SQL text or exception class name.
5. THE Backend_API SHALL serve OpenAPI documentation at `/docs` and the schema at `/openapi.json`, each with HTTP 200, describing every public endpoint.
6. WHEN `/api/health` is requested without credentials, THE Backend_API SHALL respond with HTTP 200 within 1 second with the service status and a boolean Demo mode flag.
7. THE Backend_API SHALL use parameterised SQL for every query with external input and SHALL NOT concatenate or interpolate external input into SQL text.
8. THE Backend_API SHALL return list endpoints in an envelope with `items`, `total` (0 or more), `limit` (1 to 100, default 20) and `offset` (0 or more, default 0).
9. IF `limit` is outside 1 to 100 or `offset` is less than 0, THEN THE Backend_API SHALL reject the request per criterion 2.

### Requirement 29: Demo Data and Seed Script

**User Story:** As a tester, I want rich repeatable demo data, so that every screen and the full scenario can be exercised.

#### Acceptance Criteria

1. WHEN the Seed_Script runs against an empty Database, THE Seed_Script SHALL create at least 15 Products with at least 2 in each of tote bags, fabric books, toys, gifts and accessories, each with a demo price greater than 0 and stock from 0 to 500.
2. THE Seed_Script SHALL create at least 3 demo Customers, at least 1 Seller, at least 1 Admin, at least 1 Artisan_User and at least 4 Artisan profiles.
3. THE Seed_Script SHALL create at least 1 Order in each Fulfilment_Status, at least 1 Production_Job in each Production_Status, at least 1 Custom_Order and at least 3 Notifications.
4. THE Seed_Script SHALL create inventory levels with at least 2 Products at or below their low-stock threshold and at least 5 Products above their threshold.
5. THE Seed_Script SHALL create Synthetic_Data sales history covering at least 12 consecutive months ending on the run date, with at least 1 sale in each month.
6. THE Seed_Script SHALL mark every created record as demo data, and WHILE a record is marked as demo data, THE Mobile_App SHALL show the Demo_Label on every screen displaying the record.
7. IF the Seed_Script runs against a Database that already contains seeded data, THEN THE Seed_Script SHALL make no changes, exit with a non-zero code and print a message that seeded data exists.
8. WHERE the `--reset` option is supplied, THE Seed_Script SHALL prompt for an explicit confirmation word before deleting any record, and SHALL delete and re-seed only records marked as demo data.
9. IF anything other than the exact confirmation word is typed, THEN THE Seed_Script SHALL delete nothing, change nothing and exit with a reset-cancelled message.
10. THE Seed_Script SHALL read each demo account password from an environment variable, otherwise use a documented demo password of at least 8 characters, and the README SHALL list all demo credentials as demo-only.
11. THE Seed_Script SHALL insert the 4 products from `assets/products.json` with their existing identifiers preserved, and the 4 products SHALL count toward the 15 Products of criterion 1.
12. IF seeding fails part-way, THEN THE Seed_Script SHALL roll back everything from that run, exit with a non-zero code and print the cause.

### Requirement 30: End-to-End Demo Scenario

**User Story:** As a presenter, I want the full scenario to work in sequence, so that I can demonstrate the platform.

#### Acceptance Criteria

1. WHEN a Customer logs in, browses products, adds an in-stock product to the Cart and checks out with a successful demo payment, THE Platform SHALL create exactly one Order with the Cart items and payment status `paid`, empty the Cart and decrease product stock by the ordered quantities within 5 seconds of checkout completion.
2. WHEN the Order is created, THE Platform SHALL list the Order for Staff_Users within 5 seconds with the same items, quantities, total and status as in the view of the Customer.
3. WHEN a Staff_User confirms the Order and assigns a Production_Job to an Artisan, THE Platform SHALL set the status `confirmed`, create exactly one Production_Job linked to the Order and the Artisan, and show the Production_Job to that Artisan_User.
4. WHEN a Staff_User updates production progress to a value from 0 to 100, THE Platform SHALL store the progress and show it on the tracking view of the Customer within 5 seconds.
5. WHEN a Staff_User sets a non-empty shipping reference of at most 80 characters (consistent with Requirement 22) and the status `shipped`, THE Platform SHALL store both and show both on the tracking view within 5 seconds.
6. WHEN the Dashboard is opened after the status `shipped`, THE Analytics_Service SHALL include the Order in the KPIs revenue, order count and shipped order count, each increased by the contribution of the Order.
7. WHEN the scenario completes, THE Analytics_Service SHALL include the new Order in revenue, order count and the best-seller series, with revenue increased by the Order total, order count increased by 1, and the sold quantity of each ordered product increased by the ordered quantity.
8. IF any step of the scenario fails, THEN THE Platform SHALL return an error identifying the failed step, leave the data of completed steps unchanged and execute no subsequent steps.
9. THE Platform SHALL provide an automated backend test that executes steps 1 to 7 through the HTTP API, asserts each outcome and fails on any failed assertion.

### Requirement 31: Automated Testing

**User Story:** As a maintainer, I want automated tests, so that regressions are caught.

#### Acceptance Criteria

1. THE Platform SHALL include Python backend tests with, for each of authentication, RBAC, product CRUD, search and filter, cart calculations, insufficient stock, checkout, payment outcomes, order creation, stock deduction, order history, status updates, production, notifications, forecasting and error handling, at least 1 success-path test and at least 1 failure-path test.
2. THE Platform SHALL include Flutter unit or widget tests with at least 1 test each for money formatting, form validators, cart state, the login form, role-based navigation, error state display and empty state display.
3. THE Platform SHALL include property-based tests for the invariants and round-trip properties in Requirements 11, 14, 21, 26 and 27, each executed for a minimum of 100 generated inputs per run.
4. WHEN a property-based test fails, THE test runner SHALL report the failing or minimised input.
5. THE Backend_API tests SHALL use an isolated temporary Database per run and SHALL NOT modify the development Database.
6. WHEN a test run finishes, whether passed or failed, THE test runner SHALL delete the temporary Database.
7. THE README SHALL report test results only for runs actually executed, stating the exact command, the passed count, the failed count and the date.

### Requirement 32: Documentation and Deliverables

**User Story:** As a student team member, I want clear documentation, so that anyone can run, build and assess the prototype.

#### Acceptance Criteria

1. THE README SHALL describe Windows and VS Code setup as an ordered numbered sequence including prerequisites, Python virtual environment creation, installing `backend/requirements.txt`, installing Flutter dependencies, and database migration and seeding, with a command for each step.
2. THE README SHALL describe, for web, Android emulator and physical Android device, the commands to start the Backend_API and the Mobile_App together, the host address to use, and how to set `API_BASE_URL`.
3. THE README SHALL describe the APK build steps as an ordered numbered sequence including the build command and the APK location.
4. THE README SHALL list at least 1 demo credential per Role, each labelled "demo-only", with a statement that the credentials must not be used in production.
5. THE README SHALL contain a feature completion checklist with exactly one row for each of Requirements 1 to 33, each row marked "complete", "partial" or "not done".
6. IF a checklist row is marked "partial" or "not done", THEN THE README SHALL state the reason and what is not implemented.
7. THE README SHALL document limitations with a separate entry each for simulated payments, no courier integration, no e-mail delivery, no push delivery, synthetic forecasting data and SQLite scale limits, each stating what the prototype does instead.
8. THE README SHALL document commercial-use changes with a separate entry each for a real payment gateway, courier APIs, a production database, hosted secrets management, image rights and permissions, PDPA compliance, HTTPS and an independent security review, each stating the change required.
9. THE `backend/requirements.txt` SHALL list every imported Python package with a version constraint, and `pubspec.yaml` SHALL list every imported Flutter package.
10. WHEN a team member follows the README in order on a clean Windows machine that has the prerequisites, THE README SHALL enable the team member to start both the Backend_API and the Mobile_App and log in with a demo credential with no undocumented step.

### Requirement 33: Security and Privacy

**User Story:** As a user, I want my data protected, so that the prototype follows basic good practice.

#### Acceptance Criteria

1. IF the age of a Session_Token exceeds the configured lifetime (default 7 days, configurable from 1 hour to 30 days), THEN THE Backend_API SHALL reject the request as unauthenticated with a session-expired error and leave data unchanged.
2. THE Backend_API SHALL include the header `X-Content-Type-Options: nosniff` on 100% of responses, including error responses.
3. WHEN a file is uploaded, THE Backend_API SHALL accept the file only if the extension and the content signature match the same allowed type (JPEG, PNG or WebP) and the size is at most 5 MB.
4. IF the extension is not allowed, the content signature does not match an allowed type or the extension, or the size exceeds 5 MB, THEN THE Backend_API SHALL reject the upload with a reason and store nothing.
5. THE Backend_API SHALL exclude password hashes, token hashes and Artisan private contact details from all log output at every log level.
6. WHEN the Mobile_App is first launched and WHEN the registration screen opens, THE Mobile_App SHALL show a notice that only fictional personal data should be entered, visible without scrolling on the registration screen.
7. IF `DEMO_MODE` is not `1` (including unset or empty), THEN THE Backend_API SHALL reject every payment request with HTTP 503 stating that real payments are not configured, create no Payment_Record and alter no Order state.
