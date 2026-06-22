from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_SGIS = ROOT / "data" / "raw" / "04_sgis"
FRONTEND2_DATA = ROOT / "frontend2" / "public" / "data"
FRONTEND_DATA = ROOT / "frontend" / "public" / "data"

STATION_GEOJSON = FRONTEND2_DATA / "bus_access_pangyo_bokjeong_0_60min_stations.geojson"
OUTPUT_CSV = FRONTEND2_DATA / "bus_access_pangyo_bokjeong_0_60min_station_population_workers_500m.csv"
OUTPUT_GEOJSON = FRONTEND2_DATA / "bus_access_pangyo_bokjeong_0_60min_station_population_workers_500m.geojson"
OUTPUT_DASHBOARD_JSON = FRONTEND2_DATA / "dashboard_bus_access_pangyo_bokjeong_0_60min_station_population_workers_500m.json"
OUTPUT_DASHBOARD_JSON_LEGACY = FRONTEND_DATA / "dashboard_bus_access_pangyo_bokjeong_0_60min_station_population_workers_500m.json"

BUFFER_M = 500.0


def read_csv_robust(path: Path, **kwargs) -> pd.DataFrame:
    encodings = ["utf-8-sig", "cp949", "euc-kr", "utf-8"]
    last_error: Exception | None = None
    for enc in encodings:
        try:
            return pd.read_csv(path, encoding=enc, low_memory=False, **kwargs)
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise FileNotFoundError(path)


def find_one(pattern: str) -> Path:
    matches = sorted(RAW_SGIS.rglob(pattern))
    if not matches:
        raise FileNotFoundError(f"No file matched {pattern!r} under {RAW_SGIS}")
    return matches[0]


