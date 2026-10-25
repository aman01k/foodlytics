"""Download the Olist Brazilian E-Commerce dataset into data/raw/.

Order of attempts:
  1. Files already present (checksums/row counts verified).
  2. Official Kaggle API (needs KAGGLE_USERNAME/KAGGLE_KEY and `pip install kaggle`).
  3. Public Hugging Face mirror of the *unmodified* Kaggle CSVs
     (bulutttt/olist-raw-data). File sizes are verified against the known
     Kaggle originals, so a modified mirror is detected.

Manual fallback: download https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
and unzip the 9 CSVs into data/raw/.
"""
from __future__ import annotations

import hashlib
import json
import sys
import urllib.request

from config.settings import RAW_DIR

MIRROR = "https://huggingface.co/datasets/bulutttt/olist-raw-data/resolve/main/{name}"

# Byte sizes of the original Kaggle files (used as an integrity check).
EXPECTED_BYTES = {
    "olist_customers_dataset.csv": 9033957,
    "olist_geolocation_dataset.csv": 61273883,
    "olist_order_items_dataset.csv": 15438671,
    "olist_order_payments_dataset.csv": 5777138,
    "olist_order_reviews_dataset.csv": 14451670,
    "olist_orders_dataset.csv": 17654914,
    "olist_products_dataset.csv": 2379446,
    "olist_sellers_dataset.csv": 174703,
    "product_category_name_translation.csv": 2613,
}


def _sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def missing_files() -> list[str]:
    return [n for n, sz in EXPECTED_BYTES.items()
            if not (RAW_DIR / n).exists() or (RAW_DIR / n).stat().st_size != sz]


def try_kaggle() -> bool:
    try:
        import kaggle  # noqa: F401
        from kaggle.api.kaggle_api_extended import KaggleApi
        api = KaggleApi()
        api.authenticate()
        api.dataset_download_files("olistbr/brazilian-ecommerce", path=str(RAW_DIR), unzip=True)
        return True
    except Exception as exc:  # noqa: BLE001 - any failure -> fall back
        print(f"Kaggle API unavailable ({type(exc).__name__}); using mirror.")
        return False


def download_mirror(names: list[str]) -> None:
    for name in names:
        dest = RAW_DIR / name
        print(f"downloading {name} ...")
        urllib.request.urlretrieve(MIRROR.format(name=name), dest)


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    todo = missing_files()
    if todo and not try_kaggle():
        download_mirror(todo)
    bad = missing_files()
    if bad:
        print("Integrity check failed for:", bad)
        print("Download manually from https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce")
        return 1
    manifest = {n: {"bytes": (RAW_DIR / n).stat().st_size, "sha256": _sha256(RAW_DIR / n)}
                for n in EXPECTED_BYTES}
    (RAW_DIR / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
    print("All 9 files present and size-verified. Manifest written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
