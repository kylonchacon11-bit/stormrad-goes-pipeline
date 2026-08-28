"""Fetch latest GOES-19 East CONUS MCMIP NetCDF."""
from __future__ import annotations

from pathlib import Path

import s3fs
import xarray as xr
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

    # List only — do not use nearesttime (it probes the next hour and can 404)
    df = goes.timerange(recent="180min", download=False, return_as="filelist")
    if df is None or getattr(df, "empty", True):
        raise ValueError("No GOES-19 MCMIPC files in the last 180 minutes")

    if "start" in df.columns:
        df = df.sort_values("start")
    row = df.iloc[-1]

    # Exact object key from the listing, e.g.
    # noaa-goes19/ABI-L2-MCMIPC/2026/240/00/OR_ABI-L2-MCMIPC-M6_G19_....nc
    s3_key = row["file"] if "file" in row.index else str(row.iloc[0])
    print(f"Latest file found: {s3_key}")

    local_nc = DATA_DIR / Path(s3_key).name
    print(f"Downloading to {local_nc} ...")

    fs = s3fs.S3FileSystem(anon=True)
    fs.get(s3_key, str(local_nc))

    # Optional: also write a stable name for the rest of the pipeline
    stable = DATA_DIR / "mcmip_latest.nc"
    if local_nc.resolve() != stable.resolve():
        # open + save copy (or shutil.copy)
        import shutil

        shutil.copy2(local_nc, stable)

    # Sanity check
    with xr.open_dataset(stable) as ds:
        print(f"Opened dataset vars: {list(ds.data_vars)[:8]}...")

    print(f"Wrote {stable}")
    return str(stable)


if __name__ == "__main__":
    process_latest_conus()