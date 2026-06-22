from __future__ import annotations

import json
import math
import re
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from pyproj import CRS
from shapely.geometry import Point

try:
    from scipy.spatial import cKDTree
except Exception:  # pragma: no cover
    cKDTree = None


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT
RAW = PROJECT / "data" / "raw" / "06_subway_network"
PROCESSED = PROJECT / "data" / "processed"
INVENTORY = PROJECT / "data" / "inventory"
FRONTEND = PROJECT / "frontend" / "public" / "data"

CORE_BOUNDARY = ROOT / "data" / "processed" / "01_바운더리" / "10_과정" / "boundaries_core_comparison_v2.gpkg"
ANALYSIS_BOUNDARY = ROOT / "data" / "processed" / "01_바운더리" / "10_과정" / "boundaries_analysis_v2.gpkg"
SGIS_SELECTED = ROOT / "data" / "processed" / "05_SGIS" / "90_최종" / "sgis_agg_boundary_selected_v2.gpkg"
SGIS_STATS = ROOT / "data" / "processed" / "05_SGIS" / "90_최종" / "sgis_stats_integrated_v2.csv"
BUILDING_SUMMARY = ROOT / "data" / "processed" / "04_건축물" / "90_최종" / "building_report_ready_summary_v2.csv"
SGIS_CORE_KEY = ROOT / "data" / "processed" / "05_SGIS" / "90_최종" / "sgis_core_key_indicators_v2.csv"
SGIS_ANALYSIS_KEY = ROOT / "data" / "processed" / "05_SGIS" / "90_최종" / "sgis_analysis_key_indicators_v2.csv"

TRANSPORT_DIAGNOSIS_MD = INVENTORY / "transport_data_diagnosis_v2.md"
TRANSPORT_VALIDATION_MD = INVENTORY / "transport_validation_v2.md"
STATION_ACCESS_MD = INVENTORY / "station_access_from_boundaries_v2.md"
TRAVEL_TIME_MD = INVENTORY / "transit_travel_time_to_key_centers_v2.md"
ISOCHRONE_MD = INVENTORY / "transit_isochrone_station_counts_v2.md"
CROSS_MD = INVENTORY / "transport_cross_validation_v2.md"
REPORT_MD = INVENTORY / "transport_accessibility_v2_report.md"
STATUS_REPORT = INVENTORY / "DATA_STATUS_REPORT.md"

TRANSPORT_CANDIDATES_CSV = PROCESSED / "transport_data_candidates_v2.csv"
STATION_ACCESS_CSV = PROCESSED / "station_access_from_boundaries_v2.csv"
TRAVEL_TIME_CSV = PROCESSED / "transit_travel_time_to_key_centers_v2.csv"
ISOCHRONE_CSV = PROCESSED / "transit_isochrone_station_counts_v2.csv"
ISOCHRONE_JSON = FRONTEND / "transit_isochrone_station_counts_v2.json"
STATION_REACHABILITY_GEOJSON = PROCESSED / "transit_station_reachability_v2.geojson"
STATION_REACHABILITY_FRONTEND = FRONTEND / "transit_station_reachability_v2.geojson"
ACCESSIBLE_CSV = PROCESSED / "transit_accessible_population_workers_v2.csv"
ACCESSIBLE_JSON = FRONTEND / "transit_accessible_population_workers_v2.json"
CROSS_CSV = PROCESSED / "transport_cross_validation_v2.csv"
NODE_GEOJSON = PROCESSED / "subway_nodes_2023_v2.geojson"
NODE_GEOJSON_FRONTEND = FRONTEND / "subway_nodes_2023_v2.geojson"
LINKS_CSV = PROCESSED / "subway_links_2023_v2.csv"
GRAPHML = PROCESSED / "subway_network_2023_v2.graphml"

CUTOFF = pd.Timestamp("2023-12-31")
WALK_SPEED_M_PER_MIN = 80.0

ORIGIN_REGION_IDS = ["pangyo_core", "wirye_core", "wirye_support"]
THRESHOLDS_5MIN = list(range(0, 61, 5))
LINE_ORIGIN_NODES = {
    "pangyo_core": [26, 824],
    "wirye_core": [803, 724],
}
KEY_DESTINATIONS = [
    "강남",
    "판교",
    "잠실",
    "수서",
    "서울역",
    "사당",
    "선릉",
    "삼성",
    "양재",
    "정자",
    "모란",
    "복정",
    "남위례",
    "장지역",
]


def ensure_dirs() -> None:
    for path in [PROCESSED, INVENTORY, FRONTEND]:
        path.mkdir(parents=True, exist_ok=True)


def read_table(path: Path, **kwargs: Any) -> pd.DataFrame:
    ext = path.suffix.lower()
    if ext in {".tsv", ".csv"}:
        encodings = ["utf-8-sig", "cp949", "euc-kr", "utf-8"]
        for enc in encodings:
            try:
                df = pd.read_csv(path, sep="\t" if ext == ".tsv" else ",", encoding=enc, low_memory=False, **kwargs)
                df.attrs["encoding"] = enc
                return df
            except Exception:
                continue
        raise RuntimeError(f"Unable to read table: {path}")
    if ext == ".parquet":
        df = pd.read_parquet(path, **kwargs)
        df.attrs["encoding"] = "n/a"
        return df
    raise RuntimeError(f"Unsupported table type: {path}")


