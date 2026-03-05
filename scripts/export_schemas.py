from __future__ import annotations

import argparse
from pathlib import Path

from common import export_schemas


def main() -> None:
    parser = argparse.ArgumentParser(description="Export JSON schemas for I/O contracts.")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    out_dir = Path(args.out_dir)
    schemas = export_schemas(out_dir)
    print(f"Exported {len(schemas)} schemas to {out_dir}")


if __name__ == "__main__":
    main()
