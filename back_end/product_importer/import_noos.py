#!/usr/bin/env python3
"""Import a NOOS supplier tree into the catalogue database.

Excel and PDF files are imported with their original source locations. Exact
duplicate files are processed once, all products get the NOOS offer type, embedded
or catalogue-page images are extracted, and exact SKU matches reuse an existing
catalogue image when the NOOS source has none of its own.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from ingest import (
    SCHEMA,
    add_product_image,
    candidate_files,
    ensure_schema,
    import_file,
    infer_brand_from_filename,
    mime_for_extension,
    normalized_identifier,
    safe_filename_part,
    sha256,
    stored_media_path,
    sync_source_images,
)


def source_id_for(connection: sqlite3.Connection, path: Path) -> int | None:
    row = connection.execute(
        "SELECT id FROM source_files WHERE path=?", (str(path.resolve()),)
    ).fetchone()
    return int(row[0]) if row else None


def mark_noos_products(
    connection: sqlite3.Connection, source_id: int, relative_path: Path
) -> None:
    brand = infer_brand_from_filename(relative_path.as_posix())
    with connection:
        connection.execute(
            "UPDATE products SET offer_type='NOOS', status=COALESCE(NULLIF(status,''),'NOOS'), "
            "quantity=CASE WHEN quantity=0 THEN NULL ELSE quantity END, "
            "brand=COALESCE(NULLIF(brand,''),?) WHERE source_file_id=?",
            (brand, source_id),
        )


def reuse_exact_sku_images(
    connection: sqlite3.Connection, noos_source_ids: set[int]
) -> int:
    """Attach one existing primary image to exact-SKU NOOS matches without one."""
    connection.row_factory = sqlite3.Row
    image_by_sku: dict[str, sqlite3.Row] = {}
    for row in connection.execute(
        "SELECT p.sku,p.model,i.source_file_id,i.image_path,i.mime_type,i.sha256,"
        "i.source_sheet,i.source_row,i.source_page,i.source_x,i.source_y,i.width,i.height "
        "FROM products p JOIN product_images i ON i.product_id=p.id "
        "ORDER BY i.is_primary DESC,i.sort_order,i.id"
    ):
        for identifier in (row["sku"], row["model"]):
            key = normalized_identifier(identifier)
            if len(key) >= 6:
                image_by_sku.setdefault(key, row)

    placeholders = ",".join("?" for _ in noos_source_ids)
    if not placeholders:
        return 0
    linked = 0
    targets = connection.execute(
        f"SELECT p.id,p.sku,p.model FROM products p "
        f"WHERE p.source_file_id IN ({placeholders}) "
        "AND NOT EXISTS(SELECT 1 FROM product_images i WHERE i.product_id=p.id)",
        tuple(sorted(noos_source_ids)),
    ).fetchall()
    with connection:
        for product in targets:
            image = None
            for identifier in (product["sku"], product["model"]):
                key = normalized_identifier(identifier)
                if len(key) >= 6 and key in image_by_sku:
                    image = image_by_sku[key]
                    break
            if image is None:
                continue
            add_product_image(
                connection,
                product_id=product["id"],
                source_id=image["source_file_id"],
                image_path=image["image_path"],
                digest=image["sha256"],
                mime_type=image["mime_type"],
                source_sheet=image["source_sheet"],
                source_row=image["source_row"],
                source_page=image["source_page"],
                x=image["source_x"],
                y=image["source_y"],
                width=image["width"],
                height=image["height"],
                match_method="exact_sku_image_reuse",
            )
            linked += 1
    return linked


def link_unparsed_pdf_images_by_sku(
    connection: sqlite3.Connection,
    pdf_sources: list[tuple[int, Path]],
    noos_source_ids: set[int],
    media_root: Path,
    database_parent: Path,
) -> int:
    """Link catalogue images when a PDF has searchable SKUs but no price rows."""
    try:
        import hashlib
        import pymupdf as fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required for PDF image extraction") from exc
    if not pdf_sources or not noos_source_ids:
        return 0
    connection.row_factory = sqlite3.Row
    placeholders = ",".join("?" for _ in noos_source_ids)
    rows = connection.execute(
        f"SELECT p.id,p.sku,p.model FROM products p "
        f"WHERE p.source_file_id IN ({placeholders}) "
        "AND p.sku IS NOT NULL "
        "AND NOT EXISTS(SELECT 1 FROM product_images i WHERE i.product_id=p.id)",
        tuple(sorted(noos_source_ids)),
    ).fetchall()
    target_by_key: dict[str, sqlite3.Row] = {}
    for row in rows:
        for identifier in (row["sku"], row["model"]):
            key = normalized_identifier(identifier)
            if len(key) >= 6:
                target_by_key.setdefault(key, row)
    linked = 0
    with connection:
        for source_id, path in pdf_sources:
            output_dir = media_root / f"source-{source_id:04d}-{safe_filename_part(path.stem)}"
            document = fitz.open(str(path))
            try:
                for page_index in range(document.page_count):
                    page = document[page_index]
                    page_key = normalized_identifier(page.get_text())
                    candidates = [(key, row) for key, row in target_by_key.items() if key in page_key]
                    if not candidates:
                        continue
                    blocks = [
                        block for block in page.get_text("dict").get("blocks", [])
                        if block.get("type") == 1 and block.get("image")
                    ]
                    page_area = max(page.rect.width * page.rect.height, 1)
                    usable = []
                    for block in blocks:
                        x0, y0, x1, y1 = block["bbox"]
                        width, height = x1 - x0, y1 - y0
                        if width < 35 or height < 35 or len(block["image"]) < 1000:
                            continue
                        if len(candidates) > 1 and width * height / page_area > .78:
                            continue
                        usable.append(block)
                    unused = set(range(len(usable)))
                    for key, product in candidates:
                        terms = [product["sku"], product["model"]]
                        rectangles = []
                        for term in terms:
                            if term:
                                rectangles = page.search_for(str(term))
                            if rectangles:
                                break
                        if not rectangles or not unused:
                            continue
                        rect = rectangles[0]
                        center = ((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
                        image_number = min(
                            unused,
                            key=lambda index: (
                                (usable[index]["bbox"][0] + usable[index]["bbox"][2]) / 2 - center[0]
                            ) ** 2 + 2 * (
                                (usable[index]["bbox"][1] + usable[index]["bbox"][3]) / 2 - center[1]
                            ) ** 2,
                        )
                        block = usable[image_number]
                        x0, y0, x1, y1 = block["bbox"]
                        image_center = ((x0 + x1) / 2, (y0 + y1) / 2)
                        distance = ((center[0] - image_center[0]) ** 2 + (center[1] - image_center[1]) ** 2) ** .5
                        diagonal = (page.rect.width ** 2 + page.rect.height ** 2) ** .5
                        if distance > diagonal * .48:
                            continue
                        unused.remove(image_number)
                        data = block["image"]
                        digest = hashlib.sha256(data).hexdigest()
                        extension = "." + str(block.get("ext") or "bin").lower().lstrip(".")
                        output_dir.mkdir(parents=True, exist_ok=True)
                        output_path = output_dir / f"page-{page_index + 1}-sku-{safe_filename_part(key)}-{digest[:12]}{extension}"
                        if not output_path.exists():
                            output_path.write_bytes(data)
                        add_product_image(
                            connection,
                            product_id=product["id"], source_id=source_id,
                            image_path=stored_media_path(media_root, database_parent, output_path),
                            digest=digest, mime_type=mime_for_extension(extension),
                            source_page=page_index + 1, x=x0, y=y0,
                            width=x1 - x0, height=y1 - y0,
                            match_method="pdf_exact_sku_cross_source",
                        )
                        for matched_key in [
                            candidate_key for candidate_key, candidate in target_by_key.items()
                            if candidate["id"] == product["id"]
                        ]:
                            target_by_key.pop(matched_key, None)
                        linked += 1
            finally:
                document.close()
    return linked


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import NOOS Excel/PDF stock into the catalogue")
    parser.add_argument("folder", type=Path, help="NOOS EU folder")
    parser.add_argument("--database", "-d", required=True, type=Path)
    parser.add_argument("--media-dir", type=Path)
    parser.add_argument("--default-currency", default="EUR")
    parser.add_argument("--force", action="store_true", help="re-import unchanged source files")
    parser.add_argument("--skip-images", action="store_true")
    args = parser.parse_args(argv)

    folder = args.folder.resolve()
    database = args.database.resolve()
    media_root = (args.media_dir or database.parent / "media").resolve()
    files = candidate_files(folder, recursive=True)
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    connection.executescript(SCHEMA)
    ensure_schema(connection)

    seen_hashes: dict[str, Path] = {}
    noos_source_ids: set[int] = set()
    unparsed_pdf_sources: list[tuple[int, Path]] = []
    errors = 0
    imported_products = 0
    try:
        for index, path in enumerate(files, 1):
            digest = sha256(path)
            if digest in seen_hashes:
                print(
                    f"[{index}/{len(files)}] duplicate  {path.relative_to(folder)} "
                    f"(same as {seen_hashes[digest].relative_to(folder)})",
                    flush=True,
                )
                continue
            seen_hashes[digest] = path
            status, count, warning = import_file(
                connection, path, force=args.force, default_currency=args.default_currency or None
            )
            source_id = source_id_for(connection, path)
            image_note = ""
            if source_id is not None and status != "error":
                noos_source_ids.add(source_id)
                if path.suffix.lower() == ".pdf" and count == 0:
                    unparsed_pdf_sources.append((source_id, path))
                mark_noos_products(connection, source_id, path.relative_to(folder))
                if not args.skip_images and (status == "imported" or args.force):
                    try:
                        matched, unmatched = sync_source_images(
                            connection, source_id, path, media_root, database.parent
                        )
                        image_note = f"; images {matched} matched/{unmatched} unmatched"
                    except Exception as exc:
                        errors += 1
                        image_note = f"; image error: {type(exc).__name__}: {exc}"
            imported_products += count if status == "imported" else 0
            note = f" - {warning}" if warning else ""
            print(
                f"[{index}/{len(files)}] {status:8} {count:5} products  "
                f"{path.relative_to(folder)}{note}{image_note}", flush=True,
            )
            errors += status == "error"

        cross_linked = 0
        reused = 0
        if not args.skip_images:
            cross_linked = link_unparsed_pdf_images_by_sku(
                connection, unparsed_pdf_sources, noos_source_ids, media_root, database.parent
            )
            reused = reuse_exact_sku_images(connection, noos_source_ids)
        placeholders = ",".join("?" for _ in noos_source_ids)
        if placeholders:
            summary = connection.execute(
                f"SELECT COUNT(*),SUM(sku IS NOT NULL),SUM(wholesale_price IS NOT NULL),"
                f"SUM(retail_price IS NOT NULL),SUM(image_path IS NOT NULL) FROM products "
                f"WHERE source_file_id IN ({placeholders})",
                tuple(sorted(noos_source_ids)),
            ).fetchone()
        else:
            summary = (0, 0, 0, 0, 0)
        print(
            "NOOS summary: "
            f"{summary[0]} products; {summary[1] or 0} SKU; "
            f"{summary[2] or 0} wholesale prices; {summary[3] or 0} retail prices; "
            f"{summary[4] or 0} products with images "
            f"({cross_linked} linked from unparsed PDF pages; {reused} reused by exact SKU).",
            flush=True,
        )
        print(f"Database: {database}; rows imported or refreshed this run: {imported_products}")
    finally:
        connection.close()
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
