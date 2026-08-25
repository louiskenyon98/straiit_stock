# Product stock importer

This imports every `.xlsx`, `.xlsm`, and `.pdf` supplier file in a folder into a
single SQLite database suitable for a product-listing website.

## Setup and import

```powershell
python -m pip install -r product_importer/requirements.txt
python product_importer/ingest.py . --database product_importer/products.db
```

Run the same command whenever supplier files change. Unchanged files are skipped;
changed files are replaced transactionally, so rows are not duplicated. Use
`--force` to deliberately rebuild all rows and `--recursive` to include subfolders.
Existing product IDs are preserved when matching source rows are re-imported.
Unlabelled prices default to EUR; override that with `--default-currency GBP` or
disable the default with `--default-currency ""`.

## Database

`products.db` is a SQLite database with four main tables and one website-facing view:

- `source_files`: one row per imported Excel/PDF file. It stores the absolute source
  path, filename, file type, SHA-256 checksum, timestamps, imported product count,
  and any warning. The checksum is what allows unchanged files to be skipped.
- `products`: one row per product offer. It contains normalized website fields,
  original source location, raw PDF text where applicable, and `attributes_json`
  containing all populated supplier columns. `(source_file_id, source_key)` is
  unique, preventing duplicate rows from the same sheet/page.
- `product_variants`: per-size stock and barcode records for matrix-style supplier
  sheets. It links to `products.id` and is unique by product and size.
- `product_images`: one-to-many image associations with stored path, source anchor or
  page coordinates, content hash, primary-image flag, and matching method.
- `website_products`: a read-only view joining products to their source filenames.
  This is the simplest interface for a website or API.

`products.source_file_id` is a foreign key to `source_files.id`, and
`product_variants.product_id` links variants to products. Deletes cascade through
these relationships. Indexes are provided for brand, category, SKU, barcode, product
name, variant barcode, and image hashes.

Additional normalized fields include offer type, origin, HS code, grade, model year,
collection, frame/lens colours, colour and material codes, frame material, eyewear
measurements, fitting, release code, phase, order/exceeding quantities, and total
retail value. Mirrored EAN sheets are suppressed; EAN helper sheets instead enrich
the main product and its size variants.

Use the `website_products` view for the website:

```sql
SELECT *
FROM website_products
WHERE brand = 'NIKE' AND quantity > 0
ORDER BY name;
```

The normalized columns include brand, product name, category, model, SKU, barcode,
description, colour, size, gender, material, stock quantity, wholesale and retail
prices, currency, and status. `attributes_json` retains every populated column from
the original spreadsheet, including supplier-specific MOQ prices and size matrices.
`source_file` and `source_location` make every row traceable to its origin.

PDF catalogues are less structured than spreadsheets. The importer recognizes the
formats in this folder that use `WSP`/`WHS` and `RRP`, French `P.Tarif` stock sheets,
and the classic footwear catalogue layout. A PDF with no recognizable product-price
records remains listed in `source_files` with a warning instead of inventing rows.

Useful checks:

```powershell
python -c "import sqlite3; c=sqlite3.connect('product_importer/products.db'); print(c.execute('select brand,count(*) from products group by brand order by count(*) desc limit 20').fetchall())"
python -c "import sqlite3; c=sqlite3.connect('product_importer/products.db'); print(c.execute('select filename,product_count,warning from source_files order by filename').fetchall())"
```

## Images

Image extraction runs during a normal import and stores files in `media` beside the
database. Excel pictures are associated using their native worksheet cell anchors.
PDF pictures are conservatively associated with the nearest located SKU on the same
page; unmatched page artwork is not attached to a product. The first association is
also copied to `products.image_path` for convenient website queries.

Refresh images without rebuilding product rows:

```powershell
python product_importer/ingest.py . --database product_importer/products.db --images-only
```

Use `--media-dir PATH` for a different storage location or `--skip-images` for a
data-only import.
