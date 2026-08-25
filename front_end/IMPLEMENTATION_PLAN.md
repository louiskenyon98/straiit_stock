# Straiit Stock Portal implementation plan

## Objective

Implement the Claude-designed Straiit Stock Portal as a production-quality, responsive frontend backed by the existing product-import database.

The existing visual system remains the design reference, while the database and backend schema are the source of truth for product data and supported behaviour.

## Current implementation status

- The public catalogue release is implemented.
- The buyer workflow is implemented using a separate transactional `api/portal.db` database.
- Account applications require explicit approval through `api/manage.py`.
- Approved users can sign in, submit product-specific and wanted-stock requests, view organisation requests, and sign out.
- Operator web administration is implemented at `/admin` with role-based access.
- Durable SMTP notifications and one-time password recovery are implemented.
- Offline payment is operator-confirmed; no card-payment provider is required.
- Concurrency-safe portal reservations allocate imported product quantity without mutating the importer database.

## Existing assets

- Frontend design prototype: `Straiit Stock Portal.dc.html`
- Design-system tokens and components: `_ds/industry-293dea9d-1038-4271-a137-785839d1b78f/styles.css`
- Backend importer: `../back_end/product_importer/ingest.py`
- SQLite database: `../back_end/product_importer/products.db`
- Extracted product media: `../back_end/product_importer/media/`
- Backend documentation: `../back_end/product_importer/README.md`

## Backend findings

The current backend is a Python ingestion pipeline and populated SQLite database. It is not yet an HTTP API or authentication service.

The database contains:

- 66 imported source files
- 29,784 products exposed through `website_products`
- 29,271 product-image associations
- 28,772 products with a primary image
- 28,574 products with wholesale pricing
- 8,836 products with an explicit quantity
- 7,540 products with a normalized category
- 13,101 products with a status
- 92 variant rows belonging to 18 products
- 7,681 products with brand, name, positive quantity, wholesale price, and image

The database supports the following product information when present:

- Brand, product name, category, model, SKU, and barcode
- Description, colour, size, gender, and material
- Quantity, wholesale price, retail price, and native currency
- Availability status and offer type
- Product images
- Origin, HS code, grade, model year, and collection
- Eyewear-specific measurements and attributes
- Size variants for products with `product_variants` rows
- Supplier-specific fields in `attributes_json`, including MOQ price tiers

The schema does not currently include:

- Users, organisations, sessions, or account approvals
- Demand requests, quotes, or reservations
- Warehouses
- Carton or pallet counts
- A first-class stock-lot entity

## Required adaptation of the design

The design is lot- and pallet-oriented, while the database is product-offer-oriented. The visual language will be preserved, but content will be changed to match real data.

| Claude design | Database-backed implementation |
| --- | --- |
| Stock lots | Product offers |
| Lot code | Product ID, SKU, or model |
| SKU breakdown on every lot | Variant table only when variants exist |
| Cartons and pallets | Omit because they are not stored |
| Warehouse location | Omit because it is not stored |
| Nine-warehouse claim | Remove from copy and statistics |
| One lot-level MOQ | Show supplier MOQ price tiers when available |
| Prototype status labels | Map actual database statuses |
| Placeholder lot photograph | Real primary image and optional gallery |
| Ten hard-coded lots | Paginated database results |
| Client-side currency conversion | Display the database's native currency |
| Authenticated price masking | Defer until authentication exists |
| Demand requests and reservations | Use the separate transactional portal schema and APIs |

Database status codes will be presented as readable labels:

- `AVAILABLE` -> Available
- `LAST_PIECES` -> Last pieces
- `PREORDER` -> Pre-order
- `BACKORDER` -> Back order
- `NOT_AVAILABLE` -> Not available

## Implementation phases

### 1. Create a read-only catalogue API

Add a thin Python web API beside the importer. It will read the existing SQLite schema without changing or duplicating imported catalogue data.

Recommended endpoints:

- `GET /api/catalogue/summary`
- `GET /api/products`
- `GET /api/products/:id`
- `GET /api/products/:id/images`
- `GET /api/brands`
- `GET /api/categories`
- `GET /media/...`

The product-list endpoint will support:

- Server-side pagination
- Search across brand, name, model, SKU, and barcode
- Brand, category, status, gender, currency, and in-stock filters
- Sorting by name, brand, quantity, wholesale price, retail price, and import date
- Stable query parameters so filtered catalogue views are linkable

The API will query `website_products` and join `product_variants` and `product_images` where needed. It must not expose absolute supplier paths, raw PDF text, or unfiltered `attributes_json`.

### 2. Add an API presentation layer

Normalize imported supplier data at the API boundary without mutating the importer schema:

- Merge brand names case-insensitively for filtering and summaries.
- Normalize category capitalization and clear duplicate values.
- Translate status codes to display labels.
- Keep missing quantity distinct from zero quantity.
- Select a safe allow-list of useful supplier attributes.
- Extract and structure supplier MOQ price tiers.
- Convert stored relative image paths into media URLs.
- Return capability flags such as `hasQuantity`, `hasVariants`, and `hasMultipleImages`.
- Return consistent numeric and nullable field types.

### 3. Scaffold the frontend

- Use React, TypeScript, and Vite.
- Use React Router for route-level navigation.
- Use TanStack Query for API requests, caching, and loading/error states.
- Use Lucide React at a 1.5 stroke width.
- Configure environment-based API URLs.
- Configure a development proxy for `/api` and `/media`.
- Add linting, formatting, unit-test, type-check, and production-build commands.

### 4. Convert the design system

Preserve the exported Industry design direction:

