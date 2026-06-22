from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Point
from shapely.ops import unary_union


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
PROCESSED = DATA / "processed"
V29_DIR = PROCESSED / "v29"
INVENTORY = DATA / "inventory"
FRONTEND_DATA = ROOT / "frontend" / "public" / "data"
OUT_MAPS = ROOT / "outputs" / "maps"

SUBWAY_NODES_PATH = next(ROOT.rglob("subway_nodes_2023_v2.geojson"))
SUBWAY_GRAPHML_PATH = next(ROOT.rglob("subway_network_2023_v2.graphml"))
SGIS_BLOCKS_PATH = ROOT / "data" / "processed" / "05_SGIS" / "90_최종" / "sgis_agg_boundary_selected_v2.gpkg"
SGIS_STATS_PATH = ROOT / "data" / "processed" / "05_SGIS" / "90_최종" / "sgis_stats_integrated_v2.csv"
BUS_STOPS_PATH = ROOT / "data" / "processed" / "gbis_bus_stops_near_regions_v3.geojson"
BUS_ROUTES_PATH = ROOT / "data" / "processed" / "gbis_bus_station_routes_v3.csv"
BUS_ROUTE_STATIONS_PATH = ROOT / "data" / "processed" / "gbis_bus_route_stations_v3.geojson"

TARGETS = [
    {"origin_region_id": "pangyo_core", "station_name": "판교", "station_label": "판교역"},
    {"origin_region_id": "wirye_core", "station_name": "복정", "station_label": "복정역"},
]
THRESHOLDS = list(range(0, 61, 5))

