import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from api.catalogue import ProductQuery, facets, get_product, list_products, summary


SCHEMA = """
CREATE TABLE website_products (
  id INTEGER PRIMARY KEY, brand TEXT, name TEXT, category TEXT, model TEXT,
  sku TEXT, barcode TEXT, description TEXT, color TEXT, size TEXT, gender TEXT,
  material TEXT, quantity REAL, wholesale_price REAL, retail_price REAL,
  currency TEXT, status TEXT, image_path TEXT, offer_type TEXT, origin TEXT,
  hs_code TEXT, grade TEXT, model_year TEXT, collection TEXT, frame_color TEXT,
  lens_color TEXT, color_code TEXT, material_code TEXT, frame_material TEXT,
  bridge_size TEXT, branch_size TEXT, uva_filter TEXT, fitting TEXT,
  release_code TEXT, phase TEXT, exceeding_quantity REAL,
  total_retail_value REAL, attributes_json TEXT
);
CREATE TABLE product_variants (
  id INTEGER PRIMARY KEY, product_id INTEGER, size TEXT, quantity REAL,
  barcode TEXT, sku TEXT
);
CREATE TABLE product_images (
  id INTEGER PRIMARY KEY, product_id INTEGER, image_path TEXT, mime_type TEXT,
  is_primary INTEGER, sort_order INTEGER
);
"""


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.db"
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)
        values = [
            (1, "GUCCI", "Frame One", "Optical Frames", "GG1", "SKU1", 5, 12, 90, "EUR", "AVAILABLE", "media/a.jpg"),
            (2, "Gucci", "Frame Two", "Optical frames", "GG2", "SKU2", None, 15, 100, "EUR", "PREORDER", None),
            (3, "NIKE", "Runner", "Shoes", "N1", "SKU3", 0, 20, 80, "GBP", "NOT_AVAILABLE", "media/b.jpg"),
        ]
        for value in values:
            self.connection.execute(
                "INSERT INTO website_products (id,brand,name,category,model,sku,quantity,wholesale_price,retail_price,currency,status,image_path,attributes_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (*value, json.dumps({"Net Prices € MOQ 100pcs": "10.50"}) if value[0] == 1 else "{}"),
            )
        self.connection.execute("INSERT INTO product_variants VALUES (1,1,'M',3,NULL,'SKU1-M')")
        self.connection.execute("INSERT INTO product_images VALUES (1,1,'media/a.jpg','image/jpeg',1,0)")
        self.connection.commit()

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def test_filters_and_pagination(self):
        result = list_products(self.connection, ProductQuery(brand="gucci", in_stock=True))
        self.assertEqual(result["pagination"]["total"], 1)
        self.assertEqual(result["items"][0]["status_label"], "Available")

    def test_facets_merge_case_variants(self):
        result = facets(self.connection)
        self.assertEqual(result["brands"][0]["count"], 2)

    def test_detail_includes_variants_images_and_moq(self):
        result = get_product(self.connection, 1)
        self.assertEqual(result["variants"][0]["size"], "M")
        self.assertEqual(result["images"][0]["url"], "/media/a.jpg")
        self.assertEqual(result["moq_tiers"][0]["minimum_quantity"], 100)

    def test_summary_distinguishes_explicit_stock(self):
        result = summary(self.connection)
        self.assertEqual(result["products"], 3)
        self.assertEqual(result["brands"], 2)
        self.assertEqual(result["explicit_units"], 5)
        self.assertEqual(result["in_stock_products"], 1)


if __name__ == "__main__":
    unittest.main()