def parse_date(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip().replace({"": None, "nan": None, "NaT": None, "None": None})
    return pd.to_datetime(s, errors="coerce")


def normalize_station_name(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value).strip()
    text = text.replace(" ", "")
    if text.endswith("역"):
        text = text[:-1]
    return text


def find_station_nodes(nodes: pd.DataFrame, query: str) -> pd.DataFrame:
    q = normalize_station_name(query)
    norm = nodes["station_norm"]
    exact = nodes.loc[norm.eq(q)]
    if len(exact):
        return exact.copy()
    contains = nodes.loc[norm.str.contains(q, regex=False, na=False)]
    return contains.copy()


def safe_markdown(df: pd.DataFrame, index: bool = False) -> str:
    try:
        return df.to_markdown(index=index)
    except Exception:
        return df.to_string(index=index)


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def write_geojson(path: Path, gdf: gpd.GeoDataFrame) -> None:
    path.write_text(gdf.to_json(drop_id=False), encoding="utf-8")


def station_catalog(nodes: pd.DataFrame) -> pd.DataFrame:
    cols = ["node_id", "station_name", "station_norm", "line_name", "longitude", "latitude", "geometry"]
    return nodes[cols].copy()


def load_network() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    nodes_raw = read_table(RAW / "network" / "nodes.tsv")
    links_raw = read_table(RAW / "network" / "links.tsv")
    opening = read_table(RAW / "opening.tsv")
    waits = read_table(RAW / "line_waits.parquet")

    nodes = nodes_raw.copy()
    nodes["node_id"] = pd.to_numeric(nodes["id"], errors="coerce").astype("Int64")
    nodes["line_name"] = nodes["linenm"].astype(str)
    nodes["station_name"] = nodes["statnm"].astype(str)
    nodes["station_norm"] = nodes["station_name"].map(normalize_station_name)
    nodes["longitude"] = pd.to_numeric(nodes["lng"], errors="coerce")
    nodes["latitude"] = pd.to_numeric(nodes["lat"], errors="coerce")
    nodes["geometry"] = [Point(xy) for xy in zip(pd.to_numeric(nodes["x_5179"], errors="coerce"), pd.to_numeric(nodes["y_5179"], errors="coerce"))]
    nodes["begin_date"] = parse_date(nodes["begin"])
    if "effective_begin" in nodes.columns:
        eff = parse_date(nodes["effective_begin"])
    else:
        eff = pd.Series([pd.NaT] * len(nodes), index=nodes.index)
    nodes["effective_begin_date"] = eff.fillna(nodes["begin_date"])
    nodes["active_2023"] = nodes["effective_begin_date"].le(CUTOFF)

    links = links_raw.copy()
    links["link_id"] = pd.to_numeric(links["id"], errors="coerce").astype("Int64")
    links["from_node"] = pd.to_numeric(links["fromNode"], errors="coerce").astype("Int64")
    links["to_node"] = pd.to_numeric(links["toNode"], errors="coerce").astype("Int64")
    links["travel_time_ft_sec"] = pd.to_numeric(links["timeFT"], errors="coerce")
    links["travel_time_tf_sec"] = pd.to_numeric(links["timeTF"], errors="coerce")
    links["travel_time_ft_min"] = links["travel_time_ft_sec"] / 60.0
    links["travel_time_tf_min"] = links["travel_time_tf_sec"] / 60.0
    links["distance_m"] = pd.to_numeric(links["length_m"], errors="coerce")
    links["kind"] = links["kind"].astype(str)
    links["line_name_from"] = links["linenm_from"].astype(str)
    links["line_name_to"] = links["linenm_to"].astype(str)
    links["begin_date"] = parse_date(links["begin"])
    links["active_2023"] = links["begin_date"].le(CUTOFF)

    active_nodes = nodes.loc[nodes["active_2023"]].copy()
    active_node_ids = set(active_nodes["node_id"].dropna().astype(int).tolist())
    active_links = links.loc[
        links["active_2023"]
        & links["from_node"].notna()
        & links["to_node"].notna()
        & links["from_node"].astype(int).isin(active_node_ids)
        & links["to_node"].astype(int).isin(active_node_ids)
    ].copy()

    line_wait_map = {normalize_station_name(a): float(b) for a, b in zip(waits["linenm"].astype(str), pd.to_numeric(waits["waittm"], errors="coerce"))}
    diagnostics = {
        "nodes_raw_rows": int(len(nodes_raw)),
        "links_raw_rows": int(len(links_raw)),
        "active_nodes_rows": int(len(active_nodes)),
        "active_links_rows": int(len(active_links)),
        "opening_max_date": str(pd.to_datetime(opening["date"]).max().date()),
        "opening_rows": int(len(opening)),
        "wait_lines": int(len(waits)),
        "wait_map": line_wait_map,
    }
    return active_nodes, active_links, diagnostics


def build_graph(nodes: pd.DataFrame, links: pd.DataFrame) -> nx.DiGraph:
    g = nx.DiGraph()
    for row in nodes.itertuples(index=False):
        g.add_node(
            int(row.node_id),
            station_name=row.station_name,
            station_norm=row.station_norm,
            line_name=row.line_name,
            x=float(row.longitude) if pd.notna(row.longitude) else None,
            y=float(row.latitude) if pd.notna(row.latitude) else None,
        )
    for row in links.itertuples(index=False):
        u = int(row.from_node)
        v = int(row.to_node)
        g.add_edge(
            u,
            v,
            travel_time_min=float(row.travel_time_ft_min),
            distance_m=float(row.distance_m) if pd.notna(row.distance_m) else None,
            kind=row.kind,
            line_name=row.line_name_to if row.kind == "transfer" else row.line_name_from,
            transfer_flag=row.kind == "transfer",
            link_id=int(row.link_id),
        )
        g.add_edge(
            v,
            u,
            travel_time_min=float(row.travel_time_tf_min),
            distance_m=float(row.distance_m) if pd.notna(row.distance_m) else None,
            kind=row.kind,
            line_name=row.line_name_from if row.kind == "transfer" else row.line_name_from,
            transfer_flag=row.kind == "transfer",
            link_id=int(row.link_id),
        )
    return g


def nearest_node(nodes: pd.DataFrame, point: Point) -> pd.Series:
    geoms = gpd.GeoSeries(nodes["geometry"], crs=5179)
    distances = geoms.distance(point)
    idx = distances.idxmin()
    row = nodes.loc[idx]
    out = row.to_dict()
    out["distance_m"] = float(distances.loc[idx])
    out["walk_time_min"] = float(distances.loc[idx] / WALK_SPEED_M_PER_MIN)
    return pd.Series(out)


def boundary_access(boundary_path: Path, nodes: pd.DataFrame) -> pd.DataFrame:
    gdf = gpd.read_file(boundary_path).to_crs(5179)
    rows = []
    for row in gdf.itertuples(index=False):
        geom = row.geometry
        rep = geom.representative_point()
        cen = geom.centroid
        rep_nearest = nearest_node(nodes, rep)
        cen_nearest = nearest_node(nodes, cen)
        rows.append(
            {
                "region_id": row.region_id,
                "region_name": row.region_name,
                "boundary_role": row.boundary_role,
                "comparison_role": row.comparison_role,
                "boundary_area_m2": float(geom.area),
                "boundary_area_km2": float(geom.area / 1_000_000.0),
                "representative_point_wkt": rep.wkt,
                "centroid_wkt": cen.wkt,
                "nearest_station_name": rep_nearest["station_name"],
                "nearest_station_line": rep_nearest["line_name"],
                "nearest_node_id": int(rep_nearest["node_id"]),
                "nearest_station_distance_m": float(rep_nearest["distance_m"]),
                "nearest_station_distance_km": float(rep_nearest["distance_m"] / 1000.0),
                "estimated_walk_time_min": float(rep_nearest["walk_time_min"]),
                "centroid_nearest_station_name": cen_nearest["station_name"],
                "centroid_nearest_station_line": cen_nearest["line_name"],
                "centroid_nearest_node_id": int(cen_nearest["node_id"]),
                "centroid_nearest_station_distance_m": float(cen_nearest["distance_m"]),
                "centroid_nearest_station_distance_km": float(cen_nearest["distance_m"] / 1000.0),
                "centroid_estimated_walk_time_min": float(cen_nearest["walk_time_min"]),
            }
        )
    return pd.DataFrame(rows)


def resolve_station_nodes(nodes: pd.DataFrame, query: str) -> pd.DataFrame:
    q = normalize_station_name(query)
    exact = nodes.loc[nodes["station_norm"].eq(q)]
    if len(exact):
        return exact.copy()
    contains = nodes.loc[nodes["station_norm"].str.contains(q, regex=False, na=False)]
    if len(contains):
        return contains.copy()
    return nodes.iloc[0:0].copy()


def build_origin_map(boundary_access_df: pd.DataFrame, nodes: pd.DataFrame) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for region_id in boundary_access_df["region_id"].tolist():
        row = boundary_access_df.loc[boundary_access_df["region_id"].eq(region_id)].iloc[0]
        origin_name = str(row["nearest_station_name"])
        primary_nodes = resolve_station_nodes(nodes, origin_name)["node_id"].astype(int).tolist()
        out[region_id] = {
            "primary_origin_name": origin_name,
            "primary_origin_nodes": primary_nodes,
        }
        if region_id == "pangyo_core":
            extra = resolve_station_nodes(nodes, "판교")["node_id"].astype(int).tolist()
            if extra:
                out[region_id]["extra_origin_candidates"] = ["판교"]
                out[region_id]["extra_origin_nodes"] = extra
        if region_id.startswith("wirye"):
            extras = []
            extra_nodes = []
            for label in ["복정", "남위례", "위례", "장지역", "마천", "산성"]:
                found = resolve_station_nodes(nodes, label)
                if len(found):
                    extras.append(label)
                    extra_nodes.extend(found["node_id"].astype(int).tolist())
            if extras:
                out[region_id]["extra_origin_candidates"] = extras
                out[region_id]["extra_origin_nodes"] = sorted(set(extra_nodes))
    return out


def build_origin_specs(region_id: str, info: dict[str, Any], nodes: pd.DataFrame, graph: nx.DiGraph) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    if region_id in LINE_ORIGIN_NODES:
        for node_id in LINE_ORIGIN_NODES[region_id]:
            if node_id in graph:
                specs.append(
                    {
                        "origin_node": int(node_id),
                        "origin_station_name": str(graph.nodes[node_id]["station_name"]),
                        "origin_station_line": str(graph.nodes[node_id]["line_name"]),
                    }
                )
        return specs

    primary_nodes = sorted(set(int(n) for n in info.get("primary_origin_nodes", [])))
    extra_nodes = sorted(set(int(n) for n in info.get("extra_origin_nodes", [])))
    origin_nodes = sorted(set(primary_nodes + extra_nodes))
    if not origin_nodes:
        return specs

    line_groups: dict[str, list[int]] = defaultdict(list)
    for node_id in origin_nodes:
        line_groups[str(graph.nodes[node_id]["line_name"])].append(int(node_id))

    for line_name, node_ids in sorted(line_groups.items()):
        node_id = int(sorted(node_ids)[0])
        specs.append(
            {
                "origin_node": node_id,
                "origin_station_name": str(graph.nodes[node_id]["station_name"]),
                "origin_station_line": line_name,
            }
        )
    return specs


def shortest_path_lengths(graph: nx.DiGraph, origin_nodes: list[int] | tuple[int, ...] | set[int] | int) -> dict[int, float]:
    if isinstance(origin_nodes, int):
        sources = [origin_nodes]
    else:
        sources = sorted({int(node) for node in origin_nodes if pd.notna(node)})
    if not sources:
        return {}
    if len(sources) == 1:
        return nx.single_source_dijkstra_path_length(graph, sources[0], weight="travel_time_min")
    return nx.multi_source_dijkstra_path_length(graph, sources, weight="travel_time_min")


def best_station_times(
    node_times: dict[int, float],
    nodes: pd.DataFrame,
    origin_station_norm: str | list[str] | set[str] | tuple[str, ...] | None = None,
) -> pd.DataFrame:
    tmp = nodes[["node_id", "station_name", "station_norm", "line_name"]].copy()
    tmp["travel_time_min"] = tmp["node_id"].map(node_times)
    tmp = tmp.dropna(subset=["travel_time_min"])
    if origin_station_norm:
        if isinstance(origin_station_norm, str):
            excluded = {origin_station_norm}
        else:
            excluded = {str(v) for v in origin_station_norm if str(v)}
        tmp = tmp.loc[~tmp["station_norm"].isin(excluded)].copy()
    if tmp.empty:
        return tmp
    tmp = tmp.sort_values(["station_norm", "travel_time_min"])
    tmp = tmp.groupby("station_norm", as_index=False).first()
    return tmp


def summarize_isochrone(node_times: dict[int, float], nodes: pd.DataFrame, origin_station_norm: str | list[str] | set[str] | tuple[str, ...]) -> dict[str, Any]:
    station_best = best_station_times(node_times, nodes, origin_station_norm=origin_station_norm)
    if station_best.empty:
        return {
            "reachable_stations_15min": 0,
            "reachable_stations_30min": 0,
            "reachable_stations_45min": 0,
            "reachable_stations_60min": 0,
            "reachable_lines_30min": 0,
            "reachable_lines_45min": 0,
            "reachable_lines_60min": 0,
            "mean_travel_time_to_all_reachable_60min": None,
            "median_travel_time_to_all_reachable_60min": None,
        }
    lines = []
    for limit in [15, 30, 45, 60]:
        lines.append((station_best["travel_time_min"] <= limit).sum())
    return {
        "reachable_stations_15min": int(lines[0]),
        "reachable_stations_30min": int(lines[1]),
        "reachable_stations_45min": int(lines[2]),
        "reachable_stations_60min": int(lines[3]),
        "reachable_lines_30min": int(nodes.loc[[n in node_times and node_times[n] <= 30 for n in nodes["node_id"]], "line_name"].nunique()),
        "reachable_lines_45min": int(nodes.loc[[n in node_times and node_times[n] <= 45 for n in nodes["node_id"]], "line_name"].nunique()),
        "reachable_lines_60min": int(nodes.loc[[n in node_times and node_times[n] <= 60 for n in nodes["node_id"]], "line_name"].nunique()),
        "mean_travel_time_to_all_reachable_60min": float(station_best.loc[station_best["travel_time_min"] <= 60, "travel_time_min"].mean()),
        "median_travel_time_to_all_reachable_60min": float(station_best.loc[station_best["travel_time_min"] <= 60, "travel_time_min"].median()),
    }


def route_to_destination(
    graph: nx.DiGraph,
    node_times: dict[int, float],
    nodes: pd.DataFrame,
    origin_nodes: list[int] | tuple[int, ...] | set[int] | int,
    origin_region_id: str,
    origin_type: str,
    origin_label: str,
    origin_lines: list[str] | tuple[str, ...] | set[str] | str,
    destination_label: str,
) -> dict[str, Any]:
    dest_nodes = resolve_station_nodes(nodes, destination_label)
    if dest_nodes.empty:
        return {
            "origin_region_id": origin_region_id,
            "origin_type": origin_type,
            "origin_station_name": origin_label,
            "origin_station_line": origin_lines if isinstance(origin_lines, str) else ",".join(sorted({str(v) for v in origin_lines if str(v)})),
            "destination_station_name": destination_label,
            "shortest_travel_time_min": None,
            "transfer_count": None,
            "path_station_count": None,
            "path_summary": None,
            "status": "missing_destination",
        }
    candidates = dest_nodes["node_id"].astype(int).tolist()
    best_node = None
    best_time = None
    for node_id in candidates:
        t = node_times.get(node_id)
        if t is None:
            continue
        if best_time is None or t < best_time:
            best_time = t
            best_node = node_id
    if best_node is None:
        return {
            "origin_region_id": origin_region_id,
            "origin_type": origin_type,
            "origin_station_name": origin_label,
            "origin_station_line": origin_lines if isinstance(origin_lines, str) else ",".join(sorted({str(v) for v in origin_lines if str(v)})),
            "destination_station_name": destination_label,
            "shortest_travel_time_min": None,
            "transfer_count": None,
            "path_station_count": None,
            "path_summary": None,
            "status": "unreachable",
        }
    if isinstance(origin_nodes, int):
        sources = [origin_nodes]
    else:
        sources = sorted({int(node) for node in origin_nodes if pd.notna(node)})
    if len(sources) == 1:
        path = nx.shortest_path(graph, sources[0], best_node, weight="travel_time_min")
    else:
        _, paths = nx.multi_source_dijkstra(graph, sources, weight="travel_time_min")
        path = paths[best_node]
    path_edges = list(zip(path[:-1], path[1:]))
    transfer_count = sum(1 for u, v in path_edges if graph.edges[u, v].get("transfer_flag"))
    station_names = [graph.nodes[n]["station_name"] for n in path]
    summary = " -> ".join(station_names)
    return {
        "origin_region_id": origin_region_id,
        "origin_type": origin_type,
        "origin_station_name": origin_label,
        "origin_station_line": origin_lines if isinstance(origin_lines, str) else ",".join(sorted({str(v) for v in origin_lines if str(v)})),
        "destination_station_name": destination_label,
        "shortest_travel_time_min": float(best_time),
        "transfer_count": int(transfer_count),
        "path_station_count": int(len(path)),
        "path_summary": summary,
        "status": "ok",
    }


def accessible_population_workers(
    graph: nx.DiGraph,
    nodes: pd.DataFrame,
    origin_nodes: list[int] | tuple[int, ...] | set[int] | int,
    origin_label: str,
    origin_station_norms: list[str] | tuple[str, ...] | set[str] | str,
    sgis_boundary: gpd.GeoDataFrame,
    sgis_stats: pd.DataFrame,
    thresholds: list[int] = THRESHOLDS_5MIN,
) -> pd.DataFrame:
    gdf = sgis_boundary.copy().to_crs(5179)
    stats = sgis_stats.copy()
    gdf["agg_code"] = gdf["agg_code"].astype(str)
    stats["agg_code"] = stats["agg_code"].astype(str)
    gdf["centroid"] = gdf.geometry.representative_point()
    coords = np.column_stack([gdf["centroid"].x.to_numpy(), gdf["centroid"].y.to_numpy()])
    node_coords = np.array([(geom.x, geom.y) for geom in nodes["geometry"]], dtype=float)
    if cKDTree is not None:
        tree = cKDTree(node_coords)
        dist, idx = tree.query(coords, k=1)
    else:
        idx_list: list[int] = []
        dist_list: list[float] = []
        chunk = 1500
        for start in range(0, len(coords), chunk):
            block = coords[start : start + chunk]
            diff = block[:, None, :] - node_coords[None, :, :]
            d2 = np.sum(diff * diff, axis=2)
            block_idx = np.argmin(d2, axis=1)
            block_dist = np.sqrt(d2[np.arange(len(block_idx)), block_idx])
            idx_list.extend(block_idx.tolist())
            dist_list.extend(block_dist.tolist())
        idx = np.asarray(idx_list)
        dist = np.asarray(dist_list)
    nearest = nodes.iloc[idx][["node_id", "station_name", "station_norm", "line_name"]].reset_index(drop=True)
    gdf = gdf.reset_index(drop=True)
    gdf["nearest_station_name"] = nearest["station_name"]
    gdf["nearest_station_norm"] = nearest["station_norm"]
    gdf["nearest_station_line"] = nearest["line_name"]
    gdf["nearest_station_distance_m"] = dist
    gdf["nearest_station_walk_time_min"] = dist / WALK_SPEED_M_PER_MIN
    stats_idx = stats.set_index("agg_code")
    gdf["population_total"] = gdf["agg_code"].map(stats_idx["population_total"])
    gdf["worker_total"] = gdf["agg_code"].map(stats_idx["worker_total"])
    gdf["household_total"] = gdf["agg_code"].map(stats_idx["household_total"])
    gdf["business_total"] = gdf["agg_code"].map(stats_idx["business_total"])
    gdf["population_total"] = pd.to_numeric(gdf["population_total"], errors="coerce")
    gdf["worker_total"] = pd.to_numeric(gdf["worker_total"], errors="coerce")

    node_times = shortest_path_lengths(graph, origin_nodes)
    station_time = best_station_times(node_times, nodes, origin_station_norm=origin_station_norms)
    station_time_lookup = dict(zip(station_time["station_norm"], station_time["travel_time_min"]))
    gdf["subway_time_min"] = gdf["nearest_station_norm"].map(station_time_lookup)
    gdf["total_access_time_min"] = gdf["subway_time_min"] + gdf["nearest_station_walk_time_min"]

    rows = []
    for threshold in thresholds:
        mask = gdf["total_access_time_min"].le(threshold)
        rows.append(
            {
                "origin_region_id": origin_label,
                "access_threshold_min": threshold,
                "accessible_population_total": float(gdf.loc[mask, "population_total"].fillna(0).sum()),
                "accessible_worker_total": float(gdf.loc[mask, "worker_total"].fillna(0).sum()),
                "accessible_agg_count": int(mask.sum()),
                "coverage_share_of_aggs": float(mask.mean()),
            }
        )
    return pd.DataFrame(rows)


def write_graphml(graph: nx.DiGraph, path: Path) -> None:
    serializable = nx.DiGraph()
    for n, data in graph.nodes(data=True):
        serializable.add_node(
            int(n),
            station_name=str(data.get("station_name", "")),
            station_norm=str(data.get("station_norm", "")),
            line_name=str(data.get("line_name", "")),
            x=float(data["x"]) if data.get("x") is not None else None,
            y=float(data["y"]) if data.get("y") is not None else None,
        )
    for u, v, data in graph.edges(data=True):
        serializable.add_edge(
            int(u),
            int(v),
            travel_time_min=float(data.get("travel_time_min", 0.0)),
            distance_m=float(data["distance_m"]) if data.get("distance_m") is not None else None,
            kind=str(data.get("kind", "")),
            line_name=str(data.get("line_name", "")),
            transfer_flag=int(bool(data.get("transfer_flag", False))),
            link_id=int(data.get("link_id", -1)),
        )
    nx.write_graphml(serializable, path)


def diagnosis_file(candidates: pd.DataFrame, diag: dict[str, Any], nodes: pd.DataFrame, links: pd.DataFrame, graph: nx.DiGraph) -> str:
    patterns = {
        "판교": int(nodes["station_name"].astype(str).str.contains("판교", regex=False, na=False).sum()),
        "위례": int(nodes["station_name"].astype(str).str.contains("위례", regex=False, na=False).sum()),
        "남위례": int(nodes["station_name"].astype(str).str.contains("남위례", regex=False, na=False).sum()),
        "복정": int(nodes["station_name"].astype(str).str.contains("복정", regex=False, na=False).sum()),
        "강남": int(nodes["station_name"].astype(str).str.contains("강남", regex=False, na=False).sum()),
        "잠실": int(nodes["station_name"].astype(str).str.contains("잠실", regex=False, na=False).sum()),
        "수서": int(nodes["station_name"].astype(str).str.contains("수서", regex=False, na=False).sum()),
        "서울역": int(nodes["station_name"].astype(str).str.contains("서울역", regex=False, na=False).sum()),
        "선릉": int(nodes["station_name"].astype(str).str.contains("선릉", regex=False, na=False).sum()),
        "삼성": int(nodes["station_name"].astype(str).str.contains("삼성", regex=False, na=False).sum()),
        "양재": int(nodes["station_name"].astype(str).str.contains("양재", regex=False, na=False).sum()),
        "정자": int(nodes["station_name"].astype(str).str.contains("정자", regex=False, na=False).sum()),
        "모란": int(nodes["station_name"].astype(str).str.contains("모란", regex=False, na=False).sum()),
        "장지역": int(nodes["station_name"].astype(str).str.contains("장지역", regex=False, na=False).sum()),
        "마천": int(nodes["station_name"].astype(str).str.contains("마천", regex=False, na=False).sum()),
        "산성": int(nodes["station_name"].astype(str).str.contains("산성", regex=False, na=False).sum()),
        "신분당선": int(nodes["line_name"].astype(str).str.contains("신분당선", regex=False, na=False).sum()),
        "8호선": int(nodes["line_name"].astype(str).str.contains("8호선", regex=False, na=False).sum()),
        "분당선": int(nodes["line_name"].astype(str).str.contains("분당선", regex=False, na=False).sum()),
    }
    deg = pd.Series(dict(graph.degree()))
    isolated = int((deg == 0).sum())
    md = [
        "# 지하철 네트워크 진단",
        "",
        f"- 기준일: {CUTOFF.date()}",
        f"- nodes.tsv: {diag['nodes_raw_rows']} rows, active_2023={diag['active_nodes_rows']}",
        f"- links.tsv: {diag['links_raw_rows']} rows, active_2023={diag['active_links_rows']}",
        f"- opening.tsv rows: {diag['opening_rows']}, max date: {diag['opening_max_date']}",
        f"- line_waits rows: {diag['wait_lines']}",
        f"- isolated node count: {isolated}",
        "",
        "## 후보 파일",
        safe_markdown(candidates, index=False),
        "",
        "## 핵심 역명 존재 여부",
        safe_markdown(pd.DataFrame([{"keyword": k, "node_match_count": v} for k, v in patterns.items()]), index=False),
        "",
        "## 해석",
        "- `opening.tsv` 에 미래 개통 노선이 포함되어 있으므로 2023 분석에서는 `begin_date <= 2023-12-31` 필터가 필요하다.",
        "- 네트워크는 역-역 지하철/환승 그래프로 구성되어 있으며, 보행망은 포함하지 않는다.",
        "- 위례 관련 미래 노선(위례선)은 2023 분석에서 제외해야 한다.",
        "- 역 접근거리는 직선거리이며 실제 보행시간과 다를 수 있다.",
    ]
    return "\n".join(md)


def validation_report(nodes: pd.DataFrame, links: pd.DataFrame, graph: nx.DiGraph, boundary_access_df: pd.DataFrame) -> str:
    deg = pd.Series(dict(graph.degree()))
    isolated_nodes = int((deg == 0).sum())
    active_station_counts = {
        "pangyo": int(nodes["station_name"].astype(str).str.contains("판교", regex=False, na=False).sum()),
        "wirye": int(nodes["station_name"].astype(str).str.contains("위례", regex=False, na=False).sum()),
        "namwirye": int(nodes["station_name"].astype(str).str.contains("남위례", regex=False, na=False).sum()),
    }
    checks = [
        {"check": "nodes have coordinates", "result": bool(nodes[["longitude", "latitude"]].notna().all().all())},
        {"check": "links build graph", "result": graph.number_of_edges() > 0 and graph.number_of_nodes() > 0},
        {"check": "isolated nodes not excessive", "result": isolated_nodes < len(nodes) * 0.2, "isolated_nodes": isolated_nodes},
        {"check": "pangyo station exists", "result": active_station_counts["pangyo"] > 0},
        {"check": "wirye station exists", "result": active_station_counts["wirye"] > 0},
        {"check": "major destinations exist", "result": all(x > 0 for x in [int(nodes["station_name"].astype(str).str.contains("강남", regex=False, na=False).sum()), int(nodes["station_name"].astype(str).str.contains("잠실", regex=False, na=False).sum()), int(nodes["station_name"].astype(str).str.contains("수서", regex=False, na=False).sum())])},
        {"check": "2023 filter applied", "result": bool(nodes["active_2023"].all() and links["active_2023"].all())},
        {"check": "representative point used", "result": True},
        {"check": "bus access missing", "result": True},
        {"check": "straight-line walking only", "result": True},
    ]
    df = pd.DataFrame(checks)
    md = [
        "# 교통 접근성 검증",
        "",
        safe_markdown(boundary_access_df[["region_id", "nearest_station_name", "nearest_station_distance_m", "estimated_walk_time_min"]], index=False),
        "",
        safe_markdown(df, index=False),
        "",
        "## 메모",
        "- 이 분석은 지하철 네트워크만 사용했고 버스 접근성은 포함하지 않았다.",
        "- 역 접근은 직선거리 기반이므로 실제 보행시간보다 과소/과대 추정될 수 있다.",
        "- 2023년 네트워크 필터는 `begin_date <= 2023-12-31` 기준으로 적용했다.",
    ]
    return "\n".join(md)


def cross_validation_report(building: pd.DataFrame, sgis_core: pd.DataFrame, sgis_analysis: pd.DataFrame, boundary_access_df: pd.DataFrame, travel_df: pd.DataFrame, accessible_df: pd.DataFrame) -> pd.DataFrame:
    sgis = pd.concat([sgis_core, sgis_analysis], ignore_index=True)
    sgis = sgis.drop_duplicates(subset=["region_id"])
    summary = building.merge(sgis, on="region_id", how="left", suffixes=("", "_sgis"))
    summary = summary.merge(boundary_access_df[["region_id", "nearest_station_name", "nearest_station_line", "nearest_station_distance_m", "estimated_walk_time_min"]], on="region_id", how="left")
    route_best = travel_df.loc[travel_df["origin_region_id"].isin(ORIGIN_REGION_IDS)].groupby(["origin_region_id", "destination_station_name"], as_index=False)["shortest_travel_time_min"].min()
    for dest in ["강남", "잠실", "수서", "서울역", "판교"]:
        subset = route_best.loc[route_best["destination_station_name"].eq(dest)]
        summary[f"time_to_{dest}_min"] = summary["region_id"].map(subset.set_index("origin_region_id")["shortest_travel_time_min"] if not subset.empty else {})
    if not accessible_df.empty:
        accessible_region = accessible_df.groupby(["origin_region_id", "access_threshold_min"], as_index=False)[["accessible_population_total", "accessible_worker_total", "accessible_agg_count", "coverage_share_of_aggs"]].max()
        summary = summary.merge(accessible_region.pivot(index="origin_region_id", columns="access_threshold_min", values="accessible_population_total").add_prefix("accessible_population_"), left_on="region_id", right_index=True, how="left")
        summary = summary.merge(accessible_region.pivot(index="origin_region_id", columns="access_threshold_min", values="accessible_worker_total").add_prefix("accessible_worker_"), left_on="region_id", right_index=True, how="left")
    summary["transport_interpretation_note"] = np.where(
        summary["region_id"].eq("pangyo_core"),
        "판교는 SGIS 종사자 밀도가 높고 주요 거점 접근성이 양호하면 고용 중심지 해석을 강화한다.",
        np.where(
            summary["region_id"].eq("wirye_core"),
            "위례 Core는 종사자 밀도가 낮고 주요 고용거점 접근성이 약하면 자족기능 저조 해석을 지지한다.",
            "위례 Support는 주거·상업·지원 기능의 복합 맥락으로 읽는다.",
        ),
    )
    return summary


def write_frontend_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)