def load_metric_table(path: Path, metric_code: str, value_col: str) -> pd.DataFrame:
    df = read_csv_robust(path, header=None, names=["sgis_year", "area_code", "metric_code", value_col])
    df["area_code"] = df["area_code"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    df["metric_code"] = df["metric_code"].astype(str).str.strip()
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
    df = df[df["metric_code"].eq(metric_code)].copy()
    df = df.dropna(subset=["area_code"])
    df = df.groupby("area_code", as_index=False)[value_col].sum(min_count=1)
    return df


def load_grids() -> gpd.GeoDataFrame:
    grid_paths = [
        RAW_SGIS / "bnd_oa_11_2025_2Q" / "bnd_oa_11_2025_2Q.shp",
        RAW_SGIS / "bnd_oa_31_2025_2Q" / "bnd_oa_31_2025_2Q.shp",
    ]
    frames: list[gpd.GeoDataFrame] = []
    pop_11 = load_metric_table(find_one("*11*_인구총괄(총인구).csv"), "to_in_001", "resident_population")
    pop_31 = load_metric_table(find_one("*31*_인구총괄(총인구).csv"), "to_in_001", "resident_population")
    workers_11 = load_metric_table(find_one("*11*_산업분류별(10차_대분류)_총괄종사자수.csv"), "to_em_020", "worker_population")
    workers_31 = load_metric_table(find_one("*31*_산업분류별(10차_대분류)_총괄종사자수.csv"), "to_em_020", "worker_population")

    metric_lookup = {
        "11": (pop_11, workers_11),
        "31": (pop_31, workers_31),
    }

    for shp in grid_paths:
        gdf = gpd.read_file(shp)
        if gdf.crs is None:
            gdf = gdf.set_crs(5179)
        else:
            gdf = gdf.to_crs(5179)
        sigungu = str(gdf.iloc[0]["TOT_OA_CD"])[:2] if not gdf.empty else ""
        if sigungu not in metric_lookup:
            raise ValueError(f"Unexpected grid prefix for {shp}: {sigungu}")
        pop_df, worker_df = metric_lookup[sigungu]
        gdf["area_code"] = gdf["TOT_OA_CD"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
        gdf["grid_area_m2"] = gdf.geometry.area
        gdf = gdf.merge(pop_df, on="area_code", how="left")
        gdf = gdf.merge(worker_df, on="area_code", how="left")
        gdf["resident_population"] = gdf["resident_population"].fillna(0.0)
        gdf["worker_population"] = gdf["worker_population"].fillna(0.0)
        frames.append(gdf[["area_code", "grid_area_m2", "resident_population", "worker_population", "geometry"]])

    grids = pd.concat(frames, ignore_index=True)
    grids = gpd.GeoDataFrame(grids, geometry="geometry", crs=5179)
    grids = grids[grids["grid_area_m2"].gt(0)].copy()
    return grids


def weighted_station_totals(stations: gpd.GeoDataFrame, grids: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    sindex = grids.sindex
    results: list[dict[str, object]] = []

    stations_5179 = stations.to_crs(5179).copy()
    if "station_id" not in stations_5179.columns:
        stations_5179["station_id"] = stations_5179.index.astype(str)

    for idx, row in stations_5179.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        buffer = geom.buffer(BUFFER_M)
        candidate_idx = list(sindex.query(buffer, predicate="intersects"))

        resident_total = 0.0
        worker_total = 0.0
        covered_area_m2 = 0.0
        intersected_grid_count = 0

        for grid_idx in candidate_idx:
            grid = grids.iloc[int(grid_idx)]
            inter = buffer.intersection(grid.geometry)
            if inter.is_empty:
                continue
            inter_area = float(inter.area)
            if inter_area <= 0:
                continue
            intersected_grid_count += 1
            covered_area_m2 += inter_area
            ratio = inter_area / float(grid.grid_area_m2) if float(grid.grid_area_m2) else 0.0
            resident_total += float(grid.resident_population) * ratio
            worker_total += float(grid.worker_population) * ratio

        results.append(
            {
                "station_index": int(idx),
                "origin_key": row.get("origin_key"),
                "origin_name": row.get("origin_name"),
                "target_station_id": row.get("target_station_id"),
                "target_station_name": row.get("target_station_name"),
                "target_station_no": row.get("target_station_no"),
                "target_lon": row.get("target_lon"),
                "target_lat": row.get("target_lat"),
                "travel_time_min": row.get("travel_time_min"),
                "resident_population_500m": round(resident_total, 3),
                "worker_population_500m": round(worker_total, 3),
                "buffer_area_m2": round(float(buffer.area), 3),
                "covered_area_m2": round(covered_area_m2, 3),
                "coverage_ratio": round(covered_area_m2 / float(buffer.area), 6) if buffer.area else None,
                "intersected_grid_count": intersected_grid_count,
                "geometry": row.geometry,
            }
        )

    out = gpd.GeoDataFrame(results, geometry="geometry", crs=5179)
    out = out.sort_values(["origin_key", "travel_time_min", "target_station_id"], kind="stable").reset_index(drop=True)
    return out


def build_dashboard_json(results: gpd.GeoDataFrame) -> dict[str, object]:
    df = pd.DataFrame(results.drop(columns="geometry")).copy()
    if df.empty:
        return {"table": [], "selected": [], "candidates": []}

    group_cols = ["origin_key", "origin_name"]
    summary_rows = []
    selected_rows = []

    for (origin_key, origin_name), subset in df.groupby(group_cols, sort=True):
        subset = subset.sort_values(["travel_time_min", "target_station_id"], kind="stable").copy()
        chosen = subset.iloc[0]
        summary_rows.append(
            {
                "origin_key": origin_key,
                "origin_name": origin_name,
                "selected_station_name": chosen["target_station_name"],
                "selected_station_id": chosen["target_station_id"],
                "selected_travel_time_min": float(chosen["travel_time_min"]),
                "station_count": int(len(subset)),
                "mean_resident_population_500m": float(subset["resident_population_500m"].mean()),
                "mean_worker_population_500m": float(subset["worker_population_500m"].mean()),
                "max_resident_population_500m": float(subset["resident_population_500m"].max()),
                "max_worker_population_500m": float(subset["worker_population_500m"].max()),
            }
        )
        selected_rows.append(
            {
                "origin_key": origin_key,
                "origin_name": origin_name,
                "selected_station_name": chosen["target_station_name"],
                "selected_station_id": chosen["target_station_id"],
                "selected_station_no": chosen["target_station_no"],
                "selected_travel_time_min": float(chosen["travel_time_min"]),
                "resident_population_500m": float(chosen["resident_population_500m"]),
                "worker_population_500m": float(chosen["worker_population_500m"]),
                "buffer_area_m2": float(chosen["buffer_area_m2"]),
                "coverage_ratio": float(chosen["coverage_ratio"]) if pd.notna(chosen["coverage_ratio"]) else None,
                "intersected_grid_count": int(chosen["intersected_grid_count"]),
                "selection_reason": "minimum travel time within origin group",
            }
        )

    candidates = []
    for row in df.itertuples(index=False):
        candidates.append(
            {
                "origin_key": row.origin_key,
                "origin_name": row.origin_name,
                "target_station_id": row.target_station_id,
                "target_station_name": row.target_station_name,
                "target_station_no": row.target_station_no,
                "travel_time_min": float(row.travel_time_min),
                "resident_population_500m": float(row.resident_population_500m),
                "worker_population_500m": float(row.worker_population_500m),
                "buffer_area_m2": float(row.buffer_area_m2),
                "coverage_ratio": float(row.coverage_ratio) if pd.notna(row.coverage_ratio) else None,
                "intersected_grid_count": int(row.intersected_grid_count),
                "selected": False,
            }
        )

    selected_lookup = {
        (row["origin_key"], row["selected_station_id"]): True for row in selected_rows
    }
    for candidate in candidates:
        candidate["selected"] = bool(selected_lookup.get((candidate["origin_key"], candidate["target_station_id"]), False))

    return {
        "table": summary_rows,
        "selected": selected_rows,
        "candidates": candidates,
    }


def main() -> None:
    if not STATION_GEOJSON.exists():
        raise FileNotFoundError(STATION_GEOJSON)

    FRONTEND2_DATA.mkdir(parents=True, exist_ok=True)

    stations = gpd.read_file(STATION_GEOJSON)
    if stations.crs is None:
        stations = stations.set_crs(4326)
    else:
        stations = stations.to_crs(4326)

    grids = load_grids()
    results = weighted_station_totals(stations, grids)
    dashboard = build_dashboard_json(results)

    csv_df = pd.DataFrame(results.drop(columns="geometry"))
    csv_df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    OUTPUT_GEOJSON.write_text(results.to_crs(4326).to_json(drop_id=False, ensure_ascii=False), encoding="utf-8")
    OUTPUT_DASHBOARD_JSON.write_text(json.dumps(dashboard, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUT_DASHBOARD_JSON_LEGACY.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_DASHBOARD_JSON_LEGACY.write_text(json.dumps(dashboard, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"wrote {OUTPUT_CSV}")
    print(f"wrote {OUTPUT_GEOJSON}")
    print(f"wrote {OUTPUT_DASHBOARD_JSON}")
    print(f"stations: {len(results)}")


if __name__ == "__main__":
    main()