- Steel-blue monochrome palette
- Barlow Condensed headings and Barlow body text
- Square corners and hairline borders
- Blueprint registration marks
- Duotone product imagery
- Technical tables, tags, fields, segmented controls, dialogs, and toasts

Extract the prototype's inline styles into reusable tokens and component styles. Build reusable primitives including:

- `Button`
- `BlueprintFrame`
- `Tag`
- `Field`
- `Select`
- `DataTable`
- `Modal`
- `Toast`
- `DuotoneImage`
- Pagination and filter controls
- Loading skeleton, empty state, and error state

### 5. Implement the application routes

#### `/` - Overview

- Use real catalogue summary data.
- Show meaningful statistics such as products, normalized brands, explicit available quantity, and recently imported products.
- Remove unsupported warehouse and pallet claims.
- Show selected in-stock or recently imported product offers with real images.
- Update explanatory copy to reflect product offers and supplier MOQ tiers.

#### `/stock` - Product catalogue

- Render paginated API results.
- Support the backend filters and sorting options.
- Keep filter state in the URL.
- Display image, brand, name/model, SKU, category, quantity, wholesale/retail price, currency, and status only when available.
- Provide clear loading, empty, error, and partial-data states.

#### `/stock/:productId` - Product details

- Render the real image gallery.
- Display identity, pricing, quantity, availability, description, and general specifications conditionally.
- Render category-specific fields, including eyewear measurements where present.
- Render variants only when `product_variants` exist.
- Render curated supplier attributes and MOQ price tiers.
- Show related products based on normalized brand and category.

#### `/brands` - Brand portfolio

- Use case-normalized brand facets.
- Show product counts and summed explicit quantity.
- Link each brand to a filtered catalogue URL.
- Do not treat missing quantities as zero stock.

#### `/about` - Company information

- Preserve the visual composition.
- Revise text that claims unsupported warehouse, pallet, inspection, or reservation behaviour unless independently confirmed.

#### `/support` - Support information

- Preserve the contact layout.
- Do not show a successful submission unless a real contact endpoint exists.
- Initially use direct contact links or a clearly non-submitting presentation.

The first implementation will omit the authenticated `/requests` experience and functional sign-in/application controls because the backend cannot currently support them.

### 6. Handle incomplete supplier data

- Never render empty labels or misleading zero values.
- Display "Quantity not supplied" when quantity is null.
- Keep zero quantity available for explicitly out-of-stock products.
- Use model or SKU as a fallback title when needed.
- Hide optional category, status, origin, material, and gender fields when missing.
- Use a designed image placeholder only when no associated image exists.
- Render variant tables only for products with actual variants.
- Make product-specific specification layouts tolerant of heterogeneous supplier data.

### 7. Responsive behaviour

The source design is desktop-only, so create a responsive interpretation consistent with it:

- Collapse multi-column layouts at tablet and mobile widths.
- Add an accessible mobile navigation menu.
- Stack catalogue filters and form fields on narrow screens.
- Make large data tables horizontally scrollable within labelled regions.
- Scale the hero typography responsively.
- Maintain usable touch targets and visible keyboard focus.
- Preserve the blueprint framing without creating horizontal page overflow.

### 8. Accessibility and robustness

- Use semantic links, buttons, headings, forms, tables, and landmarks.
- Provide meaningful image alternatives.
- Ensure keyboard access and themed `:focus-visible` states.
- Announce loading failures and asynchronous updates appropriately.
- Meet applicable colour-contrast requirements.
- Correct text-encoding artefacts from the exported prototype.
- Handle API timeout, offline, invalid product ID, missing media, and empty-result states.

### 9. Buyer functionality

Functional sign-in and demand-request flows require additional backend models and endpoints for:

- Organisations and users
- Authentication and sessions
- Account applications and approval status
- Product enquiries and general demand requests
- Request status history and quotes
- Reservation deadlines

The account, session, organisation, application, request, history, quote,
email-outbox, password-reset, and reservation schema is implemented in a separate
transactional portal database. Operators place quoted stock on a timed hold, confirm it
after offline payment, or release it. Public catalogue quantities are adjusted by active
portal reservations.

### 10. Testing and verification

Backend/API verification:

- Test against a temporary SQLite fixture that uses the existing schema.
- Cover pagination, search, filtering, sorting, normalization, and nullable fields.
- Verify image-path safety and media delivery.
- Confirm API responses never expose absolute source paths or raw supplier data.

Frontend verification:

- Unit-test formatting, query-state handling, filters, and conditional field display.
- Add integration tests for catalogue browsing and product details.
- Test loading, empty, error, and missing-image states.
- Test desktop, tablet, and mobile layouts.
- Run accessibility checks on every route.
- Run linting, TypeScript checks, tests, and the production build.
- Perform an end-to-end check against the real `products.db` and media directory.

## Implementation order

1. Build and test the read-only catalogue API.
2. Define frontend API contracts from real responses.
3. Scaffold the React application and routing.
4. Convert the design tokens and reusable primitives.
5. Implement the catalogue and product-detail routes.
6. Implement overview, brands, about, and support.
7. Add responsive and accessibility behaviour.
8. Complete integration tests and visual verification.
9. Scope authentication and buyer-request backend work separately.

## Completion criteria for the first release

- All catalogue content comes from the existing SQLite database through the API.
- Product images are served from the extracted backend media.
- No hard-coded prototype catalogue data remains in the application.
- The UI does not claim or display unsupported lot, pallet, carton, or warehouse data; authentication, requests, quotes, and reservations use the transactional portal schema.
- Filters and pagination work with the full dataset.
- Missing supplier fields are handled without misleading output.
- The visual result remains faithful to the Claude blueprint design.
- The application is responsive, keyboard-accessible, tested, and production-buildable.
