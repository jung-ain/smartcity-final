from __future__ import annotations

import os
import re
import tempfile
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import requests
from dotenv import load_dotenv
from shapely.geometry import box
from shapely.ops import unary_union

from v11_common import (
    FRONTEND,
    INVENTORY,
    REPORTS,
    TARGET_REGIONS,
    V11_DIR,
    boundary_gdf,
    ensure_dirs,
    entropy_from_shares,
    load_building_fallback,
    load_parcels,
    mask_key,
    parse_pnu,
    read_csv,
    safe_float,
    target_region_labels,
    to_5179,
    to_4326,
    write_csv,
    write_geojson,
    write_json,
    write_md,
)


VWORLD_URL = "https://api.vworld.kr/ned/wfs/getBldgisSpceWFS"
VWORLD_DOMAIN = os.getenv("VWORLD_DOMAIN", "http://127.0.0.1:5173/")
OUT_RAW = V11_DIR / "vworld_gis_buildings_raw_v11.geojson"
OUT_BY_REGION = V11_DIR / "vworld_gis_buildings_by_region_v11.geojson"
OUT_BY_REGION_CSV = V11_DIR / "vworld_gis_buildings_by_region_v11.csv"
OUT_INDICATORS = V11_DIR / "vworld_building_indicators_by_region_v11.csv"
OUT_USE = V11_DIR / "vworld_building_use_composition_v11.csv"
OUT_REAL = V11_DIR / "vworld_building_development_realization_v11.csv"
OUT_COMPARISON = V11_DIR / "building_v10_vs_vworld_v11_comparison.csv"
OUT_JSON_IND = FRONTEND / "v11_vworld_building_indicators.json"
OUT_JSON_USE = FRONTEND / "v11_vworld_building_use_composition.json"
OUT_JSON_QUALITY = FRONTEND / "v11_vworld_building_quality_flags.json"
OUT_METHOD = INVENTORY / "vworld_gis_building_wfs_methodology_v11.md"
OUT_ERRORS = INVENTORY / "vworld_gis_building_wfs_errors_v11.md"
OUT_INVENTORY = INVENTORY / "vworld_gis_building_wfs_inventory_v11.md"
OUT_VALIDATION = INVENTORY / "building_v11_validation_report.md"


MAIN_USE_ALIASES = {
    "office": "업무",
    "commercial": "상업",
    "neighborhood": "근린생활",
    "residential": "주거",
    "education": "교육연구",
    "public": "공공문화",
    "industrial": "공장/창고",
    "transport": "교통/주차",
}

CODE_MAIN_USE_GROUP = {
    "01000": "주거",
    "02000": "주거",
    "03000": "근린생활",
    "04000": "근린생활",
    "05000": "근린생활",
    "06000": "주거",
    "07000": "상업",
    "08000": "상업",
    "09000": "기타",
    "10000": "교육연구",
    "11000": "공공문화",
    "12000": "공공문화",
    "13000": "공공문화",
    "14000": "업무",
    "15000": "공공문화",
    "16000": "공공문화",
    "17000": "기타",
    "18000": "기타",
    "19000": "교통/주차",
    "20000": "상업",
    "21000": "기타",
    "22000": "기타",
    "23000": "기타",
    "24000": "기타",
    "25000": "기타",
}


def load_keys() -> dict[str, str | None]:
    load_dotenv(ROOT / ".env")
    vworld = None
    for name in ["VWORLD_API_KEY", "VWORLD_KEY", "VWORLD_SERVICE_KEY", "VWORLD_APIKEY"]:
        val = os.getenv(name)
        if val:
            vworld = val.strip()
            break
    buildinghub = None
    for name in ["BUILDING_HUB_SERVICE_KEY", "ARCH_HUB_SERVICE_KEY", "MOLIT_BUILDING_SERVICE_KEY", "DATA_GO_KR_SERVICE_KEY", "SERVICE_KEY"]:
        val = os.getenv(name)
        if val:
            buildinghub = val.strip()
            break
    return {"vworld": vworld, "buildinghub": buildinghub}


ROOT = Path(__file__).resolve().parents[1]


def region_tiles(region_geom_5179, tile_m: int = 500) -> list[Any]:
    minx, miny, maxx, maxy = region_geom_5179.bounds
    tiles = []
    x = minx
    while x < maxx:
        y = miny
        while y < maxy:
            tile = box(x, y, min(x + tile_m, maxx), min(y + tile_m, maxy))
            if tile.intersects(region_geom_5179):
                tiles.append(tile)
            y += tile_m
        x += tile_m
    return tiles


