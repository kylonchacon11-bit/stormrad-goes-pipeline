import os
from datetime import datetime
from satpy import Scene
from goes2go import GOES
import rasterio
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles

def process_latest_conus():
    print("Initializing GOES-16/19 CONUS download...")
    
    os.makedirs("data", exist_ok=True)
    
    # Fetch latest CONUS MCMIP data using goes2go
    goes = GOES(satellite=16, product="ABI-L2-MCMIP", domain="C")
    latest_file = goes.latest()
    
    print(f"Latest file found: {latest_file}")
    local_nc = goes.download(latest_file)
    
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