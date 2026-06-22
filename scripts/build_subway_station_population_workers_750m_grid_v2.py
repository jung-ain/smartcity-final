from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point


ROOT = Path(__file__).resolve().parents[1]
RAW_GRID = Path(r"D:\smart_3\data\raw\_grid_border_grid_2025_grid_다사_grid_다사")
RAW_CENSUS = Path(r"D:\smart_3\data\raw\_census_reqdoc_1782063003002")
FRONTEND2_DATA = ROOT / "frontend2" / "public" / "data"
FRONTEND_DATA = ROOT / "frontend" / "public" / "data"
INVENTORY = ROOT / "data" / "inventory"

REACHABILITY_PATH = FRONTEND2_DATA / "transit_station_reachability_v2.geojson"
SUBWAY_NODES_PATH = FRONTEND2_DATA / "subway_nodes_2023_v2.geojson"
OUTPUT_CSV = FRONTEND2_DATA / "subway_station_population_workers_750m_grid_v2.csv"
OUTPUT_GEOJSON = FRONTEND2_DATA / "subway_station_population_workers_750m_grid_v2.geojson"
OUTPUT_JSON = FRONTEND2_DATA / "subway_station_population_workers_750m_grid_v2.json"
OUTPUT_CSV_LEGACY = FRONTEND_DATA / "subway_station_population_workers_750m_grid_v2.csv"
OUTPUT_GEOJSON_LEGACY = FRONTEND_DATA / "subway_station_population_workers_750m_grid_v2.geojson"
OUTPUT_JSON_LEGACY = FRONTEND_DATA / "subway_station_population_workers_750m_grid_v2.json"
METHODOLOGY_MD = INVENTORY / "subway_station_population_workers_750m_grid_v2_methodology.md"

BUFFER_M = 750.0
POPULATION_CODE = "to_in_001"
WORKER_CODE = "to_em_020"


def read_csv_robust(path: Path, **kwargs: Any) -> pd.DataFrame:
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


def find_one(base: Path, pattern: str) -> Path:
    matches = sorted(base.rglob(pattern))
    if len(matches) != 1:
        raise FileNotFoundError(f"expected exactly one match for {pattern!r}, found {len(matches)}")
    return matches[0]


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return "".join(str(value).split()).strip().lower()


