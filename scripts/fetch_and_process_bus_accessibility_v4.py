from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import requests
from dotenv import load_dotenv
from shapely.geometry import Point


ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw" / "09_bus_network"
DATA_PROCESSED = ROOT / "data" / "processed"
DATA_INVENTORY = ROOT / "data" / "inventory"
FRONTEND_DATA = ROOT / "frontend" / "public" / "data"

SERVICE_KEY_ENV = "GBIS_SERVICE_KEY"
BOUNDARY_CANDIDATES = [
    DATA_PROCESSED / "boundaries_core_comparison_v2.gpkg",
    DATA_PROCESSED / "boundaries_core_comparison_v2.geojson",
    FRONTEND_DATA / "boundaries_core_comparison_v2.geojson",
    DATA_PROCESSED / "boundaries_analysis_v2.gpkg",
    DATA_PROCESSED / "boundaries_analysis_v2.geojson",
]
SEOUl_STOP_DIR = DATA_RAW / "seoul_bus_stops"
SEOUl_STOP_FALLBACK = DATA_RAW / "2023년각월1일기준_서울시버스정류소위치정보.csv"

GBIS_AROUND_URL = "https://apis.data.go.kr/6410000/busstationservice/v2/getBusStationAroundListv2"
GBIS_VIA_ROUTE_URL = "https://apis.data.go.kr/6410000/busstationservice/v2/getBusStationViaRouteListv2"
GBIS_ROUTE_STATION_URL = "https://apis.data.go.kr/6410000/busrouteservice/v2/getBusRouteStationListv2"

REGION_TARGETS = ["pangyo_core", "wirye_core"]
RADIUS_M = 500.0
NOW = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

EXPRESS_ROUTE_TYPES = {"11", "14", "16", "21", "41", "42", "43", "51", "52", "53"}
LOCAL_ROUTE_TYPES = {"13", "23", "30"}
SEAT_ROUTE_TYPES = {"12", "22"}
ROUTE_TYPE_LABELS = {
    "11": "직행좌석형시내버스",
    "12": "좌석형시내버스",
    "13": "일반형시내버스",
    "14": "광역급행형시내버스",
    "15": "따복형시내버스",
    "16": "경기순환버스",
    "21": "직행좌석형농어촌버스",
    "22": "좌석형농어촌버스",
    "23": "일반형농어촌버스",
    "30": "마을버스",
    "41": "고속형시외버스",
    "42": "좌석형시외버스",
    "43": "일반형시외버스",
    "51": "리무진공항버스",
    "52": "좌석형공항버스",
    "53": "일반형공항버스",
}


def ensure_dirs() -> None:
    for p in [DATA_PROCESSED, DATA_INVENTORY, FRONTEND_DATA]:
        p.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def write_csv(path: Path, df: pd.DataFrame) -> None:
    df.to_csv(path, index=False, encoding="utf-8-sig")


def write_geojson(path: Path, gdf: gpd.GeoDataFrame) -> None:
    path.write_text(gdf.to_json(drop_id=False), encoding="utf-8")


def normalize_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip().replace(" ", "")


def safe_float(value: Any) -> float | None:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return None
        return float(value)
    except Exception:
        return None


def rounded_coord(value: Any, digits: int = 5) -> str:
    v = safe_float(value)
    return f"{v:.{digits}f}" if v is not None else ""


def pick_first(row: pd.Series, candidates: list[str]) -> Any:
    for name in candidates:
        if name in row.index and pd.notna(row[name]) and str(row[name]).strip() != "":
            return row[name]
    return None


def station_identity(row: pd.Series) -> str:
    station_id = normalize_text(row.get("station_id"))
    ars_id = normalize_text(row.get("ars_id"))
    mobile_no = normalize_text(row.get("mobile_no"))
    name = normalize_text(row.get("station_name"))
    lon = rounded_coord(row.get("lon"))
    lat = rounded_coord(row.get("lat"))
    if station_id:
        return f"id:{station_id}"
    if ars_id:
        return f"ars:{ars_id}"
    if mobile_no:
        return f"mobile:{mobile_no}"
    return f"name:{name}|{lon}|{lat}"


def integrated_identity(row: pd.Series) -> str:
    return station_identity(row)


def masked_url(url: str, params: dict[str, Any]) -> str:
    parts = []
    for key, value in params.items():
        if key == SERVICE_KEY_ENV or key.lower() == "servicekey" or "key" in key.lower():
            parts.append(f"{key}=***")
        else:
            parts.append(f"{key}={value}")
    return f"{url}?{'&'.join(parts)}"


def load_api_rows(payload: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta: dict[str, Any] = {"resultCode": None, "resultMsg": None}
    if not isinstance(payload, dict):
        return [], meta
    response = payload.get("response", payload)
    if not isinstance(response, dict):
        return [], meta
    for header_key in ["header", "msgHeader", "comMsgHeader"]:
        header = response.get(header_key)
        if isinstance(header, dict):
            if header.get("resultCode") is not None:
                meta["resultCode"] = str(header.get("resultCode")).strip()
            if header.get("resultMsg") is not None:
                meta["resultMsg"] = header.get("resultMsg")
            if header.get("resultMessage") is not None:
                meta["resultMsg"] = header.get("resultMessage")
    body = response.get("body") or response.get("msgBody") or {}
    if not isinstance(body, dict):
        return [], meta
    for key in ["busStationList", "busStationAroundList", "busRouteList", "busRouteStationList"]:
        value = body.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)], meta
        if isinstance(value, dict):
            item = value.get("item")
            if isinstance(item, list):
                return [x for x in item if isinstance(x, dict)], meta
            if isinstance(item, dict):
                return [item], meta
            return [value], meta
    item = body.get("item")
    if isinstance(item, list):
        return [x for x in item if isinstance(x, dict)], meta
    if isinstance(item, dict):
        return [item], meta
    return [], meta


