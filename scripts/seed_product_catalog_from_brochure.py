from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from calb_sizing_tool.services.product_catalog_seed_service import (
    DEFAULT_314_EXCEL_PATH,
    DEFAULT_BROCHURE_SOURCE,
    ProductCatalogSeedService,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Admin Portal product catalog from CALB product brochure data.")
    parser.add_argument("--db-url", default=None, help="Optional SQLAlchemy database URL.")
    parser.add_argument(
        "--excel-path",
        default=str(DEFAULT_314_EXCEL_PATH),
        help="314Ah SOH Excel dictionary used for default degradation curves.",
    )
    parser.add_argument(
        "--brochure-source",
        default=DEFAULT_BROCHURE_SOURCE,
        help="Source document label stored in product metadata.",
    )
    parser.add_argument(
        "--brochure-pptx-path",
        default=None,
        help="Optional PPTX path used to extract product image assets.",
    )
    parser.add_argument(
        "--asset-root",
        default="var/product_assets",
        help="Directory for copied product image assets.",
    )
    args = parser.parse_args()

    result = ProductCatalogSeedService(args.db_url).seed_brochure_catalog(
        excel_path=Path(args.excel_path),
        brochure_source=args.brochure_source,
        brochure_pptx_path=Path(args.brochure_pptx_path) if args.brochure_pptx_path else None,
        asset_root=Path(args.asset_root),
    )
    print(
        "Seeded product catalog: "
        f"cells={result['cells']}, "
        f"degradation_curves={result['degradation_curves']}, "
        f"dc_blocks={result['dc_blocks']}, "
        f"assets={result['assets']}"
    )


if __name__ == "__main__":
    main()