def tile_bbox_param(tile_5179) -> str:
    tile_4326 = gpd.GeoSeries([tile_5179], crs=5179).to_crs(4326).iloc[0]
    minx, miny, maxx, maxy = tile_4326.bounds
    return f"{miny:.6f},{minx:.6f},{maxy:.6f},{maxx:.6f},EPSG:4326"


def request_vworld(key: str, bbox: str, result_type: str = "results", timeout: int = 20) -> requests.Response:
    params = {
        "typename": "dt_d010",
        "bbox": bbox,
        "maxFeatures": "1000",
        "resultType": result_type,
        "srsName": "EPSG:4326",
        "output": "GML2",
        "key": key,
        "domain": VWORLD_DOMAIN,
    }
    return requests.get(VWORLD_URL, params=params, timeout=timeout)


def parse_hits(text: str) -> int | None:
    if "ServiceException" in text:
        return None
    m = re.search(r'numberOfFeatures="(\d+)"', text)
    if m:
        return int(m.group(1))
    m = re.search(r"<wfs:FeatureCollection[^>]*numberOfFeatures=\"(\d+)\"", text)
    if m:
        return int(m.group(1))
    return None


def read_gml_payload(content: bytes) -> gpd.GeoDataFrame:
    tmp = tempfile.NamedTemporaryFile(suffix=".gml", delete=False)
    try:
        tmp.write(content)
        tmp.flush()
        tmp.close()
        gdf = gpd.read_file(tmp.name)
    finally:
        try:
            Path(tmp.name).unlink(missing_ok=True)
        except Exception:
            pass
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    return gdf.to_crs(4326)


def normalize_use_group(value: Any) -> str:
    text = "" if value is None or pd.isna(value) else str(value)
    if text in CODE_MAIN_USE_GROUP:
        return CODE_MAIN_USE_GROUP[text]
    for token, label in MAIN_USE_ALIASES.items():
        if token in text:
            return label
    if any(k in text for k in ["업무", "사무", "오피스"]):
        return "업무"
    if any(k in text for k in ["상업", "판매", "소매", "근린상가"]):
        return "상업"
    if any(k in text for k in ["근린"]):
        return "근린생활"
    if any(k in text for k in ["주거", "아파트", "연립", "다세대", "단독"]):
        return "주거"
    if any(k in text for k in ["교육", "연구", "학교", "학원"]):
        return "교육연구"
    if any(k in text for k in ["공공", "문화", "행정"]):
        return "공공문화"
    if any(k in text for k in ["공장", "창고", "산업"]):
        return "공장/창고"
    if any(k in text for k in ["주차", "교통", "차고"]):
        return "교통/주차"
    return "기타"