PREVIEW_PATH = ROOT / "scripts" / "generate_multimodal_accessibility_preview_v5.py"
SPEC = importlib.util.spec_from_file_location("multimodal_preview_v5", PREVIEW_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Could not load helper module: {PREVIEW_PATH}")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def ensure_dirs() -> None:
    for path in [V29_DIR, INVENTORY, FRONTEND_DATA, OUT_MAPS]:
        path.mkdir(parents=True, exist_ok=True)


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_geojson(path: Path, frame: gpd.GeoDataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = frame.copy()
    if out.crs is None:
        out = out.set_crs(4326)
    else:
        out = out.to_crs(4326)
    path.write_text(out.to_json(drop_id=False, ensure_ascii=False), encoding="utf-8")


def write_md(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def load_blocks() -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    blocks = gpd.read_file(SGIS_BLOCKS_PATH).to_crs(mod.METER_CRS)
    stats = pd.read_csv(SGIS_STATS_PATH, low_memory=False)
    stats["agg_code"] = stats["agg_code"].astype(str)
    blocks["agg_code"] = blocks["agg_code"].astype(str)
    merged = blocks.merge(stats, on="agg_code", how="left")
    return merged, stats


def station_origin_points(nodes: gpd.GeoDataFrame, station_name: str) -> tuple[list[str], Point]:
    subset = nodes[nodes["station_name"].astype(str).eq(station_name)].copy()
    if subset.empty:
        subset = nodes[nodes["station_name"].astype(str).str.contains(station_name, regex=False, na=False)].copy()
    if subset.empty:
        raise ValueError(f"No subway nodes found for station: {station_name}")
    coords = [(float(geom.x), float(geom.y)) for geom in subset.geometry if geom is not None]
    origin_point = Point(sum(x for x, _ in coords) / len(coords), sum(y for _, y in coords) / len(coords))
    return subset["node_id"].astype(str).tolist(), origin_point


def polygon_totals(poly: gpd.GeoSeries, blocks: gpd.GeoDataFrame) -> dict[str, float]:
    if poly.empty or blocks.empty:
        return {"population": 0.0, "households": 0.0, "workers": 0.0, "businesses": 0.0, "area_m2": 0.0}
    region_geom = poly.to_crs(mod.METER_CRS).iloc[0]
    totals = {
        "population": 0.0,
        "households": 0.0,
        "workers": 0.0,
        "businesses": 0.0,
        "area_m2": float(region_geom.area),
    }
    for row in blocks.itertuples(index=False):
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        inter = geom.intersection(region_geom)
        if inter.is_empty:
            continue
        ratio = float(inter.area / geom.area) if geom.area else 0.0
        totals["population"] += float(getattr(row, "population_total", 0) or 0) * ratio
        totals["households"] += float(getattr(row, "household_total", 0) or 0) * ratio
        totals["workers"] += float(getattr(row, "worker_total", 0) or 0) * ratio
        totals["businesses"] += float(getattr(row, "business_total", 0) or 0) * ratio
    return totals


def make_buffer_polygon(nodes: gpd.GeoDataFrame, links: gpd.GeoDataFrame, buffer_m: float = 800.0) -> gpd.GeoSeries:
    if nodes.empty and links.empty:
        return gpd.GeoSeries([], crs=4326)
    parts: list[Any] = []
    if not nodes.empty:
        parts.extend(list(nodes.to_crs(mod.METER_CRS).geometry.buffer(buffer_m)))
    if not links.empty:
        parts.extend(list(links.to_crs(mod.METER_CRS).geometry.buffer(buffer_m * 0.25)))
    merged = unary_union(parts)
    if merged.is_empty:
        return gpd.GeoSeries([], crs=4326)
    return gpd.GeoSeries([merged], crs=mod.METER_CRS).to_crs(4326)


def bus_origin_stops(bus_stops: gpd.GeoDataFrame, origin_point: Point, radius_m: float = 500.0) -> gpd.GeoDataFrame:
    if bus_stops.empty:
        return bus_stops
    stops_m = bus_stops.to_crs(mod.METER_CRS).copy()
    origin_m = gpd.GeoSeries([origin_point], crs=4326).to_crs(mod.METER_CRS).iloc[0]
    distances = stops_m.geometry.distance(origin_m)
    out = stops_m.loc[distances <= radius_m].copy()
    return out.to_crs(4326)


def run_subway_station_accessibility(
    origin_region_id: str,
    station_name: str,
    station_label: str,
    station_node_ids: list[str],
    origin_point: Point,
    subway_graph,
    subway_nodes: gpd.GeoDataFrame,
    blocks: gpd.GeoDataFrame,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    polygon_rows: list[dict[str, Any]] = []

    H = subway_graph.copy()
    source = f"__origin__::{origin_region_id}::subway"
    H.add_node(source)
    for node_id in station_node_ids:
        if H.has_node(node_id):
            H.add_edge(source, node_id, weight=0.0, edge_kind="origin")

    lengths = pd.Series(mod.nx.single_source_dijkstra_path_length(H, source, weight="weight"), dtype="float64")
    if source in lengths.index:
        lengths = lengths.drop(source)

    for threshold in THRESHOLDS:
        reachable = [node for node, tt in lengths.items() if float(tt) <= threshold]
        node_features: list[dict[str, Any]] = []
        link_features: list[dict[str, Any]] = []

        for node_id in reachable:
            row = subway_nodes.loc[subway_nodes["node_id"].astype(str).eq(str(node_id))]
            if row.empty:
                continue
            geom = row.iloc[0].geometry
            node_features.append(
                {
                    "origin_region_id": origin_region_id,
                    "origin_station_name": station_name,
                    "station_label": station_label,
                    "mode": "subway",
                    "threshold_min": threshold,
                    "station_id": str(row.iloc[0]["station_id"]),
                    "station_name": row.iloc[0]["station_name"],
                    "travel_time_min": float(lengths[str(node_id)]),
                    "geometry": geom,
                }
            )

        for u, v, data in H.edges(data=True):
            if u == source or v == source:
                continue
            if u in lengths.index and v in lengths.index and float(lengths[u]) <= threshold and float(lengths[v]) <= threshold:
                if subway_graph.has_edge(u, v):
                    nu = subway_graph.nodes[u]
                    nv = subway_graph.nodes[v]
                    link_features.append(
                        {
                            "origin_region_id": origin_region_id,
                            "origin_station_name": station_name,
                            "station_label": station_label,
                            "mode": "subway",
                            "threshold_min": threshold,
                            "station_id_from": u,
                            "station_name_from": nu.get("station_name"),
                            "station_id_to": v,
                            "station_name_to": nv.get("station_name"),
                            "travel_time_min": float(lengths[v]),
                            "geometry": LineString([(float(nu["lon"]), float(nu["lat"])), (float(nv["lon"]), float(nv["lat"]))]),
                        }
                    )

        node_gdf = gpd.GeoDataFrame(node_features, geometry="geometry", crs=4326) if node_features else gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=4326)
        link_gdf = gpd.GeoDataFrame(link_features, geometry="geometry", crs=4326) if link_features else gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=4326)
        poly = make_buffer_polygon(node_gdf, link_gdf)
        totals = polygon_totals(poly, blocks)
        summary_rows.append(
            {
                "origin_region_id": origin_region_id,
                "origin_station_name": station_name,
                "station_label": station_label,
                "mode": "subway",
                "threshold_min": threshold,
                "reachable_station_count": len(node_features),
                "reachable_link_count": len(link_features),
                "accessible_population": totals["population"],
                "accessible_workers": totals["workers"],
                "accessible_businesses": totals["businesses"],
                "accessible_households": totals["households"],
                "accessible_area_km2": totals["area_m2"] / 1_000_000.0 if totals["area_m2"] else 0.0,
                "geometry": poly.iloc[0] if not poly.empty else None,
            }
        )
        if not poly.empty:
            polygon_rows.append(
                {
                    "origin_region_id": origin_region_id,
                    "origin_station_name": station_name,
                    "station_label": station_label,
                    "mode": "subway",
                    "threshold_min": threshold,
                    "reachable_station_count": len(node_features),
                    "reachable_link_count": len(link_features),
                    "geometry": poly.iloc[0],
                }
            )
    return polygon_rows, rows, pd.DataFrame(summary_rows)


def run_bus_station_accessibility(
    origin_region_id: str,
    station_name: str,
    station_label: str,
    origin_point: Point,
    bus_graph,
    bus_stops: gpd.GeoDataFrame,
    bus_edges: pd.DataFrame,
    blocks: gpd.GeoDataFrame,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    polygon_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []

    nearby_stops = bus_origin_stops(bus_stops, origin_point, radius_m=500.0)
    if nearby_stops.empty:
        stop_distances = bus_stops.to_crs(mod.METER_CRS).geometry.distance(gpd.GeoSeries([origin_point], crs=4326).to_crs(mod.METER_CRS).iloc[0])
        nearest_idx = stop_distances.idxmin()
        nearby_stops = bus_stops.loc[[nearest_idx]].copy()

    start_nodes: list[dict[str, Any]] = []
    for stop in nearby_stops.itertuples(index=False):
        stop_geom = stop.geometry
        access_time = mod.haversine_m(origin_point.x, origin_point.y, float(stop_geom.x), float(stop_geom.y)) / mod.WALK_SPEED_M_PER_MIN
        start_nodes.append(
            {
                "station_id": str(stop.station_id),
                "station_name": str(stop.station_name),
                "access_time_min": access_time,
                "geometry": stop_geom,
            }
        )

    for s in start_nodes:
        if not bus_graph.has_node(s["station_id"]):
            bus_graph.add_node(
                s["station_id"],
                station_id=s["station_id"],
                station_name=s["station_name"],
                lon=float(s["geometry"].x),
                lat=float(s["geometry"].y),
                source="origin_proxy",
                region_id=origin_region_id,
            )

    H = bus_graph.copy()
    source = f"__origin__::{origin_region_id}::bus"
    H.add_node(source)
    for s in start_nodes:
        H.add_edge(source, s["station_id"], weight=float(s["access_time_min"]), edge_kind="access")

    lengths = pd.Series(mod.nx.single_source_dijkstra_path_length(H, source, weight="weight"), dtype="float64")
    if source in lengths.index:
        lengths = lengths.drop(source)

    for threshold in THRESHOLDS:
        reachable = [node for node, tt in lengths.items() if float(tt) <= threshold]
        node_features: list[dict[str, Any]] = []
        link_features: list[dict[str, Any]] = []

        for node_id in reachable:
            data = H.nodes[str(node_id)]
            if data.get("lon") is None or data.get("lat") is None:
                continue
            node_features.append(
                {
                    "origin_region_id": origin_region_id,
                    "origin_station_name": station_name,
                    "station_label": station_label,
                    "mode": "bus",
                    "threshold_min": threshold,
                    "station_id": str(node_id),
                    "station_name": data.get("station_name"),
                    "travel_time_min": float(lengths[str(node_id)]),
                    "geometry": Point(float(data["lon"]), float(data["lat"])),
                }
            )

        for _, edge in bus_edges.iterrows():
            u = str(edge["from_station_id"])
            v = str(edge["to_station_id"])
            if u in lengths.index and v in lengths.index and float(lengths[u]) <= threshold and float(lengths[v]) <= threshold:
                link_features.append(
                    {
                        "origin_region_id": origin_region_id,
                        "origin_station_name": station_name,
                        "station_label": station_label,
                        "mode": "bus",
                        "threshold_min": threshold,
                        "from_station_id": u,
                        "from_station_name": edge["from_station_name"],
                        "to_station_id": v,
                        "to_station_name": edge["to_station_name"],
                        "travel_time_min": float(lengths[v]),
                        "geometry": edge["geometry"],
                    }
                )

        node_gdf = gpd.GeoDataFrame(node_features, geometry="geometry", crs=4326) if node_features else gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=4326)
        link_gdf = gpd.GeoDataFrame(link_features, geometry="geometry", crs=4326) if link_features else gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=4326)
        poly = make_buffer_polygon(node_gdf, link_gdf)
        totals = polygon_totals(poly, blocks)
        summary_rows.append(
            {
                "origin_region_id": origin_region_id,
                "origin_station_name": station_name,
                "station_label": station_label,
                "mode": "bus",
                "threshold_min": threshold,
                "reachable_station_count": len(node_features),
                "reachable_link_count": len(link_features),
                "accessible_population": totals["population"],
                "accessible_workers": totals["workers"],
                "accessible_businesses": totals["businesses"],
                "accessible_households": totals["households"],
                "accessible_area_km2": totals["area_m2"] / 1_000_000.0 if totals["area_m2"] else 0.0,
                "geometry": poly.iloc[0] if not poly.empty else None,
            }
        )
        if not poly.empty:
            polygon_rows.append(
                {
                    "origin_region_id": origin_region_id,
                    "origin_station_name": station_name,
                    "station_label": station_label,
                    "mode": "bus",
                    "threshold_min": threshold,
                    "reachable_station_count": len(node_features),
                    "reachable_link_count": len(link_features),
                    "geometry": poly.iloc[0],
                }
            )
    return polygon_rows, rows, pd.DataFrame(summary_rows)


def build_curve_json(curve_df: pd.DataFrame) -> dict[str, Any]:
    rows = []
    for _, row in curve_df.sort_values(["origin_region_id", "mode", "threshold_min"]).iterrows():
        rows.append(
            {
                "origin_region_id": row["origin_region_id"],
                "origin_station_name": row["origin_station_name"],
                "station_label": row["station_label"],
                "mode": row["mode"],
                "minute": int(row["threshold_min"]),
                "accessible_population": float(row["accessible_population"]),
                "accessible_workers": float(row["accessible_workers"]),
                "accessible_businesses": float(row["accessible_businesses"]),
                "reachable_station_count": int(row["reachable_station_count"]),
                "reachable_link_count": int(row["reachable_link_count"]),
                "accessible_area_km2": float(row["accessible_area_km2"]),
            }
        )
    return {
        "version": "v29",
        "source": "station-based subway and bus network reachability from existing multimodal preview helpers",
        "minute_step": 5,
        "rows": rows,
    }


def main() -> None:
    ensure_dirs()
    blocks, _ = load_blocks()

    subway_nodes_raw, subway_links_raw, _ = mod.load_subway_files([])
    subway_graph, subway_nodes_gdf, _ = mod.build_subway_graph(subway_nodes_raw, subway_links_raw, [])

    bus_stops = mod.load_gbis_stops()
    bus_routes = mod.load_gbis_routes()
    bus_route_stations = mod.load_gbis_route_stations()
    bus_graph, _, bus_edges, _, _, _ = mod.build_bus_graph(pd.DataFrame(), bus_stops, bus_routes, bus_route_stations, "", [])

    poly_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    curve_rows: list[pd.DataFrame] = []

    for target in TARGETS:
        station_node_ids, origin_point = station_origin_points(subway_nodes_gdf, target["station_name"])

        subway_polys, _, subway_summary = run_subway_station_accessibility(
            target["origin_region_id"],
            target["station_name"],
            target["station_label"],
            station_node_ids,
            origin_point,
            subway_graph,
            subway_nodes_gdf,
            blocks,
        )
        bus_polys, _, bus_summary = run_bus_station_accessibility(
            target["origin_region_id"],
            target["station_name"],
            target["station_label"],
            origin_point,
            bus_graph,
            bus_stops,
            bus_edges,
            blocks,
        )

        poly_rows.extend(subway_polys)
        poly_rows.extend(bus_polys)
        summary_rows.append(subway_summary)
        summary_rows.append(bus_summary)
        curve_rows.append(subway_summary)
        curve_rows.append(bus_summary)

    summary_df = pd.concat(summary_rows, ignore_index=True)
    curve_df = summary_df.copy()
    curve_df["threshold_min"] = curve_df["threshold_min"].astype(int)
    curve_df = curve_df.sort_values(["origin_region_id", "mode", "threshold_min"]).reset_index(drop=True)
    table_df = curve_df.drop(columns=["geometry"], errors="ignore").copy()

    poly_gdf = gpd.GeoDataFrame(poly_rows, geometry="geometry", crs=4326) if poly_rows else gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=4326)
    curve_json = build_curve_json(curve_df)

    write_csv(V29_DIR / "pangyo_bokjeong_mode_accessibility_curve_v29.csv", table_df)
    write_csv(V29_DIR / "pangyo_bokjeong_mode_accessibility_summary_v29.csv", table_df)
    write_geojson(FRONTEND_DATA / "pangyo_bokjeong_mode_isochrones_v29.geojson", poly_gdf)
    write_json(FRONTEND_DATA / "pangyo_bokjeong_mode_accessibility_curve_v29.json", curve_json)
    write_json(FRONTEND_DATA / "pangyo_bokjeong_mode_accessibility_summary_v29.json", {"rows": table_df.to_dict(orient="records")})

    methodology = [
        "# 판교역·복정역 등시간권 접근성 분석 v29",
        "",
        "## 1. 목적",
        "- 판교역과 복정역을 기준으로 지하철과 버스의 0~60분 도달권을 비교한다.",
        "- 등시간권 안의 SGIS 배분 인구·종사자·사업체를 area-weighted 방식으로 합산한다.",
        "",
        "## 2. 데이터",
        f"- 지하철 네트워크: `{SUBWAY_GRAPHML_PATH.relative_to(ROOT)}`",
        f"- 지하철 노드: `{SUBWAY_NODES_PATH.relative_to(ROOT)}`",
        f"- 버스 정류장: `{BUS_STOPS_PATH.relative_to(ROOT)}`",
        f"- 버스 노선 정류장: `{BUS_ROUTE_STATIONS_PATH.relative_to(ROOT)}`",
        f"- SGIS 블록: `{SGIS_BLOCKS_PATH.relative_to(ROOT)}`",
        f"- SGIS 통계: `{SGIS_STATS_PATH.relative_to(ROOT)}`",
        "",
        "## 3. 방법",
        "- 지하철은 선택 역의 동일 명칭 노드를 super-source와 0분으로 연결해 Dijkstra shortest path를 계산했다.",
        "- 버스는 선택 역 좌표 기준 500m 내 GBIS 정류장을 출발점으로 두고, route-station graph에서 Dijkstra shortest path를 계산했다.",
        "- 각 threshold별 reachable nodes와 links를 buffer union polygon으로 변환한 뒤 SGIS 블록과 intersect하여 인구·종사자·사업체를 area-weighted 집계했다.",
        "- 곡선은 0, 5, 10, ..., 60분에 대한 실제 네트워크 도달권 집계값이다.",
        "",
        "## 4. 한계",
        "- 버스 도달권은 실제 배차와 환승대기까지 완전 반영한 GPS 궤적이 아니라, 정류장-노선 그래프 기반의 근사치다.",
        "- 등시간권 경계는 서비스 영역을 시각화하기 위한 buffer proxy이며, 행정경계와 완전히 일치하지 않는다.",
        "- SGIS 집계는 블록 단위 area-weighted 배분값이므로 세부 필지 수준의 실제 인구·종사자와 차이가 있을 수 있다.",
    ]
    write_md(INVENTORY / "pangyo_bokjeong_mode_accessibility_methodology_v29.md", "\n".join(methodology))
    write_md(
        V29_DIR / "pangyo_bokjeong_mode_accessibility_report_sentences_v29.md",
        "\n".join(
            [
                "본 연구는 판교역과 복정역을 기준으로 지하철과 버스의 0~60분 등시간권을 각각 산출하고, 각 시간권 내부의 SGIS 배분 인구·종사자·사업체를 동일 기준으로 비교하였다.",
                "판교역과 복정역은 모두 핵심역으로서 기능하지만, 지하철과 버스의 도달권 확장 속도와 내부 자원 흡수 구조는 서로 다르게 나타난다.",
                "본 분석의 등시간권 경계는 네트워크 shortest path를 기반으로 한 buffer proxy이며, 대시보드에서는 mode별 경계와 누적 곡선을 함께 해석해야 한다.",
            ]
        ),
    )

    review_html = [
        "<html><head><meta charset='utf-8'><title>v29 accessibility review</title>",
        "<style>body{font-family:Arial,sans-serif;padding:20px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;padding:8px;text-align:right}th{text-align:center;background:#f3f4f6}td:first-child,th:first-child,td:nth-child(2),th:nth-child(2),td:nth-child(3),th:nth-child(3){text-align:left}</style>",
        "</head><body>",
        "<h1>판교역·복정역 등시간권 접근성 검토 v29</h1>",
        "<table><thead><tr><th>station</th><th>mode</th><th>minute</th><th>population</th><th>workers</th><th>businesses</th><th>area_km2</th></tr></thead><tbody>",
    ]
    for row in curve_df.itertuples(index=False):
        review_html.append(
            f"<tr><td>{row.origin_station_name}</td><td>{row.mode}</td><td>{int(row.threshold_min)}</td><td>{float(row.accessible_population):.1f}</td><td>{float(row.accessible_workers):.1f}</td><td>{float(row.accessible_businesses):.1f}</td><td>{float(row.accessible_area_km2):.3f}</td></tr>"
        )
    review_html.extend(["</tbody></table>", "</body></html>"])
    (OUT_MAPS / "pangyo_bokjeong_mode_accessibility_review_v29.html").write_text("\n".join(review_html), encoding="utf-8")

    print(json.dumps({
        "curve_rows": len(table_df),
        "polygon_rows": len(poly_gdf),
        "stations": sorted(table_df["origin_station_name"].unique().tolist()),
        "modes": sorted(table_df["mode"].unique().tolist()),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
