"""Fetch latest GOES-19 East CONUS MCMIP."""
from __future__ import annotations

from pathlib import Path

from goes2go import GOES

DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)


def process_latest_conus() -> str:
    print("Initializing GOES-19 CONUS download (noaa-goes19)...")

    goes = GOES(
        satellite=19,
        product="ABI-L2-MCMIPC",
        domain="C",
    )
    print(f"Using satellite={goes.satellite!r} product={goes.product!r}")

    # List recent scans only (no bulk download of the whole window)
    df = goes.timerange(recent="180min", download=False, return_as="filelist")
    if df is None or getattr(df, "empty", True):
        raise ValueError("No GOES-19 MCMIPC files in the last 180 minutes")

    if "start" in df.columns:
        df = df.sort_values("start")
    row = df.iloc[-1]
    print(f"Latest file found: {row.get('file', row)}")

    # nearesttime downloads that scan and returns an xarray Dataset
    t = row["start"] if "start" in row.index else None
    if t is None:
        raise ValueError(f"Row has no 'start' time: {row}")
    ds = goes.nearesttime(str(t))

    out = DATA_DIR / "mcmip_latest.nc"
    ds.to_netcdf(out)
    print(f"Wrote {out}")
    return str(out)


if __name__ == "__main__":
    process_latest_conus()