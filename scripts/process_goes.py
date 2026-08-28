import os
from datetime import datetime
from satpy import Scene
from goes2go import GOES
import rasterio
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles

def process_latest_conus():
    print("Initializing GOES-19 CONUS download...")
    
    os.makedirs("data", exist_ok=True)
    
    # Use GOES-19 (active East satellite) and search recent files to avoid strict hourly folder misses
    goes = GOES(satellite=19, product="ABI-L2-MCMIP", domain="C")
    
    # Get files from the last 60 minutes
    df = goes.timeranger(recent="60min")
    if df.empty:
        raise ValueError("No recent GOES files found on S3.")
    
    # Pick the absolute latest file path from the dataframe
    latest_file_row = df.iloc[-1]
    print(f"Latest file found: {latest_file_row['file']}")
    
    # Download the NetCDF file locally
    local_nc = goes.download(latest_file_row)
    
    # Load into Satpy Scene
    print("Loading bands into Satpy...")
    scn = Scene(filenames=local_nc, reader='abi_l2_mcmip')
    scn.load(['geocolor'])
    
    # Reproject to Web Mercator (EPSG:3857)
    print("Reprojecting to EPSG:3857...")
    projected_scn = scn.resample('EPSG:3857', radius_of_influence=5000)
    
    temp_tif = "data/temp_geocolor.tif"
    final_cog = "data/geocolor_latest.tif"
    
    projected_scn.save_datasets(writer='geotiff', filename=temp_tif)
    
    # Convert to Cloud Optimized GeoTIFF (COG)
    print("Generating Cloud Optimized GeoTIFF (COG)...")
    profile = cog_profiles.get("jpeg")
    
    cog_translate(
        temp_tif,
        final_cog,
        profile,
        in_memory=False,
        overview_level=5,
        quiet=True
    )
    
    if os.path.exists(temp_tif):
        os.remove(temp_tif)
        
    print(f"Successfully generated COG at {final_cog}")

if __name__ == "__main__":
    process_latest_conus()