import os
from pathlib import Path
from satpy import Scene
from goes2go import GOES
import rasterio
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles

DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

def process_latest_conus():
    print("Initializing GOES-19 CONUS download...")
    
    # Explicitly force GOES-19 (GOES-East active operational satellite)
    goes = GOES(
        satellite=19,
        product="ABI-L2-MCMIPC",
        domain="C",
    )
    
    # Use timerange to safely find recent files without hourly prefix errors
    df = goes.timerange(recent="180min")
    if df is None or getattr(df, "empty", True):
        raise ValueError("No recent GOES-19 CONUS MCMIPC files found on S3 (noaa-goes19).")
    
    if "start" in df.columns:
        df = df.sort_values("start")
    
    latest_row = df.iloc[-1]
    print(f"Latest file record found: {latest_row.get('file', latest_row)}")
    
    # Download the NetCDF file locally using goes2go helper
    local_nc = goes.download(df.iloc[[-1]])
    if isinstance(local_nc, list):
        local_nc = local_nc[0]
        
    print(f"Downloaded NetCDF to: {local_nc}")
    
    # Load into Satpy Scene
    print("Loading bands into Satpy...")
    scn = Scene(filenames=local_nc, reader='abi_l2_mcmip')
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

if __name__ == "__main__":
    process_latest_conus()