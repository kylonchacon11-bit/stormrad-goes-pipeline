"""Download latest GOES-19 CONUS MCMIP and write a Web-Mercator RGB COG."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import s3fs
import xarray as xr
from goes2go import GOES
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles
import rasterio

DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Rough CONUS in Web Mercator (EPSG:3857), meters
WEST, SOUTH, EAST, NORTH = -14000000.0, 2500000.0, -7000000.0, 6500000.0
COG_WIDTH = 2500   # raise for sharper tiles (slower / larger)
COG_HEIGHT = 1500


def _download_latest_mcmip() -> Path:
    print("Initializing GOES-19 CONUS download (noaa-goes19)...")
    goes = GOES(satellite=19, product="ABI-L2-MCMIPC", domain="C")
    print(f"Using satellite={goes.satellite!r} product={goes.product!r}")

    df = goes.timerange(recent="180min", download=False, return_as="filelist")
    if df is None or getattr(df, "empty", True):
        raise ValueError("No GOES-19 MCMIPC files in the last 180 minutes")

    if "start" in df.columns:
        df = df.sort_values("start")
    row = df.iloc[-1]
    s3_key = row["file"] if "file" in row.index else str(row.iloc[0])
    print(f"Latest file found: {s3_key}")

    local_nc = DATA_DIR / Path(s3_key).name
    print(f"Downloading to {local_nc} ...")
    fs = s3fs.S3FileSystem(anon=True)
    fs.get(s3_key, str(local_nc))

    stable = DATA_DIR / "mcmip_latest.nc"
    if local_nc.resolve() != stable.resolve():
        import shutil

        shutil.copy2(local_nc, stable)
    print(f"Wrote {stable}")
    return stable


def _pick_var(ds: xr.Dataset, candidates: list[str]) -> xr.DataArray:
    for name in candidates:
        if name in ds:
            return ds[name]
    # fuzzy match
    lower = {k.lower(): k for k in ds.data_vars}
    for name in candidates:
        if name.lower() in lower:
            return ds[lower[name.lower()]]
    raise KeyError(f"None of {candidates} in dataset. Have: {list(ds.data_vars)[:20]}")


def _norm01(a: np.ndarray, p_lo: float = 2, p_hi: float = 98) -> np.ndarray:
    a = np.asarray(a, dtype=np.float32)
    finite = np.isfinite(a)
    if not finite.any():
        return np.zeros_like(a, dtype=np.float32)
    lo, hi = np.percentile(a[finite], [p_lo, p_hi])
    if hi <= lo:
        hi = lo + 1.0
    out = (a - lo) / (hi - lo)
    return np.clip(out, 0, 1)


def _rgb_from_mcmip(nc_path: Path) -> tuple[np.ndarray, dict]:
    """
    Build a simple daytime-style RGB from MCMIP reflective bands.
    R≈C02 (red), G≈C03 (veggie), B≈C01 (blue) — common true-color-ish recipe.
    """
    ds = xr.open_dataset(nc_path)

    # MCMIP variable names vary slightly by version
    r = _pick_var(ds, ["CMI_C02", "C02", "CMI_C02_earth"]).values
    g = _pick_var(ds, ["CMI_C03", "C03", "CMI_C03_earth"]).values
    b = _pick_var(ds, ["CMI_C01", "C01", "CMI_C01_earth"]).values

    # goes2go TrueColor-style gamma-ish stretch
    rgb = np.stack([_norm01(r), _norm01(g), _norm01(b)], axis=0)
    # mild gamma
    rgb = np.power(rgb, 0.75)
    rgb_u8 = (np.clip(rgb, 0, 1) * 255).astype(np.uint8)

    # Approximate geolocation from file metadata if present
    meta = {
        "title": "GOES-19 MCMIP RGB",
        "source": str(nc_path.name),
    }
    ds.close()
    return rgb_u8, meta


def _write_geotiff_webmercator(rgb_u8: np.ndarray, tif_path: Path) -> None:
    """
    Write RGB as EPSG:3857 GeoTIFF covering CONUS-ish bounds.
    (Simple georeference for map overlay; not a full GOES parallax correct remap.)
    """
    transform = from_bounds(WEST, SOUTH, EAST, NORTH, COG_WIDTH, COG_HEIGHT)

    # Resize native GOES grid to COG size
    import cv2  # optional — if missing, use simple numpy slice

    _, h, w = rgb_u8.shape
    try:
        import cv2

        resized = np.stack(
            [
                cv2.resize(rgb_u8[i], (COG_WIDTH, COG_HEIGHT), interpolation=cv2.INTER_AREA)
                for i in range(3)
            ],
            axis=0,
        )
    except ImportError:
        # nearest-neighbor fallback without opencv
        ys = (np.linspace(0, h - 1, COG_HEIGHT)).astype(int)
        xs = (np.linspace(0, w - 1, COG_WIDTH)).astype(int)
        resized = rgb_u8[:, ys][:, :, xs]

    profile = {
        "driver": "GTiff",
        "height": COG_HEIGHT,
        "width": COG_WIDTH,
        "count": 3,
        "dtype": "uint8",
        "crs": "EPSG:3857",
        "transform": transform,
        "compress": "deflate",
        "photometric": "RGB",
    }
    with rasterio.open(tif_path, "w", **profile) as dst:
        dst.write(resized)
    print(f"Wrote intermediate GeoTIFF {tif_path}")


def _to_cog(src_tif: Path, dst_cog: Path) -> None:
    profile = cog_profiles.get("deflate")
    profile["BLOCKSIZE"] = 256
    cog_translate(
        str(src_tif),
        str(dst_cog),
        profile,
        in_memory=False,
        quiet=True,
        overview_level=5,
        overview_resampling="average",
        resampling="bilinear",
    )
    print(f"Wrote COG {dst_cog}")


def process_latest_conus() -> str:
    nc_path = _download_latest_mcmip()

    print("Building RGB from MCMIP bands...")
    rgb_u8, meta = _rgb_from_mcmip(nc_path)
    print(f"RGB shape {rgb_u8.shape} meta={meta}")

    temp_tif = DATA_DIR / "temp_geocolor.tif"
    final_cog = DATA_DIR / "geocolor_latest.tif"

    _write_geotiff_webmercator(rgb_u8, temp_tif)
    _to_cog(temp_tif, final_cog)

    if temp_tif.exists():
        temp_tif.unlink()

    print(f"Done. COG ready at {final_cog}")
    return str(final_cog)


if __name__ == "__main__":
    process_latest_conus()