def load_metric_table(path: Path, metric_code: str, value_col: str) -> pd.DataFrame:
    df = read_csv_robust(path, header=None, names=["sgis_year", "grid_code", "metric_code", value_col])
    df["grid_code"] = df["grid_code"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    df["metric_code"] = df["metric_code"].astype(str).str.strip()
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
    df = df[df["metric_code"].eq(metric_code)].copy()
    df = df.dropna(subset=["grid_code"])
    df = df.groupby("grid_code", as_index=False)[value_col].sum(min_count=1)
    return df


def load_grid_cells() -> gpd.GeoDataFrame:
    shp = find_one(RAW_GRID, "grid_다사_500M.shp")
    gdf = gpd.read_file(shp)
    if gdf.crs is None:
        gdf = gdf.set_crs(5179)
    else:
        gdf = gdf.to_crs(5179)
    gdf["grid_code"] = gdf["GRID_CD"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    gdf["grid_area_m2"] = gdf.geometry.area

    pop_csv = find_one(RAW_CENSUS, "2023년_인구_다사_500M.csv")
    worker_csv = find_one(RAW_CENSUS, "2023년_종사자_다사_500M.csv")
    pop_df = load_metric_table(pop_csv, POPULATION_CODE, "resident_population")
    worker_df = load_metric_table(worker_csv, WORKER_CODE, "worker_population")

    gdf = gdf.merge(pop_df, on="grid_code", how="left")
    gdf = gdf.merge(worker_df, on="grid_code", how="left")
    gdf["resident_population"] = gdf["resident_population"].fillna(0.0)
    gdf["worker_population"] = gdf["worker_population"].fillna(0.0)
    return gdf[["grid_code", "grid_area_m2", "resident_population", "worker_population", "geometry"]]


def load_reachability() -> gpd.GeoDataFrame:
    gdf = gpd.read_file(REACHABILITY_PATH)
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    else:
        gdf = gdf.to_crs(4326)
    gdf["origin_region_id"] = gdf["origin_region_id"].astype(str)
    gdf["origin_station_name"] = gdf["origin_station_name"].astype(str)
    gdf["station_name"] = gdf["station_name"].astype(str)
    gdf["station_norm"] = gdf["station_norm"].astype(str)
    gdf["line_name"] = gdf["line_name"].astype(str)
    gdf["threshold_min"] = pd.to_numeric(gdf["threshold_min"], errors="coerce")
    gdf["travel_time_min"] = pd.to_numeric(gdf["travel_time_min"], errors="coerce")
    gdf["station_key"] = (
        gdf["origin_region_id"].map(normalize_text)
        + "|"
        + gdf["origin_station_name"].map(normalize_text)
        + "|"
        + gdf["origin_station_line"].map(normalize_text)
        + "|"
        + gdf["station_name"].map(normalize_text)
        + "|"
        + gdf["line_name"].map(normalize_text)
    )
    gdf = gdf.sort_values(["origin_region_id", "origin_station_name", "travel_time_min", "threshold_min", "station_name", "line_name"], kind="stable")
    gdf = gdf.drop_duplicates("station_key", keep="first").copy()
    return gdf


def load_station_nodes() -> gpd.GeoDataFrame:
    gdf = gpd.read_file(SUBWAY_NODES_PATH)
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    else:
        gdf = gdf.to_crs(4326)
    gdf["node_id"] = pd.to_numeric(gdf["node_id"], errors="coerce")
    gdf["station_name"] = gdf["station_name"].astype(str)
    gdf["station_norm"] = gdf["station_norm"].astype(str)
    gdf["line_name"] = gdf["line_name"].astype(str)
    gdf["station_key_exact"] = gdf["station_name"].map(normalize_text) + "|" + gdf["line_name"].map(normalize_text)
    gdf["station_key_name"] = gdf["station_name"].map(normalize_text)
    return gdf


def attach_station_node(row: pd.Series, nodes: gpd.GeoDataFrame) -> dict[str, Any]:
    exact = nodes[nodes["station_key_exact"].eq(f"{normalize_text(row['station_name'])}|{normalize_text(row['line_name'])}")]
    fallback = nodes[nodes["station_key_name"].eq(normalize_text(row["station_name"]))]
    chosen = exact.iloc[0] if not exact.empty else (fallback.iloc[0] if not fallback.empty else None)

    if chosen is not None:
        geom = chosen.geometry
        lon = float(geom.x)
        lat = float(geom.y)
        node_id = int(chosen["node_id"]) if pd.notna(chosen["node_id"]) else None
        station_norm = str(chosen.get("station_norm") or row.get("station_norm") or row["station_name"])
        line_name = str(chosen.get("line_name") or row["line_name"])
        return {
            "node_id": node_id,
            "station_norm": station_norm,
            "longitude": lon,
            "latitude": lat,
            "geometry": Point(lon, lat),
            "representative_from": "node",
            "line_name": line_name,
        }

    geom = row.geometry
    if geom is None or geom.is_empty:
        return {
            "node_id": None,
            "station_norm": str(row.get("station_norm") or row["station_name"]),
            "longitude": None,
            "latitude": None,
            "geometry": None,
            "representative_from": "reachability",
            "line_name": str(row["line_name"]),
        }
    return {
        "node_id": None,
        "station_norm": str(row.get("station_norm") or row["station_name"]),
        "longitude": float(geom.x),
        "latitude": float(geom.y),
        "geometry": geom,
        "representative_from": "reachability",
        "line_name": str(row["line_name"]),
    }


def compute_station_totals(reachability: gpd.GeoDataFrame, grids: gpd.GeoDataFrame, nodes: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    grids_5179 = grids.to_crs(5179).copy()
    sindex = grids_5179.sindex

    rows: list[dict[str, Any]] = []
    for row in reachability.itertuples(index=False):
        row_series = pd.Series(row._asdict())
        node_info = attach_station_node(row_series, nodes)
        geom = node_info["geometry"] if node_info["geometry"] is not None else row.geometry
        if geom is None or geom.is_empty:
            continue

        point_gs = gpd.GeoSeries([geom], crs=4326).to_crs(5179)
        buffer = point_gs.iloc[0].buffer(BUFFER_M)
        candidate_idx = list(sindex.query(buffer, predicate="intersects"))

        resident_total = 0.0
        worker_total = 0.0
        covered_area_m2 = 0.0
        intersected_grid_count = 0

        for grid_idx in candidate_idx:
            grid = grids_5179.iloc[int(grid_idx)]
            inter = buffer.intersection(grid.geometry)
            if inter.is_empty:
                continue
            inter_area = float(inter.area)
            if inter_area <= 0:
                continue
            ratio = inter_area / float(grid.grid_area_m2) if float(grid.grid_area_m2) else 0.0
            resident_total += float(grid.resident_population) * ratio
            worker_total += float(grid.worker_population) * ratio
            covered_area_m2 += inter_area
            intersected_grid_count += 1

        buffer_area_m2 = float(buffer.area)
        rows.append(
            {
                "origin_region_id": str(row.origin_region_id),
                "origin_station_name": str(row.origin_station_name),
                "origin_station_line": str(row.origin_station_line) if hasattr(row, "origin_station_line") else None,
                "threshold_min": float(row.threshold_min) if pd.notna(row.threshold_min) else None,
                "station_name": str(row.station_name),
                "station_norm": str(node_info["station_norm"]),
                "line_name": str(node_info["line_name"] or row.line_name),
                "node_id": node_info["node_id"],
                "longitude": node_info["longitude"],
                "latitude": node_info["latitude"],
                "min_travel_time_min": float(row.travel_time_min) if pd.notna(row.travel_time_min) else None,
                "population_750m": round(resident_total, 3),
                "worker_750m": round(worker_total, 3),
                "buffer_area_m2": round(buffer_area_m2, 3),
                "covered_area_m2": round(covered_area_m2, 3),
                "coverage_ratio": round(covered_area_m2 / buffer_area_m2, 6) if buffer_area_m2 else None,
                "intersected_grid_count": int(intersected_grid_count),
                "geometry": point_gs.iloc[0],
            }
        )

    out = gpd.GeoDataFrame(rows, geometry="geometry", crs=5179)
    out = out.sort_values(
        ["origin_region_id", "origin_station_name", "min_travel_time_min", "station_name", "line_name", "node_id"],
        kind="stable",
    ).reset_index(drop=True)
    return out


def build_dashboard_json(results: gpd.GeoDataFrame) -> dict[str, Any]:
    if results.empty:
        return {
            "metadata": {
                "buffer_m": BUFFER_M,
                "methodology_note": "750m buffer around subway station points, aggregated from SGIS 500m DaSa grid cells with area-weighted intersection.",
            },
            "table": [],
            "selected": [],
            "candidates": [],
        }

    df = pd.DataFrame(results.drop(columns="geometry")).copy()
    df["score"] = df["population_750m"].fillna(0) + df["worker_750m"].fillna(0)
    table_rows: list[dict[str, Any]] = []
    selected_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []

    for (origin_region_id, origin_station_name, origin_station_line), subset in df.groupby(["origin_region_id", "origin_station_name", "origin_station_line"], sort=True):
        subset = subset.sort_values(["min_travel_time_min", "station_name", "line_name", "node_id"], kind="stable").copy()
        rep = subset.sort_values(["score", "min_travel_time_min", "population_750m", "worker_750m"], ascending=[False, True, False, False], kind="stable").iloc[0]

        table_rows.append(
            {
                "origin_region_id": origin_region_id,
                "station_name": origin_station_name,
                "origin_station_line": origin_station_line,
                "station_count": int(len(subset)),
                "mean_population_750m": float(subset["population_750m"].mean()),
                "mean_worker_750m": float(subset["worker_750m"].mean()),
                "max_population_750m": float(subset["population_750m"].max()),
                "max_worker_750m": float(subset["worker_750m"].max()),
                "representative_line_name": str(rep["line_name"]),
                "representative_node_id": int(rep["node_id"]) if pd.notna(rep["node_id"]) else None,
                "station_total_population_750m": float(subset["population_750m"].sum()),
                "station_total_worker_750m": float(subset["worker_750m"].sum()),
                "representative_travel_time_min": float(rep["min_travel_time_min"]),
            }
        )

        selected_rows.append(
            {
                "origin_region_id": origin_region_id,
                "origin_station_name": origin_station_name,
                "origin_station_line": origin_station_line,
                "station_name": str(rep["station_name"]),
                "line_name": str(rep["line_name"]),
                "node_id": int(rep["node_id"]) if pd.notna(rep["node_id"]) else None,
                "selected_travel_time_min": float(rep["min_travel_time_min"]),
                "population_750m": float(rep["population_750m"]),
                "worker_750m": float(rep["worker_750m"]),
                "station_total_population_750m": float(subset["population_750m"].sum()),
                "station_total_worker_750m": float(subset["worker_750m"].sum()),
                "buffer_area_m2": float(rep["buffer_area_m2"]),
                "coverage_ratio": float(rep["coverage_ratio"]) if pd.notna(rep["coverage_ratio"]) else None,
                "intersected_grid_count": int(rep["intersected_grid_count"]),
                "selected": True,
                "selection_reason": "highest area-weighted population+worker among reachable stations",
            }
        )

        for candidate in subset.itertuples(index=False):
            candidate_rows.append(
                {
                    "origin_region_id": candidate.origin_region_id,
                    "origin_station_name": candidate.origin_station_name,
                    "origin_station_line": candidate.origin_station_line,
                    "station_name": candidate.station_name,
                    "line_name": candidate.line_name,
                    "node_id": int(candidate.node_id) if pd.notna(candidate.node_id) else None,
                    "threshold_min": float(candidate.threshold_min) if pd.notna(candidate.threshold_min) else None,
                    "min_travel_time_min": float(candidate.min_travel_time_min) if pd.notna(candidate.min_travel_time_min) else None,
                    "population_750m": float(candidate.population_750m),
                    "worker_750m": float(candidate.worker_750m),
                    "buffer_area_m2": float(candidate.buffer_area_m2),
                    "coverage_ratio": float(candidate.coverage_ratio) if pd.notna(candidate.coverage_ratio) else None,
                    "intersected_grid_count": int(candidate.intersected_grid_count),
                    "selected": (
                        bool(
                            candidate.origin_region_id == rep["origin_region_id"]
                            and candidate.station_name == rep["station_name"]
                            and candidate.line_name == rep["line_name"]
                            and ((pd.isna(candidate.node_id) and pd.isna(rep["node_id"])) or candidate.node_id == rep["node_id"])
                        )
                    ),
                }
            )

    table_rows = sorted(table_rows, key=lambda row: row["origin_region_id"])
    selected_rows = sorted(selected_rows, key=lambda row: row["origin_region_id"])
    candidate_rows = sorted(candidate_rows, key=lambda row: (row["origin_region_id"], row["min_travel_time_min"] or 0.0, row["station_name"], row["line_name"]))

    return {
        "metadata": {
            "buffer_m": BUFFER_M,
            "source_reachability": str(REACHABILITY_PATH.name),
            "source_nodes": str(SUBWAY_NODES_PATH.name),
            "source_grid": str(find_one(RAW_GRID, "grid_다사_500M.shp").name),
            "source_census": ["2023년_인구_다사_500M.csv", "2023년_종사자_다사_500M.csv"],
            "methodology_note": "750m buffer around subway station points, aggregated from SGIS 500m DaSa grid cells with area-weighted intersection.",
        },
        "table": table_rows,
        "selected": selected_rows,
        "candidates": candidate_rows,
    }


def write_methodology_note() -> None:
    METHODOLOGY_MD.parent.mkdir(parents=True, exist_ok=True)
    METHODOLOGY_MD.write_text(
        "\n".join(
            [
                "# 지하철 역 750m 격자 기반 인구·종사자 산정",
                "",
                "- 공간단위: SGIS `다사 500M` 격자(`grid_다사_500M.shp`).",
                "- 원자료: `2023년_인구_다사_500M.csv`, `2023년_종사자_다사_500M.csv`.",
                "- 계산 방식: 각 역 중심점의 750m 버퍼와 격자 폴리곤의 교차 면적을 격자 면적으로 나눈 비율로 인구와 종사자를 면적가중 배분.",
                "- 750m는 직선거리 버퍼이며, 네트워크 도보권이 아니다.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    FRONTEND2_DATA.mkdir(parents=True, exist_ok=True)
    FRONTEND_DATA.mkdir(parents=True, exist_ok=True)
    INVENTORY.mkdir(parents=True, exist_ok=True)

    reachability = load_reachability()
    nodes = load_station_nodes()
    grids = load_grid_cells()
    results = compute_station_totals(reachability, grids, nodes)
    dashboard = build_dashboard_json(results)

    csv_df = pd.DataFrame(results.drop(columns="geometry"))
    csv_df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    csv_df.to_csv(OUTPUT_CSV_LEGACY, index=False, encoding="utf-8-sig")

    geojson_text = results.to_crs(4326).to_json(drop_id=False, ensure_ascii=False)
    OUTPUT_GEOJSON.write_text(geojson_text, encoding="utf-8")
    OUTPUT_GEOJSON_LEGACY.write_text(geojson_text, encoding="utf-8")

    json_text = json.dumps(dashboard, ensure_ascii=False, indent=2)
    OUTPUT_JSON.write_text(json_text, encoding="utf-8")
    OUTPUT_JSON_LEGACY.write_text(json_text, encoding="utf-8")

    write_methodology_note()

    print(f"wrote {OUTPUT_CSV}")
    print(f"wrote {OUTPUT_GEOJSON}")
    print(f"wrote {OUTPUT_JSON}")
    print(f"stations: {len(results)}")
    print(f"origins: {len(dashboard['selected'])}")


if __name__ == "__main__":
    main()