def api_get(
    url: str,
    params: dict[str, Any],
    label: str,
    inventory: list[str],
    errors: list[dict[str, Any]],
    timeout: int = 15,
    retries: int = 3,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    request_label = masked_url(url, params)
    last_meta: dict[str, Any] = {"http_status": None, "content_type": None, "resultCode": None, "resultMsg": None}
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, params=params, timeout=timeout)
            last_meta["http_status"] = response.status_code
            last_meta["content_type"] = response.headers.get("content-type", "")
            preview = (response.text or "")[:300]
            preview = preview.replace(os.getenv("GBIS_SERVICE_KEY", ""), "***")

            if response.status_code != 200:
                errors.append(
                    {
                        "label": label,
                        "attempt": attempt,
                        "status": "http_error",
                        "http_status": response.status_code,
                        "content_type": last_meta["content_type"],
                        "request": request_label,
                        "message": preview,
                    }
                )
                if attempt < retries:
                    time.sleep(1.0)
                    continue
                return [], last_meta

            try:
                payload = response.json()
            except Exception as exc:
                errors.append(
                    {
                        "label": label,
                        "attempt": attempt,
                        "status": "json_parse_error",
                        "http_status": response.status_code,
                        "content_type": last_meta["content_type"],
                        "request": request_label,
                        "message": f"{type(exc).__name__}: {exc}",
                        "preview": preview,
                    }
                )
                if attempt < retries:
                    time.sleep(1.0)
                    continue
                return [], last_meta

            rows, meta = load_api_rows(payload)
            last_meta["resultCode"] = meta.get("resultCode")
            last_meta["resultMsg"] = meta.get("resultMsg")
            code = str(meta.get("resultCode") or "").strip()
            if code == "0":
                inventory.append(f"[OK] {label}: {len(rows)} rows | {request_label}")
                time.sleep(0.25)
                return rows, last_meta
            if code == "4":
                inventory.append(f"[EMPTY] {label}: 0 rows | {request_label}")
                return [], last_meta
            errors.append(
                {
                    "label": label,
                    "attempt": attempt,
                    "status": "api_error",
                    "http_status": response.status_code,
                    "content_type": last_meta["content_type"],
                    "resultCode": code or "unknown",
                    "resultMsg": meta.get("resultMsg"),
                    "request": request_label,
                    "preview": preview,
                }
            )
            if attempt < retries:
                time.sleep(1.0)
                continue
            return [], last_meta
        except Exception as exc:
            errors.append(
                {
                    "label": label,
                    "attempt": attempt,
                    "status": "exception",
                    "request": request_label,
                    "message": f"{type(exc).__name__}: {exc}",
                }
            )
            if attempt < retries:
                time.sleep(1.0)
                continue
    return [], last_meta


def detect_csv_crs(df: pd.DataFrame, x_col: str, y_col: str) -> str | None:
    x = pd.to_numeric(df[x_col], errors="coerce")
    y = pd.to_numeric(df[y_col], errors="coerce")
    if x.dropna().empty or y.dropna().empty:
        return None
    xmin, xmax = float(x.min()), float(x.max())
    ymin, ymax = float(y.min()), float(y.max())
    if 124 <= xmin <= 132 and 124 <= xmax <= 132 and 33 <= ymin <= 39 and 33 <= ymax <= 39:
        return "EPSG:4326"
    if 190000 <= xmin <= 1000000 and 190000 <= xmax <= 1000000 and 100000 <= ymin <= 1000000 and 100000 <= ymax <= 1000000:
        return "EPSG:5179"
    return None


def pick_boundary_file() -> Path | None:
    for p in BOUNDARY_CANDIDATES:
        if p.exists():
            return p
    return None


def pick_seoul_stop_file() -> Path | None:
    if SEOUl_STOP_DIR.exists():
        candidates = []
        for ext in ["*.csv", "*.xlsx", "*.geojson", "*.shp"]:
            candidates.extend(SEOUl_STOP_DIR.glob(ext))
        if candidates:
            order = {".csv": 0, ".xlsx": 1, ".geojson": 2, ".shp": 3}
            return sorted(candidates, key=lambda p: (order.get(p.suffix.lower(), 9), p.name))[0]
    if SEOUl_STOP_FALLBACK.exists():
        return SEOUl_STOP_FALLBACK
    return None


def load_boundaries() -> tuple[gpd.GeoDataFrame, Path]:
    path = pick_boundary_file()
    if path is None:
        raise FileNotFoundError("경계 파일을 찾지 못했습니다.")
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        raise RuntimeError(f"경계 CRS를 확인할 수 없습니다: {path}")
    if not {"region_id", "region_name"}.issubset(gdf.columns):
        raise RuntimeError(f"경계 파일에 region_id/region_name이 없습니다: {path}")
    gdf = gdf.loc[gdf["region_id"].isin(REGION_TARGETS)].copy()
    if gdf.empty:
        raise RuntimeError("대상 region_id를 찾지 못했습니다.")
    return gdf, path


