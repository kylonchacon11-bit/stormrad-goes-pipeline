"""Fetch latest GOES-19 East CONUS MCMIP and write a COG-friendly intermediate."""
from __future__ import annotations

import os
from pathlib import Path

# Write goes2go config BEFORE importing GOES so defaults cannot stay on 16
_CFG = Path.home() / ".config" / "goes2go" / "config.toml"
_CFG.parent.mkdir(parents=True, exist_ok=True)
_CFG.write_text(
    '[default]\n'
    'satellite = 19\n'
    'product = "ABI-L2-MCMIPC"\n'
    'domain = "C"\n'
    'save_dir = "data/goes"\n'
)

from goes2go import GOES  # noqa: E402

DATA_DIR = Path(os.environ.get("GOES_DATA_DIR", "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)


def process_latest_conus() -> str:
    print("Initializing GOES-19 CONUS download (bucket noaa-goes19)...")

    goes = GOES(
        satellite=19,  # explicit — never rely on package default
        product="ABI-L2-MCMIPC",
        domain="C",
    )
    print(f"GOES object: satellite={getattr(goes, 'satellite', '?')} product={getattr(goes, 'product', '?')}")

    # Avoid goes.latest() — it only lists the current UTC hour and raises if empty
    df = goes.timerange(recent="180min")
    if df is None or getattr(df, "empty", True):
        raise ValueError(
            "No GOES-19 MCMIPC files in the last 180 minutes on noaa-goes19. "
            "Check S3 / outages."
        )

    if "start" in df.columns:
        df = df.sort_values("start")
    row = df.iloc[-1]
    print(f"Latest file row: {row.get('file', row)}")

    t = row["start"] if "start" in row.index else None
    if t is not None:
        ds = goes.nearesttime(str(t))
    else:
        ds = goes.nearesttime()  # library default window

    out_nc = DATA_DIR / "mcmip_latest.nc"
    if hasattr(ds, "to_netcdf"):
        ds.to_netcdf(out_nc)
        print(f"Wrote {out_nc}")
    else:
        print(f"Unexpected return type from nearesttime: {type(ds)} {ds!r}")

    return str(out_nc)


if __name__ == "__main__":
    process_latest_conus()