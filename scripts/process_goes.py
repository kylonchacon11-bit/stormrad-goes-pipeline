import os
from pathlib import Path

from goes2go import GOES
from satpy import Scene
from pyresample import create_area_def
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles

DATA_DIR = Path("data")
TEMP_TIF = DATA_DIR / "temp_geocolor.tif"
FINAL_COG = DATA_DIR / "geocolor_latest.tif"

# CONUS-ish Web Mercator footprint (adjust as needed)
WEB_MERCATOR_CONUS = create_area_def(
    "web_mercator_conus",
    {"proj": "epsg:3857"},
    area_extent=(-14000000, 2000000, -7000000, 6500000),  # rough CONUS
    resolution=2000,  # meters; raise for speed, lower for detail
)

def process_latest_conus():
    print("Initializing GOES-19 CONUS download...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # L1b CONUS radiance is the usual source for true-color style RGBs
    goes = GOES(satellite=19, product="ABI-L1b-RadC", domain="C")

    df = goes.timerange(recent="120min")
    if df is None or df.empty:
        raise ValueError("No recent GOES-19 CONUS files found on S3.")

    # Newest by start time if available
    if "start" in df.columns:
        df = df.sort_values("start")
    latest = df.iloc[-1]
    file_key = latest["file"] if "file" in latest.index else latest.iloc[0]
    print(f"Latest file found: {file_key}")

    # Download (API varies slightly by goes2go version)
    local_paths = goes.download(latest)
    if isinstance(local_paths, (str, Path)):
        filenames = [str(local_paths)]
    elif hasattr(local_paths, "__iter__"):
        filenames = [str(p) for p in local_paths]
    else:
        filenames = [str(local_paths)]

    print("Loading bands into Satpy...")
    scn = Scene(filenames=filenames, reader="abi_l1b")
    # true_color needs C01, C02, C03 (Satpy loads deps automatically)
    scn.load(["true_color"])

    print("Reprojecting to EPSG:3857...")
    projected = scn.resample(WEB_MERCATOR_CONUS)

    print("Writing temporary GeoTIFF...")
    if TEMP_TIF.exists():
        TEMP_TIF.unlink()
    projected.save_datasets(
        writer="geotiff",
        filename=str(TEMP_TIF),
        enhance=True,
        dtype="uint8",
    )

    print("Generating Cloud Optimized GeoTIFF (COG)...")
    profile = cog_profiles.get("jpeg")
    # Keep alpha if present; jpeg profile is RGB-friendly
    cog_translate(
        str(TEMP_TIF),
        str(FINAL_COG),
        profile,
        in_memory=False,
        quiet=True,
    )

    if TEMP_TIF.exists():
        TEMP_TIF.unlink()

    print(f"Successfully generated COG at {FINAL_COG}")
    return str(FINAL_COG)

if __name__ == "__main__":
    process_latest_conus()