def representative_points(boundaries: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    projected = boundaries.to_crs(5179).copy()
    projected["rep_geom"] = projected.geometry.representative_point()
    reps = gpd.GeoDataFrame(projected.drop(columns="geometry"), geometry="rep_geom", crs=5179).to_crs(4326)
    reps["representative_lon"] = reps.geometry.x
    reps["representative_lat"] = reps.geometry.y
    reps["geometry"] = [Point(xy) for xy in zip(reps["representative_lon"], reps["representative_lat"])]
    return reps[["region_id", "region_name", "representative_lon", "representative_lat", "geometry"]].copy()


def standardize_seoul_static(path: Path, warnings: list[str], inventory: list[str]) -> gpd.GeoDataFrame | None:
    ext = path.suffix.lower()
    raw_rows = 0
    df: pd.DataFrame | None = None
    if ext == ".csv":
        for enc in ["cp949", "utf-8-sig", "euc-kr", "utf-8"]:
            try:
                df = pd.read_csv(path, encoding=enc, low_memory=False)
                inventory.append(f"[OK] seoul csv read using {enc}: {path}")
                break
            except Exception:
                continue
        if df is None or df.empty:
            warnings.append(f"서울 정류장 CSV를 읽지 못했습니다: {path}")
            return None
        raw_rows = len(df)
        cols = {c.lower(): c for c in df.columns}
        station_id_col = next((cols[k] for k in cols if k in {"station_id", "정류소id", "정류장id", "node_id", "sttn_id"}), None)
        station_name_col = next((cols[k] for k in cols if k in {"station_name", "정류소명", "정류장명", "node_nm", "sttn_nm"}), None)
        ars_col = next((cols[k] for k in cols if k in {"ars_id", "ars-id", "정류소번호", "정류장번호", "sttn_no", "mobile_no"}), None)
        lon_col = next((cols[k] for k in cols if k in {"lon", "lng", "경도", "x좌표", "x", "crdnt_x"}), None)
        lat_col = next((cols[k] for k in cols if k in {"lat", "위도", "y좌표", "y", "crdnt_y"}), None)
        if not all([station_name_col, lon_col, lat_col]):
            warnings.append(f"서울 정류장 CSV 컬럼을 진단하지 못했습니다: {path}")
            return None
        crs = detect_csv_crs(df, lon_col, lat_col)
        if crs is None:
            warnings.append(f"서울 정류장 CRS를 확정할 수 없습니다: {path}")
            return None
        lon = pd.to_numeric(df[lon_col], errors="coerce")
        lat = pd.to_numeric(df[lat_col], errors="coerce")
        if crs == "EPSG:5179":
            temp = gpd.GeoDataFrame(df.copy(), geometry=gpd.points_from_xy(lon, lat), crs=5179).to_crs(4326)
            lon = temp.geometry.x
            lat = temp.geometry.y
        out = gpd.GeoDataFrame(
            {
                "source": "seoul_static",
                "sido": "서울",
                "station_id": df[station_id_col].astype(str).str.strip() if station_id_col else None,
                "ars_id": df[ars_col].astype(str).str.strip() if ars_col else None,
                "station_name": df[station_name_col].astype(str).str.strip(),
                "mobile_no": df[ars_col].astype(str).str.strip() if ars_col else None,
                "lon": lon,
                "lat": lat,
                "source_api": "static_file",
                "source_accessed_at": NOW,
            },
            geometry=gpd.points_from_xy(lon, lat),
            crs=4326,
        )
    elif ext in {".geojson", ".json", ".shp"}:
        gdf = gpd.read_file(path)
        if gdf.crs is None:
            warnings.append(f"서울 정류장 공간파일 CRS를 확인할 수 없습니다: {path}")
            return None
        raw_rows = len(gdf)
        gdf = gdf.to_crs(4326)
        cols = {c.lower(): c for c in gdf.columns}
        station_id_col = next((cols[k] for k in cols if k in {"station_id", "정류소id", "정류장id", "node_id", "sttn_id"}), None)
        station_name_col = next((cols[k] for k in cols if k in {"station_name", "정류소명", "정류장명", "node_nm", "sttn_nm"}), None)
        ars_col = next((cols[k] for k in cols if k in {"ars_id", "ars-id", "정류소번호", "정류장번호", "sttn_no", "mobile_no"}), None)
        if not station_name_col:
            warnings.append(f"서울 정류장 공간파일 컬럼을 진단하지 못했습니다: {path}")
            return None
        out = gpd.GeoDataFrame(
            {
                "source": "seoul_static",
                "sido": "서울",
                "station_id": gdf[station_id_col].astype(str).str.strip() if station_id_col else None,
                "ars_id": gdf[ars_col].astype(str).str.strip() if ars_col else None,
                "station_name": gdf[station_name_col].astype(str).str.strip(),
                "mobile_no": gdf[ars_col].astype(str).str.strip() if ars_col else None,
                "lon": gdf.geometry.x,
                "lat": gdf.geometry.y,
                "source_api": "static_file",
                "source_accessed_at": NOW,
            },
            geometry=gdf.geometry,
            crs=4326,
        )
    else:
        warnings.append(f"지원하지 않는 서울 정류장 파일 형식입니다: {path}")
        return None

    out = out.loc[out["lon"].between(124, 132) & out["lat"].between(33, 39)].copy()
    if out.empty:
        warnings.append(f"서울 정류장 좌표가 비정상입니다: {path}")
        return None
    before = len(out)
    out["station_identity"] = out.apply(station_identity, axis=1)
    out = out.sort_values(["station_identity", "station_name"]).drop_duplicates("station_identity", keep="first").copy()
    after = len(out)
    inventory.append(f"[OK] seoul raw rows={raw_rows}, dedup_before={before}, dedup_after={after}, crs=EPSG:4326")
    return out[["source", "sido", "station_id", "ars_id", "station_name", "mobile_no", "lon", "lat", "geometry", "source_api", "source_accessed_at"]]


def standardize_gbis_stops(rows: list[dict[str, Any]], region_id: str, region_name: str, source_api: str) -> gpd.GeoDataFrame:
    items = []
    for row in rows:
        lon = safe_float(pick_first(pd.Series(row), ["x", "lon", "lng"]))
        lat = safe_float(pick_first(pd.Series(row), ["y", "lat"]))
        if lon is None or lat is None:
            continue
        items.append(
            {
                "region_id": region_id,
                "region_name": region_name,
                "source": "gbis_api",
                "source_api": source_api,
                "source_accessed_at": NOW,
                "station_id": str(pick_first(pd.Series(row), ["stationId", "station_id"]) or "").strip(),
                "station_name": str(pick_first(pd.Series(row), ["stationName", "station_name"]) or "").strip(),
                "mobile_no": str(pick_first(pd.Series(row), ["mobileNo", "mobile_no"]) or "").strip() or None,
                "station_region_name": str(pick_first(pd.Series(row), ["regionName", "stationRegionName"]) or "").strip() or None,
                "center_yn": str(pick_first(pd.Series(row), ["centerYn", "center_yn"]) or "").strip() or None,
                "lon": lon,
                "lat": lat,
                "distance_m": safe_float(pick_first(pd.Series(row), ["distance"])),
                "geometry": Point(lon, lat),
            }
        )
    gdf = gpd.GeoDataFrame(items, geometry="geometry", crs=4326)
    gdf["station_identity"] = gdf.apply(station_identity, axis=1)
    return gdf.sort_values(["distance_m", "station_id"]).drop_duplicates("station_identity", keep="first")


def standardize_gbis_routes(rows: list[dict[str, Any]], region_id: str, region_name: str, station_id: str, station_name: str) -> pd.DataFrame:
    items = []
    for row in rows:
        items.append(
            {
                "region_id": region_id,
                "region_name": region_name,
                "station_id": station_id,
                "station_name": station_name,
                "route_id": str(pick_first(pd.Series(row), ["routeId", "route_id"]) or "").strip(),
                "route_name": str(pick_first(pd.Series(row), ["routeName", "route_name"]) or "").strip(),
                "route_type_cd": str(pick_first(pd.Series(row), ["routeTypeCd", "route_type_cd"]) or "").strip(),
                "route_type_name": str(pick_first(pd.Series(row), ["routeTypeName", "route_type_name"]) or "").strip(),
                "route_region_name": str(pick_first(pd.Series(row), ["regionName", "routeRegionName"]) or "").strip() or None,
                "sta_order": safe_float(pick_first(pd.Series(row), ["staOrder", "sta_order"])),
                "route_dest_id": str(pick_first(pd.Series(row), ["routeDestId", "route_dest_id"]) or "").strip() or None,
                "route_dest_name": str(pick_first(pd.Series(row), ["routeDestName", "route_dest_name"]) or "").strip() or None,
                "source_api": "getBusStationViaRouteListv2",
                "source_accessed_at": NOW,
            }
        )
    return pd.DataFrame(items)


def standardize_route_stations(rows: list[dict[str, Any]], route_id: str, route_name: str) -> gpd.GeoDataFrame:
    items = []
    for row in rows:
        lon = safe_float(pick_first(pd.Series(row), ["x", "lon", "lng"]))
        lat = safe_float(pick_first(pd.Series(row), ["y", "lat"]))
        if lon is None or lat is None:
            continue
        items.append(
            {
                "route_id": route_id,
                "route_name": route_name,
                "station_id": str(pick_first(pd.Series(row), ["stationId", "station_id"]) or "").strip(),
                "station_name": str(pick_first(pd.Series(row), ["stationName", "station_name"]) or "").strip(),
                "station_seq": safe_float(pick_first(pd.Series(row), ["stationSeq", "station_seq"])),
                "turn_yn": str(pick_first(pd.Series(row), ["turnYn", "turn_yn"]) or "").strip() or None,
                "turn_seq": safe_float(pick_first(pd.Series(row), ["turnSeq", "turn_seq"])),
                "district_cd": str(pick_first(pd.Series(row), ["districtCd", "district_cd"]) or "").strip() or None,
                "admin_name": str(pick_first(pd.Series(row), ["adminName", "admin_name"]) or "").strip() or None,
                "region_name": str(pick_first(pd.Series(row), ["regionName", "region_name"]) or "").strip() or None,
                "mobile_no": str(pick_first(pd.Series(row), ["mobileNo", "mobile_no"]) or "").strip() or None,
                "center_yn": str(pick_first(pd.Series(row), ["centerYn", "center_yn"]) or "").strip() or None,
                "lon": lon,
                "lat": lat,
                "source_api": "getBusRouteStationListv2",
                "source_accessed_at": NOW,
                "geometry": Point(lon, lat),
            }
        )
    return gpd.GeoDataFrame(items, geometry="geometry", crs=4326)


def within_radius_count(points: gpd.GeoDataFrame, rep_point: Point, radius_m: float = RADIUS_M) -> int:
    if points.empty:
        return 0
    rep_5179 = gpd.GeoSeries([rep_point], crs=4326).to_crs(5179).iloc[0]
    projected = points.to_crs(5179)
    return int((projected.geometry.distance(rep_5179) <= radius_m).sum())


def nearest_distance(points: gpd.GeoDataFrame, rep_point: Point) -> float | None:
    if points.empty:
        return None
    rep_5179 = gpd.GeoSeries([rep_point], crs=4326).to_crs(5179).iloc[0]
    projected = points.to_crs(5179)
    d = projected.geometry.distance(rep_5179)
    return float(d.min()) if not d.empty else None


def summarize_route_types(route_df: pd.DataFrame) -> pd.DataFrame:
    if route_df.empty:
        return pd.DataFrame(columns=["region_id", "region_name", "route_type_cd", "route_type_name", "route_count", "route_group"])
    rows = []
    for (region_id, region_name, cd, name), group in route_df.groupby(["region_id", "region_name", "route_type_cd", "route_type_name"], dropna=False):
        cd = str(cd or "")
        if cd in EXPRESS_ROUTE_TYPES:
            group_name = "광역/직행성"
        elif cd in LOCAL_ROUTE_TYPES:
            group_name = "지역/생활권"
        elif cd in SEAT_ROUTE_TYPES:
            group_name = "좌석형"
        else:
            group_name = "기타"
        rows.append(
            {
                "region_id": region_id,
                "region_name": region_name,
                "route_type_cd": cd,
                "route_type_name": name or ROUTE_TYPE_LABELS.get(cd, ""),
                "route_count": int(group["route_id"].dropna().astype(str).nunique()),
                "route_group": group_name,
            }
        )
    return pd.DataFrame(rows).sort_values(["region_id", "route_group", "route_type_cd"], na_position="last")


def route_direction_summary(route_station_gdf: gpd.GeoDataFrame) -> dict[str, Any]:
    if route_station_gdf.empty:
        return {}
    summary: dict[str, Any] = {}
    for route_id, group in route_station_gdf.groupby("route_id", dropna=False):
        ordered = group.sort_values(["station_seq", "turn_seq"], na_position="last")
        summary[str(route_id)] = {
            "route_name": ordered.iloc[0]["route_name"] if len(ordered) else None,
            "station_count": int(len(group)),
            "center_count": int((group["center_yn"].astype(str).str.upper() == "Y").sum()) if "center_yn" in group else None,
            "turn_count": int((group["turn_yn"].astype(str).str.upper() == "Y").sum()) if "turn_yn" in group else None,
            "first_station": ordered.iloc[0]["station_name"] if len(ordered) else None,
            "last_station": ordered.iloc[-1]["station_name"] if len(ordered) else None,
        }
    return summary


def write_inventory(path: Path, title: str, lines: list[str]) -> None:
    write_text(path, "\n".join([f"# {title}", "", *lines]).rstrip() + "\n")


def main() -> None:
    ensure_dirs()
    load_dotenv(ROOT / ".env")

    errors: list[dict[str, Any]] = []
    inventory: list[str] = []
    warnings: list[str] = []

    service_key = os.getenv(SERVICE_KEY_ENV, "").strip()
    if not service_key:
        print("GBIS_SERVICE_KEY가 설정되지 않았습니다. 프로젝트 루트의 .env 파일을 확인하세요.")
        raise SystemExit(1)

    boundaries, boundary_path = load_boundaries()
    reps = representative_points(boundaries)
    write_csv(DATA_PROCESSED / "region_representative_points_v3.csv", reps.drop(columns="geometry"))

    seoul_path = pick_seoul_stop_file()
    seoul_found = seoul_path is not None
    seoul_stops = standardize_seoul_static(seoul_path, warnings, inventory) if seoul_path else None
    if seoul_stops is None or seoul_stops.empty:
        write_inventory(
            DATA_INVENTORY / "seoul_bus_stop_missing_or_failed_v3.md",
            "seoul_bus_stop_missing_or_failed_v3",
            ["서울 버스정류장 정적 데이터가 없거나 읽기/표준화에 실패했습니다."],
        )

    gbis_stop_frames: list[gpd.GeoDataFrame] = []
    gbis_route_frames: list[pd.DataFrame] = []
    route_station_frames: list[gpd.GeoDataFrame] = []
    route_catalog: dict[str, dict[str, Any]] = {}

    for rep in reps.itertuples(index=False):
        around_rows, around_meta = api_get(
            GBIS_AROUND_URL,
            {"serviceKey": service_key, "x": rep.representative_lon, "y": rep.representative_lat, "format": "json"},
            f"{rep.region_id}:around",
            inventory,
            errors,
        )
        stop_df = standardize_gbis_stops(around_rows, str(rep.region_id), str(rep.region_name), "getBusStationAroundListv2")
        stop_df = stop_df.loc[pd.to_numeric(stop_df["distance_m"], errors="coerce").fillna(999999) <= RADIUS_M].copy()
        gbis_stop_frames.append(stop_df)
        for stop in stop_df.itertuples(index=False):
            route_rows, _ = api_get(
                GBIS_VIA_ROUTE_URL,
                {"serviceKey": service_key, "stationId": stop.station_id, "format": "json"},
                f"{rep.region_id}:via:{stop.station_id}",
                inventory,
                errors,
            )
            route_df = standardize_gbis_routes(route_rows, str(rep.region_id), str(rep.region_name), str(stop.station_id), str(stop.station_name))
            if not route_df.empty:
                gbis_route_frames.append(route_df)
                for row in route_df.to_dict(orient="records"):
                    rid = str(row.get("route_id") or "").strip()
                    if rid:
                        route_catalog.setdefault(
                            rid,
                            {
                                "route_id": rid,
                                "route_name": row.get("route_name"),
                                "route_type_cd": row.get("route_type_cd"),
                                "route_type_name": row.get("route_type_name"),
                            },
                        )

    gbis_stops = gpd.GeoDataFrame(pd.concat(gbis_stop_frames, ignore_index=True), geometry="geometry", crs=4326) if gbis_stop_frames else gpd.GeoDataFrame(columns=["region_id", "region_name", "source", "source_api", "source_accessed_at", "station_id", "station_name", "mobile_no", "station_region_name", "center_yn", "lon", "lat", "distance_m", "station_identity", "geometry"], geometry="geometry", crs=4326)
    if not gbis_stops.empty:
        gbis_stops = gbis_stops.loc[gbis_stops["station_identity"].notna()].copy()
        gbis_stops = gbis_stops.sort_values(["region_id", "distance_m", "station_id"]).drop_duplicates("station_identity", keep="first")
        write_geojson(DATA_PROCESSED / "gbis_bus_stops_near_regions_v3.geojson", gbis_stops)
        write_geojson(FRONTEND_DATA / "gbis_bus_stops_near_regions_v3.geojson", gbis_stops)

    gbis_routes = pd.concat(gbis_route_frames, ignore_index=True) if gbis_route_frames else pd.DataFrame(columns=["region_id", "region_name", "station_id", "station_name", "route_id", "route_name", "route_type_cd", "route_type_name", "route_region_name", "sta_order", "route_dest_id", "route_dest_name", "source_api", "source_accessed_at"])
    write_csv(DATA_PROCESSED / "gbis_bus_station_routes_v3.csv", gbis_routes)

    for route_id in sorted(route_catalog):
        route_station_rows, _ = api_get(
            GBIS_ROUTE_STATION_URL,
            {"serviceKey": service_key, "routeId": route_id, "format": "json"},
            f"route_station:{route_id}",
            inventory,
            errors,
        )
        if route_station_rows:
            route_station_frames.append(standardize_route_stations(route_station_rows, route_id, str(route_catalog[route_id].get("route_name") or "")))

    if route_station_frames:
        route_station_gdf = gpd.GeoDataFrame(pd.concat(route_station_frames, ignore_index=True), geometry="geometry", crs=4326)
        write_geojson(DATA_PROCESSED / "gbis_bus_route_stations_v3.geojson", route_station_gdf)
    else:
        route_station_gdf = gpd.GeoDataFrame(columns=["route_id", "route_name", "station_id", "station_name", "station_seq", "turn_yn", "turn_seq", "district_cd", "admin_name", "region_name", "mobile_no", "center_yn", "lon", "lat", "source_api", "source_accessed_at", "geometry"], geometry="geometry", crs=4326)

    if seoul_stops is None:
        seoul_stops = gpd.GeoDataFrame(columns=["source", "sido", "station_id", "ars_id", "station_name", "mobile_no", "lon", "lat", "geometry", "source_api", "source_accessed_at"], geometry="geometry", crs=4326)
    if not seoul_stops.empty:
        write_geojson(DATA_PROCESSED / "seoul_bus_stops_standardized_v3.geojson", seoul_stops)

    integrated = pd.concat([gbis_stops.copy(), seoul_stops.copy()], ignore_index=True, sort=False)
    if not integrated.empty:
        integrated = gpd.GeoDataFrame(integrated, geometry="geometry", crs=4326)
        integrated["integrated_identity"] = integrated.apply(integrated_identity, axis=1)
        integrated = integrated.sort_values(["station_name", "source"], na_position="last").drop_duplicates("integrated_identity", keep="first")
        write_geojson(DATA_PROCESSED / "bus_stops_seoul_gyeonggi_integrated_v3.geojson", integrated)
        write_geojson(FRONTEND_DATA / "bus_stops_seoul_gyeonggi_integrated_v3.geojson", integrated)

    route_type_summary = summarize_route_types(gbis_routes)
    write_csv(DATA_PROCESSED / "bus_route_type_summary_v3.csv", route_type_summary)
    write_text(FRONTEND_DATA / "bus_route_type_summary_v3.json", json.dumps(route_type_summary.to_dict(orient="records"), ensure_ascii=False, indent=2))

    direction_summary = route_direction_summary(route_station_gdf)

    metrics = []
    validation_warnings = []
    for rep in reps.itertuples(index=False):
        rep_point = Point(float(rep.representative_lon), float(rep.representative_lat))
        region_gbis = gbis_stops.loc[gbis_stops["region_id"] == rep.region_id].copy() if not gbis_stops.empty else gbis_stops.copy()
        region_routes = gbis_routes.loc[gbis_routes["region_id"] == rep.region_id].copy() if not gbis_routes.empty else gbis_routes.copy()
        seoul_count = within_radius_count(seoul_stops, rep_point) if not seoul_stops.empty else 0
        gbis_count = within_radius_count(region_gbis, rep_point) if not region_gbis.empty else 0
        integrated_count = within_radius_count(integrated, rep_point) if not integrated.empty else 0
        if integrated_count < seoul_count:
            validation_warnings.append(f"{rep.region_id}: integrated_bus_stop_count_500m < seoul_bus_stop_count_500m")
        if integrated_count < gbis_count:
            validation_warnings.append(f"{rep.region_id}: integrated_bus_stop_count_500m < gbis_bus_stop_count_500m")
        nearest_m = nearest_distance(integrated, rep_point) if not integrated.empty else None
        central_count = int((region_gbis["center_yn"].astype(str).str.upper() == "Y").sum()) if not region_gbis.empty else None

        if region_routes.empty:
            unique_route_count = None
            avg_routes = None
            median_routes = None
            route_type_counts = None
            regional_express = None
            local_routes = None
            seat_routes = None
            diversity = None
            data_status = "no_gbis_data"
        else:
            unique_route_count = int(region_routes["route_id"].dropna().astype(str).nunique())
            routes_per_stop = region_routes.groupby("station_id")["route_id"].nunique()
            avg_routes = float(routes_per_stop.mean()) if not routes_per_stop.empty else None
            median_routes = float(routes_per_stop.median()) if not routes_per_stop.empty else None
            route_type_counts = {str(k): int(v) for k, v in region_routes.groupby("route_type_cd")["route_id"].nunique().items() if pd.notna(k)}
            regional_express = int(sum(v for k, v in route_type_counts.items() if k in EXPRESS_ROUTE_TYPES))
            local_routes = int(sum(v for k, v in route_type_counts.items() if k in LOCAL_ROUTE_TYPES))
            seat_routes = int(sum(v for k, v in route_type_counts.items() if k in SEAT_ROUTE_TYPES))
            diversity = int(len(route_type_counts))
            data_status = "ok"

        note = "버스 접근성은 정류장·노선 기반 보조지표이며 시간권 분석이 아니다."
        if rep.region_id == "wirye_core":
            note += " 위례는 서울 송파구와 경기 성남·하남에 걸쳐 있어 서울버스와 경기버스 체계가 함께 작동한다. 본 분석에서 서울 정류장 자료는 위치 기반 정류장 수에는 반영되지만, 서울 면허 노선의 경유노선 수와 노선유형은 별도 서울 노선자료가 없으면 완전하게 반영되지 않는다."
        note += " 본 버스 접근성 지표는 업무지구 전체 경계의 500m 접근권이 아니라, 각 업무지구의 대표점 기준 500m 주변정류소 조회 결과이다. 따라서 면적이 넓거나 선형으로 배치된 업무지구에서는 실제 정류장 접근성이 과소추정될 수 있다. 향후에는 업무지구 경계 500m buffer 또는 경계 샘플링 기반 정류장 수집 방식으로 보완할 필요가 있다."

        metrics.append(
            {
                "region_id": rep.region_id,
                "region_name": rep.region_name,
                "representative_lon": rep.representative_lon,
                "representative_lat": rep.representative_lat,
                "gbis_bus_stop_count_500m": gbis_count,
                "seoul_bus_stop_count_500m": seoul_count,
                "integrated_bus_stop_count_500m": integrated_count,
                "nearest_bus_stop_distance_m": nearest_m,
                "central_lane_stop_count_500m": central_count,
                "unique_route_count_500m": unique_route_count,
                "avg_routes_per_stop_500m": avg_routes,
                "median_routes_per_stop_500m": median_routes,
                "regional_or_express_route_count": regional_express,
                "local_route_count": local_routes,
                "seat_route_count": seat_routes,
                "route_type_diversity_count": diversity,
                "route_type_summary": json.dumps(route_type_counts, ensure_ascii=False) if route_type_counts is not None else None,
                "bus_accessibility_data_status": data_status,
                "bus_accessibility_note": note,
            }
        )

    summary_df = pd.DataFrame(metrics)
    write_csv(DATA_PROCESSED / "bus_accessibility_by_region_v3.csv", summary_df)
    write_text(FRONTEND_DATA / "bus_accessibility_v3.json", json.dumps(summary_df.to_dict(orient="records"), ensure_ascii=False, indent=2))

    methodology = [
        "버스 접근성은 서울 버스정류장 정적 데이터와 경기버스정보 API를 전처리하여 산정한 정류장·경유노선 기반 보조지표이다.",
        "본 버스 접근성 지표는 업무지구 전체 경계의 500m 접근권이 아니라, 각 업무지구의 대표점 기준 500m 주변정류소 조회 결과이다. 따라서 면적이 넓거나 선형으로 배치된 업무지구에서는 실제 정류장 접근성이 과소추정될 수 있다. 향후에는 업무지구 경계 500m buffer 또는 경계 샘플링 기반 정류장 수집 방식으로 보완할 필요가 있다.",
        "경기버스정보 API는 정류장별 경유노선과 노선유형 산정에 사용했고, 서울 정류장 자료는 정류장 수와 위치 보완에 사용하였다.",
        "따라서 본 지표는 시간대별 배차간격, 실제 버스 주행시간, 도로 혼잡, 환승대기시간을 반영한 30분·60분 버스 등시간권이 아니다.",
        "서울버스 노선정보가 별도 노선자료 없이 확보되지 않으면 서울 면허 노선의 경유노선 수와 노선유형은 완전하게 반영되지 않을 수 있다.",
        "향후에는 GTFS 또는 시간대별 대중교통 API를 활용한 door-to-door 분석으로 확장하는 것이 바람직하다.",
    ]
    write_inventory(DATA_INVENTORY / "bus_accessibility_methodology_v3.md", "bus_accessibility_methodology_v3", methodology)

    if errors:
        write_inventory(DATA_INVENTORY / "gbis_api_errors_v3.md", "gbis_api_errors_v3", [f"- {json.dumps(e, ensure_ascii=False)}" for e in errors])
    else:
        write_inventory(DATA_INVENTORY / "gbis_api_errors_v3.md", "gbis_api_errors_v3", ["API 오류는 발생하지 않았습니다."])

    write_inventory(
        DATA_INVENTORY / "gbis_api_inventory_v3.md",
        "gbis_api_inventory_v3",
        [
            f"- boundary file: {boundary_path}",
            f"- seoul file found: {seoul_found}",
            f"- seoul standardized: {bool(seoul_stops is not None and not seoul_stops.empty)}",
            f"- gbis around used: {not gbis_stops.empty}",
            f"- gbis via-route used: {not gbis_routes.empty}",
            f"- gbis route-station used: {not route_station_gdf.empty}",
            f"- unique route count: {len(route_catalog)}",
            *[f"- {line}" for line in inventory[:2000]],
        ],
    )

    validation_lines = [
        f"- seoul raw rows: {len(pd.read_csv(seoul_path, encoding='cp949', low_memory=False)) if seoul_path and seoul_path.suffix.lower() == '.csv' else 'n/a'}",
        f"- seoul dedup rows: {0 if seoul_stops is None else len(seoul_stops)}",
        f"- gbis stop rows: {len(gbis_stops)}",
        f"- integrated rows: {0 if integrated.empty else len(integrated)}",
        f"- integrated >= seoul: {all(summary_df['integrated_bus_stop_count_500m'] >= summary_df['seoul_bus_stop_count_500m']) if not summary_df.empty else 'n/a'}",
        f"- integrated >= gbis: {all(summary_df['integrated_bus_stop_count_500m'] >= summary_df['gbis_bus_stop_count_500m']) if not summary_df.empty else 'n/a'}",
        f"- distance CRS: EPSG:5179 for distance and buffer; EPSG:4326 for storage",
        f"- null/N/A handling: {summary_df['bus_accessibility_data_status'].isin(['ok', 'no_gbis_data']).all() if 'bus_accessibility_data_status' in summary_df.columns else False}",
        *[f"- warning: {w}" for w in validation_warnings],
    ]
    write_inventory(DATA_INVENTORY / "bus_accessibility_validation_v3.md", "bus_accessibility_validation_v3", validation_lines)

    print(f".env 로드 성공 여부: {bool(service_key)}")
    print(f"key masked: {service_key[:4]}...{service_key[-4:] if len(service_key) >= 8 else '****'}")
    print(f"대표점 출처: {boundary_path if boundary_path else 'n/a'}")
    print(f"서울 정류장 원본/표준화: raw={len(pd.read_csv(seoul_path, encoding='cp949', low_memory=False)) if seoul_path and seoul_path.suffix.lower() == '.csv' else 'n/a'}, dedup={0 if seoul_stops is None else len(seoul_stops)}")
    print(f"경기버스 주변정류소 API 호출 성공 여부: {not gbis_stops.empty}")
    print(f"경기버스 정류소 경유노선 API 호출 성공 여부: {not gbis_routes.empty}")
    print(f"경유정류소 목록조회 API 실행 여부: {not route_station_gdf.empty}")
    print(f"API 오류 수: {len(errors)}")
    print(f"수집된 경기버스 정류장 수: {len(gbis_stops)}")
    print(f"수집된 정류소-노선 row 수: {len(gbis_routes)}")
    print(f"수집된 unique routeId 수: {len(route_catalog)}")
    print(f"서울 정류장 dedup 전/후 수: raw={len(pd.read_csv(seoul_path, encoding='cp949', low_memory=False)) if seoul_path and seoul_path.suffix.lower() == '.csv' else 'n/a'}, dedup={0 if seoul_stops is None else len(seoul_stops)}")
    print(f"통합 정류장 수: {0 if integrated.empty else len(integrated)}")
    print("판교/위례별 최종 버스 접근성 지표:")
    print(summary_df.to_string(index=False) if not summary_df.empty else "empty")
    print(f"validation integrated >= seoul: {all(summary_df['integrated_bus_stop_count_500m'] >= summary_df['seoul_bus_stop_count_500m']) if not summary_df.empty else 'n/a'}")
    print(f"validation integrated >= gbis: {all(summary_df['integrated_bus_stop_count_500m'] >= summary_df['gbis_bus_stop_count_500m']) if not summary_df.empty else 'n/a'}")
    print("validation distance CRS: EPSG:5179")
    print(f"validation null/N/A: {summary_df['bus_accessibility_data_status'].isin(['ok', 'no_gbis_data']).all() if 'bus_accessibility_data_status' in summary_df.columns else False}")


if __name__ == "__main__":
    main()