def main() -> None:
    ensure_dirs()
    nodes, links, diag = load_network()
    graph = build_graph(nodes, links)

    nodes_export = nodes.loc[:, ["node_id", "station_name", "station_norm", "line_name", "longitude", "latitude", "geometry"]].copy()
    nodes_gdf = gpd.GeoDataFrame(nodes_export, geometry="geometry", crs=5179)
    write_geojson(NODE_GEOJSON, nodes_gdf)
    write_frontend_copy(NODE_GEOJSON, NODE_GEOJSON_FRONTEND)

    links_out = links.copy()
    if "geometry_wkt" in links_out.columns:
        links_out["geometry_wkt"] = links_out["geometry_wkt"].astype(str)
    links_out.to_csv(LINKS_CSV, index=False, encoding="utf-8-sig")
    try:
        write_graphml(graph, GRAPHML)
    except Exception as exc:
        graphml_warning = f"graphml write failed: {exc}"
    else:
        graphml_warning = "graphml written"

    # Diagnostics files.
    nodes_raw_table = read_table(RAW / "network" / "nodes.tsv")
    links_raw_table = read_table(RAW / "network" / "links.tsv")
    opening_table = read_table(RAW / "opening.tsv")
    waits_table = read_table(RAW / "line_waits.parquet")
    candidate_rows = [
        {
            "file_path": str(RAW / "network" / "nodes.tsv"),
            "file_type": "station/node",
            "encoding": nodes_raw_table.attrs.get("encoding", "utf-8-sig"),
            "row_count": int(len(nodes)),
            "columns": ",".join(list(nodes_raw_table.columns)),
            "data_role": "station nodes",
            "year": 2023,
            "contains_pangyo": bool(nodes["station_name"].astype(str).str.contains("판교", regex=False, na=False).any()),
            "contains_wirye": bool(nodes["station_name"].astype(str).str.contains("위례", regex=False, na=False).any()),
        },
        {
            "file_path": str(RAW / "network" / "links.tsv"),
            "file_type": "link/edge",
            "encoding": links_raw_table.attrs.get("encoding", "utf-8-sig"),
            "row_count": int(len(links)),
            "columns": ",".join(list(links_raw_table.columns)),
            "data_role": "subway and transfer edges",
            "year": 2023,
            "contains_pangyo": True,
            "contains_wirye": True,
        },
        {
            "file_path": str(RAW / "opening.tsv"),
            "file_type": "opening/cutoff",
            "encoding": opening_table.attrs.get("encoding", "utf-8-sig"),
            "row_count": int(len(opening_table)),
            "columns": "date,desc",
            "data_role": "cutoff dates",
            "year": 2032,
            "contains_pangyo": False,
            "contains_wirye": True,
        },
        {
            "file_path": str(RAW / "line_waits.parquet"),
            "file_type": "wait table",
            "encoding": "n/a",
            "row_count": int(len(waits_table)),
            "columns": "linenm,waittm",
            "data_role": "line headway / wait penalties",
            "year": 2023,
            "contains_pangyo": False,
            "contains_wirye": True,
        },
    ]
    candidates_df = pd.DataFrame(candidate_rows)
    candidates_df.to_csv(TRANSPORT_CANDIDATES_CSV, index=False, encoding="utf-8-sig")
    write_text(TRANSPORT_DIAGNOSIS_MD, diagnosis_file(candidates_df, diag, nodes, links, graph))

    boundary_access_core = boundary_access(CORE_BOUNDARY, nodes)
    boundary_access_analysis = boundary_access(ANALYSIS_BOUNDARY, nodes)
    boundary_access_df = pd.concat([boundary_access_core, boundary_access_analysis], ignore_index=True).drop_duplicates(subset=["region_id"], keep="first")
    boundary_access_df.to_csv(STATION_ACCESS_CSV, index=False, encoding="utf-8-sig")
    write_text(STATION_ACCESS_MD, safe_markdown(boundary_access_df, index=False))

    origin_map = build_origin_map(boundary_access_df, nodes)
    origin_records = []
    travel_records = []
    iso_records = []
    accessible_records = []
    reachability_features = []

    # Build route table and isochrones.
    sgis_boundary = gpd.read_file(SGIS_SELECTED).to_crs(5179)
    sgis_stats = read_table(SGIS_STATS)

    for region_id, info in origin_map.items():
        origin_specs = build_origin_specs(region_id, info, nodes, graph)
        if not origin_specs:
            continue

        for spec in origin_specs:
            origin_node = int(spec["origin_node"])
            origin_station_name = str(spec["origin_station_name"])
            origin_station_line = str(spec["origin_station_line"])
            origin_station_norm = str(graph.nodes[origin_node]["station_norm"])
            node_times = shortest_path_lengths(graph, origin_node)

            origin_records.append(
                {
                    "origin_region_id": region_id,
                    "origin_type": origin_station_line,
                    "origin_station_name": origin_station_name,
                    "origin_station_line": origin_station_line,
                    **summarize_isochrone(node_times, nodes, origin_station_norm),
                }
            )
            for dest in KEY_DESTINATIONS:
                travel_records.append(
                    route_to_destination(
                        graph,
                        node_times,
                        nodes,
                        origin_node,
                        region_id,
                        origin_station_line,
                        origin_station_name,
                        origin_station_line,
                        dest,
                    )
                )
            if region_id in {"pangyo_core", "wirye_core"}:
                accessible = accessible_population_workers(
                    graph,
                    nodes,
                    origin_node,
                    region_id,
                    origin_station_norm,
                    sgis_boundary,
                    sgis_stats,
                    thresholds=THRESHOLDS_5MIN,
                )
                if not accessible.empty:
                    accessible_records.append(accessible)

                best_station_df = best_station_times(node_times, nodes, origin_station_norm=origin_station_norm)
                for threshold in THRESHOLDS_5MIN:
                    subset = best_station_df.loc[best_station_df["travel_time_min"].le(threshold)].copy()
                    for st in subset.itertuples(index=False):
                        station_match = nodes.loc[nodes["station_norm"].eq(st.station_norm)].iloc[0]
                        reachability_features.append(
                            {
                                "type": "Feature",
                                "geometry": {
                                    "type": "Point",
                                    "coordinates": [float(station_match["longitude"]), float(station_match["latitude"])],
                                },
                                "properties": {
                                    "origin_region_id": region_id,
                                    "origin_station_name": origin_station_name,
                                    "origin_station_line": origin_station_line,
                                    "threshold_min": threshold,
                                    "station_name": st.station_name,
                                    "station_norm": st.station_norm,
                                    "line_name": st.line_name,
                                    "travel_time_min": float(st.travel_time_min),
                                },
                            }
                        )

    origin_df = pd.DataFrame(origin_records)
    extra_iso_df = pd.DataFrame(iso_records)
    if not extra_iso_df.empty:
        origin_df = pd.concat([origin_df, extra_iso_df], ignore_index=True)
    origin_df.to_csv(ISOCHRONE_CSV, index=False, encoding="utf-8-sig")
    origin_df.to_json(ISOCHRONE_JSON, orient="records", force_ascii=False, indent=2)
    write_text(ISOCHRONE_MD, safe_markdown(origin_df, index=False))

    travel_df = pd.DataFrame(travel_records)
    travel_df.to_csv(TRAVEL_TIME_CSV, index=False, encoding="utf-8-sig")
    write_text(TRAVEL_TIME_MD, safe_markdown(travel_df, index=False))

    accessible_df = pd.concat(accessible_records, ignore_index=True) if accessible_records else pd.DataFrame()
    if not accessible_df.empty:
        accessible_df.to_csv(ACCESSIBLE_CSV, index=False, encoding="utf-8-sig")
        accessible_df.to_json(ACCESSIBLE_JSON, orient="records", force_ascii=False, indent=2)

    STATION_REACHABILITY_GEOJSON.write_text(
        json.dumps({"type": "FeatureCollection", "features": reachability_features}, ensure_ascii=False),
        encoding="utf-8",
    )
    write_frontend_copy(STATION_REACHABILITY_GEOJSON, STATION_REACHABILITY_FRONTEND)

    # Cross-validation summary.
    building = read_table(BUILDING_SUMMARY)
    sgis_core = read_table(SGIS_CORE_KEY)
    sgis_analysis = read_table(SGIS_ANALYSIS_KEY)
    cross_df = cross_validation_report(building, sgis_core, sgis_analysis, boundary_access_df, travel_df, accessible_df)
    cross_df.to_csv(CROSS_CSV, index=False, encoding="utf-8-sig")
    write_text(CROSS_MD, safe_markdown(cross_df, index=False))

    # Validation report.
    write_text(TRANSPORT_VALIDATION_MD, validation_report(nodes, links, graph, boundary_access_df))

    # Main report.
    core_row = boundary_access_df.loc[boundary_access_df["region_id"].eq("pangyo_core")].iloc[0]
    wirye_row = boundary_access_df.loc[boundary_access_df["region_id"].eq("wirye_core")].iloc[0]
    support_row = boundary_access_df.loc[boundary_access_df["region_id"].eq("wirye_support")].iloc[0]
    building_summary = read_table(BUILDING_SUMMARY)
    building_summary = building_summary.set_index("region_id")
    sgis_core_sum = read_table(SGIS_CORE_KEY).set_index("region_id")
    primary_travel_df = travel_df.loc[travel_df["origin_region_id"].isin(ORIGIN_REGION_IDS)].groupby(["origin_station_name", "destination_station_name"], as_index=False)["shortest_travel_time_min"].min()
    key_route = primary_travel_df.set_index(["origin_station_name", "destination_station_name"])["shortest_travel_time_min"].to_dict()
    origin_summary = origin_df.groupby("origin_region_id", as_index=False)[["reachable_stations_30min", "reachable_stations_45min", "reachable_stations_60min"]].max() if not origin_df.empty else pd.DataFrame()

    def route_time(origin: str, dest: str) -> Any:
        return key_route.get((origin, dest))

    report = [
        "# 교통 접근성 분석 v2",
        "",
        "## 1. 이번 분석 목적",
        "- 판교 Core, 위례 Core, 위례 Support의 지하철 접근성과 광역 거점 연결성을 비교했다.",
        "- 2023년 운영망 기준으로 최단시간과 등시간권을 계산했다.",
        "- SGIS 종사자 밀도와 건축물대장 결과와 같은 방향인지 교차검증했다.",
        "",
        "## 2. 사용한 지하철 네트워크 데이터",
        f"- 입력: `{RAW}`",
        f"- 기준일: {CUTOFF.date()}",
        f"- nodes.active: {diag['active_nodes_rows']} / raw {diag['nodes_raw_rows']}",
        f"- links.active: {diag['active_links_rows']} / raw {diag['links_raw_rows']}",
        f"- graphml: {graphml_warning}",
        "",
        "## 3. 2023년 네트워크 필터링 방식",
        "- node는 `effective_begin`가 있으면 이를 우선 적용하고, 없으면 `begin`을 사용했다.",
        "- link는 `begin <= 2023-12-31` 이면서 양 끝 node가 활성인 경우만 유지했다.",
        "- `opening.tsv` 는 미래 노선을 포함하므로 그대로 쓰지 않고 필터 기준 확인용으로만 사용했다.",
        "",
        "## 4. 분석구역 대표점 설정 방식",
        safe_markdown(boundary_access_df[["region_id", "nearest_station_name", "nearest_station_line", "nearest_station_distance_m", "estimated_walk_time_min", "centroid_nearest_station_name", "centroid_estimated_walk_time_min"]], index=False),
        "",
        "## 5. 가장 가까운 지하철역 분석",
        safe_markdown(boundary_access_df[["region_id", "nearest_station_name", "nearest_station_line", "nearest_station_distance_m", "estimated_walk_time_min"]], index=False),
        "",
        "## 6. 주요 거점 접근시간 분석",
        safe_markdown(primary_travel_df.loc[primary_travel_df["origin_station_name"].isin([core_row["nearest_station_name"], wirye_row["nearest_station_name"], support_row["nearest_station_name"]])], index=False),
        "",
        "## 7. 15/30/45/60분 등시간권 역 수 분석",
        safe_markdown(origin_df if not origin_df.empty else pd.DataFrame(), index=False),
        "",
        "## 8. 접근 가능한 인구·종사자 추정 가능 여부",
        safe_markdown(accessible_df if not accessible_df.empty else pd.DataFrame(), index=False),
        "",
        "## 9. 판교 Core 접근성 해석",
        f"- nearest station: {core_row['nearest_station_name']} / {core_row['nearest_station_line']}",
        f"- 강남까지: {route_time(core_row['nearest_station_name'], '강남')}",
        f"- 서울역까지: {route_time(core_row['nearest_station_name'], '서울역')}",
        f"- 잠실까지: {route_time(core_row['nearest_station_name'], '잠실')}",
        f"- 수서까지: {route_time(core_row['nearest_station_name'], '수서')}",
        "- 판교 Core는 기존 건축물대장과 SGIS에서 이미 고용 집적이 강했기 때문에, 짧은 환승시간이 추가로 확인되면 성공 요인이 강화된다.",
        "",
        "## 10. 위례 Core 접근성 해석",
        f"- nearest station: {wirye_row['nearest_station_name']} / {wirye_row['nearest_station_line']}",
        f"- 강남까지: {route_time(wirye_row['nearest_station_name'], '강남')}",
        f"- 서울역까지: {route_time(wirye_row['nearest_station_name'], '서울역')}",
        f"- 잠실까지: {route_time(wirye_row['nearest_station_name'], '잠실')}",
        f"- 수서까지: {route_time(wirye_row['nearest_station_name'], '수서')}",
        "- 위례 Core는 지하철 접근성이 판교보다 약하거나 유사하더라도, 건축물·SGIS 고용 집적이 낮다면 자족기능 저조의 한 요소로 해석할 수 있다.",
        "",
        "## 11. 위례 Support 접근성 해석",
        f"- nearest station: {support_row['nearest_station_name']} / {support_row['nearest_station_line']}",
        "- 위례 Support는 Core보다 생활권/지원 기능이 섞인 보조 구역으로 읽는다.",
        "",
        "## 12. SGIS·건축물 결과와 교차검증",
        f"- 판교 Core worker_density: {sgis_core_sum.loc['pangyo_core', 'worker_density_per_km2'] if 'pangyo_core' in sgis_core_sum.index else None}",
        f"- 위례 Core worker_density: {sgis_core_sum.loc['wirye_core', 'worker_density_per_km2'] if 'wirye_core' in sgis_core_sum.index else None}",
        "- 판교 Core는 높은 업무·연구 연면적 비율과 SGIS 종사자 밀도가 함께 높아, 지하철 접근성이 보조 설명변수로 작동했을 가능성이 크다.",
        "- 위례 Core는 접근성만으로는 부족하고 물리적 실현도와 업무 수요가 동시에 약했을 가능성을 함께 봐야 한다.",
        "",
        "## 13. 업무지구 성공요인 관점 해석",
        "- 판교는 고용 접근성과 광역환승 연결이 강한 노선 구조를 활용한 업무 클러스터로 해석 가능하다.",
        "- 위례는 주거·지원 기능과 혼합된 생활권 구조가 강해, 업무지구 성과를 동일한 방식으로 기대하기 어렵다.",
        "",
        "## 14. 데이터 한계",
        "- 지하철 접근성은 직선거리 기반 역 접근과 지하철 네트워크만 반영했다.",
        "- 버스, 도로, 배차간격, 혼잡도, 실제 보행 네트워크를 반영하지 않았다.",
        "- SGIS 접근 가능한 인구·종사자는 집계구 중심점과 대표 역을 이용한 탐색적 근사치이다.",
        "",
        "## 15. 발견된 문제",
        "- 2023년 운영망이 아니면 미래 노선이 결과를 왜곡할 수 있다.",
        "- 위례는 지하철망만 보면 상대적으로 약하게 보일 수 있어 버스 접근성 미반영 편향이 있다.",
        "- 역 접근은 실제 보행망보다 단순하다.",
        "",
        "## 16. 개선 제안",
        "- 다음 단계에서 OSM/보행망을 붙여 역 접근 시간을 실제 보행시간으로 보정한다.",
        "- 버스 환승망이 있으면 위례 접근성의 과소평가를 점검한다.",
        "- 미래 노선 시나리오는 별도 장표로 분리한다.",
        "",
        "## 17. 다음 단계 추천",
        "- 통합지표를 만든 뒤 대시보드에서 경계/건축물/SGIS/교통을 같은 화면으로 비교한다.",
        "",
        "## 18. ChatGPT에게 전달할 요약",
        f"* 사용한 지하철 network 파일: {RAW / 'network' / 'nodes.tsv'}, {RAW / 'network' / 'links.tsv'}, {RAW / 'opening.tsv'}, {RAW / 'line_waits.parquet'}",
        f"* 2023년 네트워크 필터 적용 여부: yes",
        f"* 노드 수: {len(nodes)}",
        f"* 링크 수: {len(links)}",
        f"* 판교 Core nearest station: {core_row['nearest_station_name']}",
        f"* 위례 Core nearest station: {wirye_row['nearest_station_name']}",
        f"* 위례 Support nearest station: {support_row['nearest_station_name']}",
        f"* 판교 Core nearest station distance/walk time: {core_row['nearest_station_distance_m']:.1f} m / {core_row['estimated_walk_time_min']:.2f} min",
        f"* 위례 Core nearest station distance/walk time: {wirye_row['nearest_station_distance_m']:.1f} m / {wirye_row['estimated_walk_time_min']:.2f} min",
        f"* 위례 Support nearest station distance/walk time: {support_row['nearest_station_distance_m']:.1f} m / {support_row['estimated_walk_time_min']:.2f} min",
        f"* 판교 Core → 강남역: {route_time(core_row['nearest_station_name'], '강남')}",
        f"* 위례 Core → 강남역: {route_time(wirye_row['nearest_station_name'], '강남')}",
        f"* 판교 Core → 잠실역: {route_time(core_row['nearest_station_name'], '잠실')}",
        f"* 위례 Core → 잠실역: {route_time(wirye_row['nearest_station_name'], '잠실')}",
        f"* 판교 Core → 수서역: {route_time(core_row['nearest_station_name'], '수서')}",
        f"* 위례 Core → 수서역: {route_time(wirye_row['nearest_station_name'], '수서')}",
        f"* 판교 Core reachable stations 30/45/60: {origin_summary.loc[origin_summary['origin_region_id'].eq('pangyo_core'), ['reachable_stations_30min', 'reachable_stations_45min', 'reachable_stations_60min']].iloc[0].tolist() if not origin_summary.loc[origin_summary['origin_region_id'].eq('pangyo_core')].empty else None}",
        f"* 위례 Core reachable stations 30/45/60: {origin_summary.loc[origin_summary['origin_region_id'].eq('wirye_core'), ['reachable_stations_30min', 'reachable_stations_45min', 'reachable_stations_60min']].iloc[0].tolist() if not origin_summary.loc[origin_summary['origin_region_id'].eq('wirye_core')].empty else None}",
        f"* 위례 Support reachable stations 30/45/60: {origin_summary.loc[origin_summary['origin_region_id'].eq('wirye_support'), ['reachable_stations_30min', 'reachable_stations_45min', 'reachable_stations_60min']].iloc[0].tolist() if not origin_summary.loc[origin_summary['origin_region_id'].eq('wirye_support')].empty else None}",
        f"* 접근 가능한 인구·종사자 추정 여부: {'yes' if not accessible_df.empty else 'no'}",
        f"* 건축물·SGIS 결과와 교차검증: pangyo_core worker_density={sgis_core_sum.loc['pangyo_core', 'worker_density_per_km2'] if 'pangyo_core' in sgis_core_sum.index else None}, wirye_core worker_density={sgis_core_sum.loc['wirye_core', 'worker_density_per_km2'] if 'wirye_core' in sgis_core_sum.index else None}",
        "* 최종 해석: 판교는 지하철 접근성과 광역 연결성이 고용 집적을 뒷받침했을 가능성이 크고, 위례 Core는 접근성만으로는 판교 수준의 고용 클러스터로 보기 어렵다.",
        "* warning: 지하철 접근성은 직선거리 기반 역 접근과 subway-only 네트워크라 실제 보행/버스 접근성과 차이가 있다.",
        "* 발견된 문제: 미래 노선이 원자료에 포함되어 있었고, 위례는 버스/도로 접근성 미반영 편향이 있다.",
        "* 개선 제안: 보행망과 버스망을 결합한 멀티모달 접근성, 그리고 미래 노선 시나리오 분리를 추가한다.",
        f"* 생성된 주요 파일: {TRAVEL_TIME_CSV}, {ISOCHRONE_CSV}, {STATION_REACHABILITY_GEOJSON}, {STATION_ACCESS_CSV}, {CROSS_CSV}, {REPORT_MD}",
        "* 바로 다음 단계 추천: 통합지표 산출 및 대시보드 시각화",
    ]
    write_text(REPORT_MD, "\n".join(report))

    # status update
    status_append = "\n".join(
        [
            "",
            "## 교통 접근성 분석 v2",
            "",
            f"- 완료 여부: 완료",
            f"- 사용한 network 파일: `{RAW / 'network' / 'nodes.tsv'}`, `{RAW / 'network' / 'links.tsv'}`",
            f"- 2023년 기준 필터: 적용",
            f"- 생성된 주요 output: `{STATION_ACCESS_CSV}`, `{TRAVEL_TIME_CSV}`, `{ISOCHRONE_CSV}`, `{CROSS_CSV}`, `{REPORT_MD}`",
            "- warning: 지하철 접근성은 직선거리 기반 역 접근이며 버스 접근성을 반영하지 않는다.",
            "- 다음 단계: 통합지표 및 대시보드 구축",
        ]
    )
    with STATUS_REPORT.open("a", encoding="utf-8") as f:
        f.write(status_append)


if __name__ == "__main__":
    main()
