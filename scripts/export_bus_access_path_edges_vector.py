from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely import wkt


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "raw" / "09_bus_network" / "bus_access_pangyo_bokjeong_0_60min_path_edges.csv"
OUT_DIR = ROOT / "data" / "processed" / "09_bus_network"

FGB_OUT = OUT_DIR / "bus_access_pangyo_bokjeong_0_60min_path_edges_vector.fgb"
GEOJSON_OUT = OUT_DIR / "bus_access_pangyo_bokjeong_0_60min_path_edges_vector.geojson"
SHP_OUT = OUT_DIR / "bus_access_pangyo_bokjeong_0_60min_path_edges_vector.shp"


def read_csv_robust(path: Path) -> pd.DataFrame:
    encodings = ["utf-8-sig", "cp949", "euc-kr", "utf-8"]
    last_error: Exception | None = None
    for enc in encodings:
        try:
            return pd.read_csv(path, encoding=enc, low_memory=False)
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise FileNotFoundError(path)


def load_edges(path: Path) -> gpd.GeoDataFrame:
    df = read_csv_robust(path)
    required = {"geometry_wkt"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    df = df.copy()
    df["distance_m"] = pd.to_numeric(df.get("distance_m"), errors="coerce")
    df["travel_time_sec"] = pd.to_numeric(df.get("travel_time_sec"), errors="coerce")
    df["geometry"] = df["geometry_wkt"].apply(lambda value: wkt.loads(value) if isinstance(value, str) and value.strip() else None)
    df = df.dropna(subset=["geometry"]).copy()

    gdf = gpd.GeoDataFrame(df, geometry="geometry", crs=4326)
    return gdf


def write_outputs(gdf: gpd.GeoDataFrame) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    keep_cols = [
        "origin_key",
        "origin_name",
        "target_station_id",
        "from_node",
        "to_node",
        "mode",
        "route_id",
        "route_name",
        "distance_m",
        "travel_time_sec",
        "geometry_source",
        "geometry",
    ]
    available = [c for c in keep_cols if c in gdf.columns]
    out = gdf[available].copy()

    for path in [
        FGB_OUT,
        GEOJSON_OUT,
        SHP_OUT,
        SHP_OUT.with_suffix(".dbf"),
        SHP_OUT.with_suffix(".shx"),
        SHP_OUT.with_suffix(".prj"),
        SHP_OUT.with_suffix(".cpg"),
        SHP_OUT.with_suffix(".qpj"),
    ]:
        if path.exists():
            path.unlink()

    # Full-precision files for analysis / dashboard loading.
    out.to_file(FGB_OUT, driver="FlatGeobuf", encoding="utf-8", index=False)
    out.to_file(GEOJSON_OUT, driver="GeoJSON", encoding="utf-8", index=False)

    # Shapefile compatibility. Field names must be <= 10 chars, so we shorten them.
    shp = out.rename(
        columns={
            "origin_key": "orig_key",
            "origin_name": "orig_name",
            "target_station_id": "tgt_stid",
            "geometry_source": "geom_src",
            "travel_time_sec": "tt_sec",
            "distance_m": "dist_m",
            "route_name": "route_nm",
        }
    )
    shp = shp[
        [
            "orig_key",
            "orig_name",
            "tgt_stid",
            "from_node",
            "to_node",
            "mode",
            "route_id",
            "route_nm",
            "dist_m",
            "tt_sec",
            "geom_src",
            "geometry",
        ]
    ].copy()
    shp.to_file(SHP_OUT, driver="ESRI Shapefile", encoding="utf-8", index=False)


def main() -> None:
    gdf = load_edges(INPUT)
    write_outputs(gdf)
    print(f"rows={len(gdf)}")
    print(f"fgb={FGB_OUT}")
    print(f"geojson={GEOJSON_OUT}")
    print(f"shp={SHP_OUT}")


if __name__ == "__main__":
    main()
