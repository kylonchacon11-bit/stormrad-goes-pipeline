"""Download latest GOES-19 (East) CONUS MCMIP and write a local NetCDF."""
from __future__ import annotations

import os
from pathlib import Path

from goes2go import GOES

DATA_DIR = Path(os.environ.get("GOES_DATA_DIR", "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Operational GOES-East since 2025-04-07
SATELLITE = 19
PRODUCT = "ABI-L2-MCMIPC"  # multi-channel cloud/moisture, CONUS
DOMAIN = "C"

def process_latest_conus():
    print("Initializing GOES-19 CONUS download (noaa-goes19)...")

    goes = GOES(
        satellite=SATELLITE,  # required — do not rely on config.toml default (often 16)
        product=PRODUCT,
        domain=DOMAIN,
    )

    # latest() only probes the current UTC hour; if that prefix is empty it raises
    # FileNotFoundError. Prefer a short lookback window.
    df = goes.timerange(recent="180min")
    if df is None or getattr(df, "empty", True):
        # Fallback: try latest() only after timerange failed
        print("timerange empty; trying goes.latest()...")
        ds = goes.latest()
    else:
        if "start" in df.columns:
            df = df.sort_values("start")
        row = df.iloc[-1]
        print(f"Latest scan: {row.get('file', row)}")
        # nearesttime downloads + opens the scan closest to that time
        t = row["start"] if "start" in row.index else None
        if t is not None:
            ds = goes.nearesttime(str(t))
        else:
            ds = goes.latest()

    out = DATA_DIR / "mcmip_latest.nc"
    if hasattr(ds, "to_netcdf"):
        ds.to_netcdf(out)
        print(f"Wrote {out}")
    else:
        # Some goes2go versions return a path / list of paths
        print(f"Download result (not Dataset): {ds!r}")

    return str(out)

if __name__ == "__main__":
    process_latest_conus()