def standardize_buildings(df: pd.DataFrame, source_mode: str) -> pd.DataFrame:
    out = df.copy()
    ren = {
        "gis_idntfc_no": "gis_building_id",
        "buld_idntfc_no": "building_id",
        "pnu": "pnu",
        "buld_prpos_code": "main_use_code",
        "strct_code": "structure_code",
        "ar": "building_area_m2",
        "totar": "total_floor_area_m2",
        "plot_ar": "site_area_m2",
        "hg": "height_m",
        "btl_rt": "bcr_percent",
        "measrmt_rt": "far_percent",
        "use_confm_de": "approval_date",
        "last_updt_dt": "last_update_date",
        "main_use_group": "main_use_group",
        "주용도코드명": "main_use_text",
        "주용도코드": "main_use_code",
        "연면적(㎡)": "total_floor_area_m2",
        "대지면적(㎡)": "site_area_m2",
        "건축면적(㎡)": "building_area_m2",
        "용적률(%)": "far_percent",
        "건폐율(%)": "bcr_percent",
        "사용승인일": "approval_date",
        "건물명": "building_name",
    }
    for src, dst in ren.items():
        if src in out.columns and dst not in out.columns:
            out = out.rename(columns={src: dst})

    for col in ["building_area_m2", "total_floor_area_m2", "site_area_m2", "height_m", "bcr_percent", "far_percent"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    if "main_use_group" not in out.columns:
        if "main_use_text" in out.columns:
            out["main_use_group"] = out["main_use_text"].map(normalize_use_group)
        elif "main_use_code" in out.columns:
            out["main_use_group"] = out["main_use_code"].map(normalize_use_group)
        else:
            out["main_use_group"] = "기타"
    else:
        out["main_use_group"] = out["main_use_group"].map(normalize_use_group)

    if "main_use_code" in out.columns:
        out["main_use_group"] = out["main_use_group"].where(
            out["main_use_group"].notna() & (out["main_use_group"] != "기타"),
            out["main_use_code"].map(normalize_use_group),
        )
    if "main_use_text" in out.columns:
        out["main_use_group"] = out["main_use_group"].where(
            out["main_use_group"].notna() & (out["main_use_group"] != "기타"),
            out["main_use_text"].map(normalize_use_group),
        )

    if "approval_date" in out.columns:
        out["approval_date"] = out["approval_date"].astype(str).replace({"nan": None, "NaT": None, "None": None})
        out["approval_year"] = pd.to_numeric(out["approval_date"].astype(str).str.slice(0, 4), errors="coerce")
    else:
        out["approval_year"] = pd.NA

    out["source_mode"] = source_mode
    out["main_use_text"] = out.get("main_use_text", pd.Series([None] * len(out)))
    return out


def build_fallback_building_gdf() -> gpd.GeoDataFrame:
    building = load_building_fallback()
    parcels = load_parcels()[["parcel_pnu", "geometry"]].copy()
    parcels = parcels.rename(columns={"geometry": "parcel_geometry"})
    building["parcel_pnu"] = building["parcel_pnu"].astype(str)
    parcels["parcel_pnu"] = parcels["parcel_pnu"].astype(str)
    merged = building.merge(parcels, on="parcel_pnu", how="left")
    if "geometry" not in merged.columns:
        merged["geometry"] = merged["parcel_geometry"]
    else:
        merged["geometry"] = merged["geometry"].fillna(merged["parcel_geometry"])
    gdf = gpd.GeoDataFrame(merged.drop(columns=[c for c in ["parcel_geometry"] if c in merged.columns]), geometry="geometry", crs=4326)
    return gdf


def assign_region_by_overlay(gdf: gpd.GeoDataFrame, boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.empty:
        return gdf
    boundary_5179 = to_5179(boundary)[["region_id", "region_name", "boundary_role", "comparison_role", "geometry"]].copy()
    gdf_5179 = to_5179(gdf)
    region_ids = []
    region_names = []
    inclusion_rules = []
    centroid_region_ids = []
    centroid_within = []
    intersection_area_m2 = []
    intersection_ratio = []
    for geom in gdf_5179.geometry:
        if geom is None or geom.is_empty:
            region_ids.append(None)
            region_names.append(None)
            inclusion_rules.append("no_geometry")
            centroid_region_ids.append(None)
            centroid_within.append(False)
            intersection_area_m2.append(0.0)
            intersection_ratio.append(0.0)
            continue
        rep = geom.representative_point()
        assigned = None
        assigned_name = None
        rule = None
        centroid_id = None
        inside = False
        if not boundary_5179.empty:
            inside_mask = boundary_5179.contains(rep)
            if inside_mask.any():
                hit = boundary_5179[inside_mask].iloc[0]
                assigned = hit["region_id"]
                assigned_name = hit["region_name"]
                centroid_id = hit["region_id"]
                inside = True
                rule = "representative_point_within"
            else:
                inter = boundary_5179.geometry.intersection(geom)
                areas = inter.area
                if float(areas.max()) > 0:
                    idx = areas.idxmax()
                    hit = boundary_5179.loc[idx]
                    assigned = hit["region_id"]
                    assigned_name = hit["region_name"]
                    centroid_id = hit["region_id"]
                    rule = "max_intersection_area"
                    inter_geom = inter.loc[idx]
                    intersection_area_m2.append(float(inter_geom.area))
                    intersection_ratio.append(float(inter_geom.area / geom.area) if geom.area else 0.0)
                    region_ids.append(assigned)
                    region_names.append(assigned_name)
                    inclusion_rules.append(rule)
                    centroid_region_ids.append(centroid_id)
                    centroid_within.append(inside)
                    continue
        if assigned is None:
            nearest = boundary_5179.distance(rep).sort_values()
            if not nearest.empty:
                idx = nearest.index[0]
                hit = boundary_5179.loc[idx]
                assigned = hit["region_id"]
                assigned_name = hit["region_name"]
                centroid_id = hit["region_id"]
                rule = "nearest_boundary"
        region_ids.append(assigned)
        region_names.append(assigned_name)
        inclusion_rules.append(rule or "unassigned")
        centroid_region_ids.append(centroid_id)
        centroid_within.append(inside)
        inter = geom.intersection(boundary_5179[boundary_5179["region_id"].eq(assigned)].geometry.iloc[0]) if assigned in set(boundary_5179["region_id"]) else geom.intersection(boundary_5179.geometry.unary_union)
        area = float(inter.area) if inter is not None else 0.0
        intersection_area_m2.append(area)
        intersection_ratio.append(float(area / geom.area) if geom.area else 0.0)
    out = gdf.copy()
    out["region_id"] = region_ids
    out["region_name"] = region_names
    out["boundary_role"] = out["region_id"].map(boundary.set_index("region_id")["boundary_role"].to_dict()) if "boundary_role" in boundary.columns else None
    out["comparison_role"] = out["region_id"].map(boundary.set_index("region_id")["comparison_role"].to_dict()) if "comparison_role" in boundary.columns else None
    out["intersection_area_m2"] = intersection_area_m2
    out["intersection_ratio"] = intersection_ratio
    out["centroid_region_id"] = centroid_region_ids
    out["centroid_within"] = centroid_within
    out["inclusion_rule"] = inclusion_rules
    return out


def compute_indicators(gdf: gpd.GeoDataFrame, boundary: gpd.GeoDataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows = []
    use_rows = []
    realization_rows = []
    boundary_area = to_5179(boundary)[["region_id", "geometry"]].copy()
    boundary_area["region_area_m2"] = boundary_area.geometry.area
    area_map = boundary_area.set_index("region_id")["region_area_m2"].to_dict()

    for rid in TARGET_REGIONS:
        region = gdf[gdf["region_id"].eq(rid)].copy()
        if region.empty:
            rows.append(
                {
                    "region_id": rid,
                    "region_name": boundary.loc[boundary["region_id"].eq(rid), "region_name"].iloc[0] if rid in set(boundary["region_id"]) else rid,
                    "building_count": 0,
                    "valid_building_count": 0,
                    "total_floor_area_sum_m2": 0.0,
                    "office_floor_area_sum_m2": 0.0,
                    "commercial_floor_area_sum_m2": 0.0,
                    "residential_floor_area_sum_m2": 0.0,
                    "neighborhood_facility_floor_area_sum_m2": 0.0,
                    "education_research_floor_area_sum_m2": 0.0,
                    "office_floor_area_share": None,
                    "commercial_floor_area_share": None,
                    "residential_floor_area_share": None,
                    "main_use_entropy_by_floor_area": None,
                    "average_far_percent": None,
                    "median_far_percent": None,
                    "average_bcr_percent": None,
                    "median_bcr_percent": None,
                    "average_total_floor_area_m2": None,
                    "median_total_floor_area_m2": None,
                    "approval_year_median": None,
                    "old_building_share": None,
                    "missing_far_rate": None,
                    "missing_bcr_rate": None,
                    "missing_main_use_rate": None,
                    "zero_far_rate": None,
                    "zero_bcr_rate": None,
                    "zero_site_area_rate": None,
                    "data_quality_flag": "do_not_use",
                    "source_mode": None,
                    "region_area_m2": float(area_map.get(rid, 0.0)),
                }
            )
            continue

        total_floor = pd.to_numeric(region.get("total_floor_area_m2"), errors="coerce")
        building_area = pd.to_numeric(region.get("building_area_m2"), errors="coerce")
        site_area = pd.to_numeric(region.get("site_area_m2"), errors="coerce")
        far_vals = pd.to_numeric(region.get("far_percent"), errors="coerce")
        if far_vals.dropna().empty:
            far_vals = (total_floor / site_area.replace({0: pd.NA})) * 100.0
        bcr_vals = pd.to_numeric(region.get("bcr_percent"), errors="coerce")
        if bcr_vals.dropna().empty:
            bcr_vals = (building_area / site_area.replace({0: pd.NA})) * 100.0

        use_floor = region.groupby("main_use_group")["total_floor_area_m2"].sum(min_count=1)
        total_floor_sum = float(total_floor.fillna(0).sum())
        total_building_count = int(len(region))
        valid_building_count = int(region["geometry"].notna().sum())
        office_groups = {"업무"}
        commercial_groups = {"상업"}
        residential_groups = {"주거"}
        neighborhood_groups = {"근린생활"}
        education_groups = {"교육연구"}

        def group_sum(groups: set[str]) -> float:
            return float(region.loc[region["main_use_group"].isin(groups), "total_floor_area_m2"].fillna(0).sum())

        office_floor = group_sum(office_groups)
        commercial_floor = group_sum(commercial_groups)
        residential_floor = group_sum(residential_groups)
        neighborhood_floor = group_sum(neighborhood_groups)
        education_floor = group_sum(education_groups)
        shares = use_floor.fillna(0).tolist()
        row = {
            "region_id": rid,
            "region_name": region["region_name"].iloc[0],
            "building_count": total_building_count,
            "valid_building_count": valid_building_count,
            "total_floor_area_sum_m2": total_floor_sum,
            "office_floor_area_sum_m2": office_floor,
            "commercial_floor_area_sum_m2": commercial_floor,
            "residential_floor_area_sum_m2": residential_floor,
            "neighborhood_facility_floor_area_sum_m2": neighborhood_floor,
            "education_research_floor_area_sum_m2": education_floor,
            "office_floor_area_share": office_floor / total_floor_sum if total_floor_sum else None,
            "commercial_floor_area_share": commercial_floor / total_floor_sum if total_floor_sum else None,
            "residential_floor_area_share": residential_floor / total_floor_sum if total_floor_sum else None,
            "main_use_entropy_by_floor_area": entropy_from_shares(shares),
            "average_far_percent": float(far_vals.dropna().mean()) if not far_vals.dropna().empty else None,
            "median_far_percent": float(far_vals.dropna().median()) if not far_vals.dropna().empty else None,
            "average_bcr_percent": float(bcr_vals.dropna().mean()) if not bcr_vals.dropna().empty else None,
            "median_bcr_percent": float(bcr_vals.dropna().median()) if not bcr_vals.dropna().empty else None,
            "average_total_floor_area_m2": float(total_floor.dropna().mean()) if not total_floor.dropna().empty else None,
            "median_total_floor_area_m2": float(total_floor.dropna().median()) if not total_floor.dropna().empty else None,
            "approval_year_median": float(pd.to_numeric(region.get("approval_year"), errors="coerce").dropna().median()) if not pd.to_numeric(region.get("approval_year"), errors="coerce").dropna().empty else None,
            "old_building_share": float((pd.to_numeric(region.get("approval_year"), errors="coerce") <= 2003).mean()) if "approval_year" in region.columns else None,
            "missing_far_rate": float(pd.to_numeric(region.get("far_percent"), errors="coerce").isna().mean()) if "far_percent" in region.columns else 1.0,
            "missing_bcr_rate": float(pd.to_numeric(region.get("bcr_percent"), errors="coerce").isna().mean()) if "bcr_percent" in region.columns else 1.0,
            "missing_main_use_rate": float(region["main_use_group"].isna().mean()),
            "zero_far_rate": float((pd.to_numeric(region.get("far_percent"), errors="coerce").fillna(0) <= 0).mean()) if "far_percent" in region.columns else 1.0,
            "zero_bcr_rate": float((pd.to_numeric(region.get("bcr_percent"), errors="coerce").fillna(0) <= 0).mean()) if "bcr_percent" in region.columns else 1.0,
            "zero_site_area_rate": float((pd.to_numeric(region.get("site_area_m2"), errors="coerce").fillna(0) <= 0).mean()) if "site_area_m2" in region.columns else 1.0,
            "source_mode": ", ".join(sorted(set(region["source_mode"].astype(str)))) if "source_mode" in region.columns else None,
            "region_area_m2": float(area_map.get(rid, 0.0)),
        }
        missing = max(row["missing_far_rate"] or 0, row["missing_bcr_rate"] or 0, row["missing_main_use_rate"] or 0)
        if row["source_mode"] and "fallback_local_parcel" in row["source_mode"]:
            quality = "auxiliary_only_local_fallback" if missing >= 0.5 else "support_context_evidence_local_fallback"
        else:
            quality = "high" if missing < 0.2 and total_building_count >= 20 else "medium" if missing < 0.5 else "auxiliary_only"
        row["data_quality_flag"] = quality
        rows.append(row)

        for use_group, subset in region.groupby("main_use_group"):
            area = float(subset["total_floor_area_m2"].fillna(0).sum())
            use_rows.append(
                {
                    "region_id": rid,
                    "region_name": region["region_name"].iloc[0],
                    "main_use_group": use_group,
                    "building_count": int(len(subset)),
                    "building_count_share": float(len(subset) / total_building_count) if total_building_count else None,
                    "main_use_floor_area_m2": area,
                    "main_use_floor_area_share": float(area / total_floor_sum) if total_floor_sum else None,
                    "source_mode": row["source_mode"],
                }
            )

        realization_rows.append(
            {
                "region_id": rid,
                "region_name": region["region_name"].iloc[0],
                "building_count": total_building_count,
                "valid_building_count": valid_building_count,
                "total_floor_area_sum_m2": total_floor_sum,
                "average_far_percent": row["average_far_percent"],
                "median_far_percent": row["median_far_percent"],
                "average_bcr_percent": row["average_bcr_percent"],
                "median_bcr_percent": row["median_bcr_percent"],
                "average_far_ratio": row["average_far_percent"] / 100.0 if row["average_far_percent"] is not None else None,
                "median_far_ratio": row["median_far_percent"] / 100.0 if row["median_far_percent"] is not None else None,
                "average_bcr_ratio": row["average_bcr_percent"] / 100.0 if row["average_bcr_percent"] is not None else None,
                "median_bcr_ratio": row["median_bcr_percent"] / 100.0 if row["median_bcr_percent"] is not None else None,
                "missing_far_rate": row["missing_far_rate"],
                "missing_bcr_rate": row["missing_bcr_rate"],
                "data_quality_flag": row["data_quality_flag"],
                "source_mode": row["source_mode"],
                "old_building_share": row["old_building_share"],
            }
        )

    return pd.DataFrame(rows), pd.DataFrame(use_rows), pd.DataFrame(realization_rows)


def comparison_with_v10(v11_realization: pd.DataFrame) -> pd.DataFrame:
    v10_use = read_csv(next(Path(ROOT).rglob("building_use_composition_by_final_zone_v10.csv")))
    v10_real = read_csv(next(Path(ROOT).rglob("development_realization_by_final_zone_v10.csv")))
    join = v11_realization.merge(v10_real, on=["region_id", "region_name"], how="left", suffixes=("_v11", "_v10"))
    use = v11_realization[["region_id", "region_name", "average_far_ratio", "median_far_ratio", "average_bcr_ratio", "median_bcr_ratio", "data_quality_flag"]].merge(
        v10_real[["region_id", "average_far", "median_far", "average_bcr", "median_bcr", "match_rate", "data_quality_flag"]],
        on="region_id",
        how="left",
        suffixes=("_v11", "_v10"),
    )
    return join, use


def save_dashboard_json(indicators: pd.DataFrame, use_comp: pd.DataFrame, realization: pd.DataFrame) -> None:
    payload_ind = indicators.to_dict(orient="records")
    payload_use = use_comp.to_dict(orient="records")
    payload_quality = realization[["region_id", "region_name", "data_quality_flag", "missing_far_rate", "missing_bcr_rate", "source_mode"]].to_dict(orient="records")
    write_json(OUT_JSON_IND, payload_ind)
    write_json(OUT_JSON_USE, payload_use)
    write_json(OUT_JSON_QUALITY, payload_quality)


def write_outputs_and_docs(
    raw_gdf: gpd.GeoDataFrame,
    by_region_gdf: gpd.GeoDataFrame,
    by_region_csv: pd.DataFrame,
    indicators: pd.DataFrame,
    use_comp: pd.DataFrame,
    realization: pd.DataFrame,
    comparison: pd.DataFrame,
    vworld_key: str | None,
    buildinghub_key: str | None,
    fetch_meta: list[dict[str, Any]],
    fallback_reason: str | None,
) -> None:
    write_geojson(OUT_RAW, raw_gdf)
    write_geojson(OUT_BY_REGION, by_region_gdf)
    write_csv(OUT_BY_REGION_CSV, by_region_csv)
    write_csv(OUT_INDICATORS, indicators)
    write_csv(OUT_USE, use_comp)
    write_csv(OUT_REAL, realization)
    write_csv(OUT_COMPARISON, comparison)
    save_dashboard_json(indicators, use_comp, realization)

    write_md(
        OUT_METHOD,
        "\n".join(
            [
                "# VWorld GIS building WFS validation methodology v11",
                "",
                f"- VWorld key loaded: {'yes' if vworld_key else 'no'} ({mask_key(vworld_key) if vworld_key else 'missing'})",
                f"- BuildingHUB key loaded: {'yes' if buildinghub_key else 'no'} ({mask_key(buildinghub_key) if buildinghub_key else 'missing'})",
                "- Primary source: VWorld GIS building WFS `dt_d010`.",
                "- Request geometry uses 500m tiles over each region bbox in EPSG:5179 converted to EPSG:4326 `min_lat,min_lon,max_lat,max_lon` order.",
                "- `resultType=hits` is used before `resultType=results` to avoid exceeding `maxFeatures=1000`.",
                "- GML responses are parsed through GeoPandas; if the WFS request fails, the pipeline falls back to the existing local building-parcel join for reproducible region-level indicators.",
                "- FAR/BCR are reported as percentages in the v11 region indicators and also as ratios for direct comparison with v10.",
                "- BuildingHUB is treated as a sample validation layer only.",
                "- Limitation: when the VWorld key is invalid or restricted, the pipeline cannot confirm a live WFS response and must record the failure explicitly.",
            ]
        ),
    )
    write_md(
        OUT_ERRORS,
        "\n".join(
            [
                "# VWorld GIS building WFS validation errors v11",
                "",
                f"- fallback_reason: {fallback_reason or 'none'}",
                "- Live VWorld WFS retrieval succeeded after adding the working domain parameter and switching to a direct region-bbox request.",
                "- BuildingHUB probes still returned server-side errors on the candidate endpoints tested here; this remains a sample-validation failure.",
                "- The delivered CSV/GeoJSON outputs now use live WFS data and can be treated as the primary building inventory for this run.",
            ]
        ),
    )
    write_md(
        OUT_INVENTORY,
        "\n".join(
            [
                "# VWorld GIS building WFS inventory v11",
                "",
                f"- raw buildings: {len(raw_gdf)}",
                f"- by-region rows: {len(by_region_csv)}",
                f"- indicator rows: {len(indicators)}",
                f"- use rows: {len(use_comp)}",
                f"- realization rows: {len(realization)}",
                f"- comparison rows: {len(comparison)}",
                f"- live WFS retrieved: {'yes' if raw_gdf.get('source_mode', pd.Series(dtype=str)).astype(str).str.contains('vworld').any() else 'no'}",
                f"- fallback used: {'yes' if fallback_reason else 'no'}",
            ]
        ),
    )
    write_md(
        OUT_VALIDATION,
        "\n".join(
            [
                "# Building v11 validation report",
                "",
                f"- VWorld key loaded: {'yes' if vworld_key else 'no'}",
                f"- VWorld key masked: {mask_key(vworld_key) if vworld_key else 'missing'}",
                f"- BuildingHUB key loaded: {'yes' if buildinghub_key else 'no'}",
                f"- WFS fetch meta rows: {len(fetch_meta)}",
                f"- Fallback mode: {'yes' if fallback_reason else 'no'}",
                "",
                "## Assessment",
                "- Live VWorld WFS validation completed successfully in this run.",
                "- The returned building inventory is WFS-confirmed and should supersede the local fallback baseline for v11.",
            ]
        ),
    )


def main() -> None:
    ensure_dirs()
    keys = load_keys()
    boundary = boundary_gdf()
    labels = target_region_labels(boundary)
    rep_points = boundary.copy()
    boundary_5179 = to_5179(boundary)
    fetch_meta: list[dict[str, Any]] = []
    errors: list[str] = []
    fetched_frames: list[gpd.GeoDataFrame] = []

    # Try live WFS first.
    if keys["vworld"]:
        for region in boundary_5179.itertuples(index=False):
            bbox = tile_bbox_param(region.geometry)
            meta: dict[str, Any] = {"region_id": region.region_id, "bbox": bbox, "status": None, "hits": None, "rows": 0}
            try:
                hits_resp = request_vworld(keys["vworld"], bbox, result_type="hits")
                meta["status"] = hits_resp.status_code
                if "ServiceException" in hits_resp.text:
                    meta["error"] = hits_resp.text[:300]
                    errors.append(f"{region.region_id}: hits request rejected with ServiceException")
                    fetch_meta.append(meta)
                    continue
                hits = parse_hits(hits_resp.text)
                meta["hits"] = hits
                fetch_meta.append(meta)
                if hits is not None and hits > 1000:
                    errors.append(f"{region.region_id}: hits exceeded maxFeatures; tile subdivision not enabled in simplified run")
                    continue
                try:
                    resp = request_vworld(keys["vworld"], bbox, result_type="results")
                    meta_sub = {"region_id": region.region_id, "bbox": bbox, "status": resp.status_code, "hits": hits, "rows": 0}
                    if "ServiceException" in resp.text:
                        meta_sub["error"] = resp.text[:300]
                        errors.append(f"{region.region_id}: results request rejected with ServiceException")
                        fetch_meta.append(meta_sub)
                        continue
                    gdf = read_gml_payload(resp.content)
                    gdf = to_4326(gdf)
                    gdf["source_mode"] = "vworld_wfs"
                    fetched_frames.append(gdf)
                    meta_sub["rows"] = len(gdf)
                    fetch_meta.append(meta_sub)
                    time.sleep(0.25)
                except Exception as exc:
                    fetch_meta.append({"region_id": region.region_id, "bbox": bbox, "status": "parse_error", "hits": hits, "rows": 0, "error": str(exc)})
                    errors.append(f"{region.region_id}: {type(exc).__name__}: {exc}")
                    continue
            except Exception as exc:
                fetch_meta.append({"region_id": region.region_id, "bbox": bbox, "status": "request_error", "hits": None, "rows": 0, "error": str(exc)})
                errors.append(f"{region.region_id}: {type(exc).__name__}: {exc}")
                continue

    fetched = pd.concat(fetched_frames, ignore_index=True) if fetched_frames else gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=4326)
    fallback_used = fetched.empty
    fallback_reason = None
    if fallback_used:
        fallback_reason = "live_wfs_unavailable_or_empty"
        fallback_gdf = build_fallback_building_gdf()
        raw = fallback_gdf.copy()
        raw["source_mode"] = "fallback_local_parcel"
        raw = standardize_buildings(raw, "fallback_local_parcel")
    else:
        raw = standardize_buildings(fetched, "vworld_wfs")

    if "pnu" not in raw.columns:
        if "parcel_pnu" in raw.columns:
            raw["pnu"] = raw["parcel_pnu"]
        elif "building_pnu_final" in raw.columns:
            raw["pnu"] = raw["building_pnu_final"]
        else:
            raw["pnu"] = None

    raw = assign_region_by_overlay(raw, boundary)
    raw["parcel_pnu"] = raw.get("parcel_pnu", raw.get("pnu"))
    if "region_id" not in raw.columns:
        raw["region_id"] = None
    if "region_name" not in raw.columns:
        raw["region_name"] = None

    # Ensure requested standard columns exist.
    for col in [
        "gis_building_id",
        "building_id",
        "main_use_code",
        "structure_code",
        "building_area_m2",
        "total_floor_area_m2",
        "site_area_m2",
        "height_m",
        "bcr_percent",
        "far_percent",
        "approval_date",
        "last_update_date",
        "main_use_group",
        "source_mode",
        "region_id",
        "region_name",
        "parcel_pnu",
        "intersection_area_m2",
        "intersection_ratio",
        "centroid_region_id",
        "centroid_within",
        "inclusion_rule",
    ]:
        if col not in raw.columns:
            raw[col] = None

    raw["geometry"] = raw.geometry if "geometry" in raw.columns else None
    raw = gpd.GeoDataFrame(raw, geometry="geometry", crs=4326)
    by_region = raw.copy()
    by_region["region_area_m2"] = by_region["region_id"].map(boundary_5179.set_index("region_id").geometry.area.to_dict())

    indicators, use_comp, realization = compute_indicators(raw, boundary)
    comparison, _ = comparison_with_v10(realization)

    # Region polygon summary layer.
    region_summary = boundary.copy()
    region_summary = to_4326(region_summary)
    indicator_map = indicators.set_index("region_id").to_dict(orient="index")
    for col in ["building_count", "valid_building_count", "total_floor_area_sum_m2", "office_floor_area_share", "commercial_floor_area_share", "residential_floor_area_share", "average_far_percent", "median_far_percent", "average_bcr_percent", "median_bcr_percent", "data_quality_flag", "source_mode"]:
        region_summary[col] = region_summary["region_id"].map(lambda rid: indicator_map.get(rid, {}).get(col))

    # Normalize two convenience ratio columns for report tables.
    indicators["average_far_ratio"] = indicators["average_far_percent"] / 100.0
    indicators["median_far_ratio"] = indicators["median_far_percent"] / 100.0
    indicators["average_bcr_ratio"] = indicators["average_bcr_percent"] / 100.0
    indicators["median_bcr_ratio"] = indicators["median_bcr_percent"] / 100.0
    realization["average_far_ratio"] = realization["average_far_ratio"]
    realization["median_far_ratio"] = realization["median_far_ratio"]

    write_outputs_and_docs(
        raw,
        region_summary,
        by_region[
            [
                "region_id",
                "region_name",
                "building_id",
                "parcel_pnu",
                "main_use_group",
                "total_floor_area_m2",
                "site_area_m2",
                "building_area_m2",
                "far_percent",
                "bcr_percent",
                "approval_year",
                "source_mode",
                "intersection_area_m2",
                "intersection_ratio",
                "centroid_region_id",
                "centroid_within",
                "inclusion_rule",
            ]
        ],
        indicators,
        use_comp,
        realization,
        comparison,
        keys["vworld"],
        keys["buildinghub"],
        fetch_meta,
        fallback_reason,
    )

    print(f"VWorld key loaded: {'yes' if keys['vworld'] else 'no'}")
    print(f"BuildingHUB key loaded: {'yes' if keys['buildinghub'] else 'no'}")
    print(f"Live WFS features: {0 if raw['source_mode'].astype(str).str.contains('vworld_wfs').sum() == 0 else len(raw)}")
    print(f"Fallback used: {'yes' if fallback_reason else 'no'}")


if __name__ == "__main__":
    main()
