"""Fetch latest GOES-19 East CONUS MCMIP and process into a GeoColor COG."""
from __future__ import annotations

from pathlib import Path
from satpy import Scene
from goes2go import GOES
import rasterio
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles

DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

def process_latest_conus() -> str:
    print("Initializing GOES-19 CONUS download (noaa-goes19)...")

    # Explicit args beat any missing config.toml sections
    goes = GOES(
        satellite=19,
        product="ABI-L2-MCMIPC",
        domain="C",
    )
    print(f"Using satellite={goes.satellite!r} product={goes.product!r}")

    # List recent files (DataFrame)
    df = goes.timerange(recent="180min", download=False, return_as="filelist")
    if df is None or getattr(df, "empty", True):
        raise ValueError("No GOES-19 MCMIPC files in the last 180 minutes")

    if "start" in df.columns:
        df = df.sort_values("start")
    row = df.iloc[-1]
    print(f"Latest file found: {row.get('file', row)}")

    t = row["start"] if "start" in row.index else None
    
    # Download using nearesttime to get the netcdf file path or dataset
    local_nc_path = goes.download(row)
    if isinstance(local_nc_path, list):
        local_nc_path = local_nc_path[0]

    print(f"Downloaded NetCDF to: {local_nc_path}")

    # Load into Satpy Scene
    print("Loading bands into Satpy...")
    scn = Scene(filenames=local_nc_path, reader='abi_l2_mcmip')
    scn.load(['geocolor'])

    # Reproject to Web Mercator (EPSG:3857)
    print("Reprojecting to EPSG:3857...")
    projected_scn = scn.resample('EPSG:3857', radius_of_influence=5000)

    temp_tif = DATA_DIR / "temp_geocolor.tif"
    final_cog = DATA_DIR / "geocolor_latest.tif"

    projected_scn.save_datasets(writer='geotiff', filename=str(temp_tif))

    # Convert to Cloud Optimized GeoTIFF (COG)
    print("Generating Cloud Optimized GeoTIFF (COG)...")
    profile = cog_profiles.get("jpeg")

    cog_translate(
        str(temp_tif),
        str(final_cog),
        profile,
        in_memory=False,
        overview_level=5,
        quiet=True
    )

    # Clean up temp file
    if temp_tif.exists():
        temp_tif.unlink()

    print(f"Successfully generated COG at {final_cog}")
    return str(final_cog)

if __name__ == "__main__":
    process_latest_conus()