from __future__ import annotations

import json
import shutil
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = ROOT / "frontend" / "public" / "data"
FRONTEND_DST = ROOT / "frontend2" / "public" / "data"
REGISTER_SRC = ROOT / "data" / "processed" / "v12" / "vworld_register_join_feature_level_v12.geojson"
STATION_SRC = ROOT / "frontend" / "public" / "data" / "final_subway_reachable_stations_v15.geojson"

RAW_BUILDING_SOURCES = [
    ROOT.parent / "data" / "raw" / "AL_D162_11_20240211" / "AL_D162_11_20240211.shp",
    ROOT.parent / "data" / "raw" / "AL_D162_41_20240211" / "AL_D162_41_20240211.shp",
    ROOT.parent / "data" / "raw" / "AL_D164_11_20240211" / "AL_D164_11_20240211.shp",
    ROOT.parent / "data" / "raw" / "AL_D164_41_20240211" / "AL_D164_41_20240211.shp",
]

STATIC_FILES = [
    "boundaries_core_comparison_v2.geojson",
    "boundaries_analysis_v2.geojson",
    "full_boundary_v25.geojson",
    "map_full_planning_landuse_pangyo_v24.geojson",
    "map_full_planning_landuse_wirye_v24.geojson",
    "final_landuse_scope_boundaries_v16.geojson",
    "pangyo_bokjeong_mode_isochrones_v30.geojson",
    "pangyo_bokjeong_mode_accessibility_summary_v30.json",
    "pangyo_bokjeong_mode_accessibility_curve_v30.json",
    "sgis_core_key_indicators_v2.json",
    "sgis_analysis_key_indicators_v2.json",
    "sgis_industry_summary_v2.json",
]

REGION_SPECS = {
    "pangyo": {
        "label": "판교",
        "station_label": "판교역",
        "station_short": "판교",
        "region_ids": {"pangyo_core", "pangyo_station_support_zone"},
        "core_region_id": "pangyo_core",
    },
    "wirye": {
        "label": "위례",
        "station_label": "복정역",
        "station_short": "복정",
        "region_ids": {"wirye_core", "wirye_station_support_zone"},
        "core_region_id": "wirye_core",
    },
}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def copy_static_files() -> None:
    ensure_dir(FRONTEND_DST)
    for name in STATIC_FILES:
        src = FRONTEND_SRC / name
        dst = FRONTEND_DST / name
        if src.exists():
            shutil.copy2(src, dst)


def decode_text(value: object) -> object:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, str):
        try:
            return value.encode("latin1").decode("cp949")
        except Exception:
            return value
    return value


def decode_frame_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    result = df.copy()
    for column in columns:
        if column in result.columns:
            result[column] = result[column].map(decode_text)
    return result


def as_feature_collection(value: object) -> dict[str, object]:
    if isinstance(value, dict) and value.get("type") == "FeatureCollection" and isinstance(value.get("features"), list):
        return value
    return {"type": "FeatureCollection", "features": []}


def normalize_scope_scope(region_id: str) -> str:
    if region_id in {"pangyo_core", "pangyo_station_support_zone"}:
        return "pangyo"
    if region_id in {"wirye_core", "wirye_station_support_zone"}:
        return "wirye"
    return "unknown"


def use_group(raw_use: object) -> str:
    text = str(decode_text(raw_use) or "").strip()
    if not text or text == "nan":
        return "기타"

    mapping = [
        ("업무", "업무"),
        ("사무", "업무"),
        ("상업", "상업"),
        ("판매", "상업"),
        ("근린생활", "생활서비스"),
        ("주택", "주거"),
        ("아파트", "주거"),
        ("연립", "주거"),
        ("다세대", "주거"),
        ("공동주택", "주거"),
        ("교육", "교육"),
        ("문화", "공공"),
        ("공공", "공공"),
        ("의료", "공공"),
        ("종교", "공공"),
        ("숙박", "상업"),
        ("운동", "공공"),
        ("공장", "산업·물류"),
        ("창고", "산업·물류"),
        ("운수", "산업·물류"),
        ("자동차", "산업·물류"),
        ("농업", "기타"),
    ]
    for needle, group in mapping:
        if needle in text:
            return group
    return "기타"


def format_year(value: object) -> int | None:
    text = str(value or "").strip()
    if not text or text == "nan":
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 4:
        try:
            return int(digits[:4])
        except Exception:
            return None
    return None


def summarize_raw_buildings(raw_df: pd.DataFrame, register_df: gpd.GeoDataFrame) -> list[dict[str, object]]:
    merged = register_df[["region_id", "region_name", "parcel_pnu", "pnu"]].copy()
    merged["parcel_pnu"] = merged["parcel_pnu"].astype(str)
    merged["pnu"] = merged["pnu"].astype(str)

    raw = raw_df.copy()
    raw["pnu"] = raw["A1"].astype(str)
    raw["main_use_group"] = raw["A30"].map(use_group)
    raw["main_use_text"] = raw["A30"].map(decode_text)
    raw["site_area_m2"] = pd.to_numeric(raw["A22"], errors="coerce")
    raw["building_area_m2"] = pd.to_numeric(raw["A23"], errors="coerce")
    raw["total_floor_area_m2"] = pd.to_numeric(raw["A24"], errors="coerce")
    raw["far_floor_area_m2"] = pd.to_numeric(raw["A25"], errors="coerce")
    raw["floor_count"] = pd.to_numeric(raw["A27"], errors="coerce")
    raw["approval_year"] = raw["A35"].map(format_year)
    raw["structure_text"] = raw["A28"].map(decode_text)

    joined = merged.merge(raw, on="pnu", how="left")
    joined["region_group"] = joined["region_id"].map(normalize_scope_scope)

    summaries: list[dict[str, object]] = []
    for region_key in ("pangyo", "wirye"):
        region_ids = REGION_SPECS[region_key]["region_ids"]
        for scope, scope_filter in (("full", region_ids), ("core", {REGION_SPECS[region_key]["core_region_id"]})):
            subset = joined[joined["region_id"].isin(scope_filter)].copy()
            if subset.empty:
                summaries.append(
                    {
                        "region_group": f"{region_key}_{scope}",
                        "region_id": region_key,
                        "scope": scope,
                        "record_count": 0,
                        "unique_pnu_count": 0,
                        "total_floor_area_m2": 0.0,
                        "site_area_m2": 0.0,
                        "building_area_m2": 0.0,
                        "floor_count_median": None,
                        "approval_year_median": None,
                        "use_rows": [],
                        "use_rows_by_count": [],
                    }
                )
                continue

            subset["effective_floor_area_m2"] = subset["total_floor_area_m2"].fillna(subset["far_floor_area_m2"]).fillna(subset["building_area_m2"]).fillna(0)
            subset["effective_site_area_m2"] = subset["site_area_m2"].fillna(0)
            subset["effective_building_area_m2"] = subset["building_area_m2"].fillna(0)

            grouped = (
                subset.groupby("main_use_group", dropna=False)
                .agg(
                    record_count=("main_use_group", "size"),
                    unique_pnu_count=("pnu", "nunique"),
                    total_floor_area_m2=("effective_floor_area_m2", "sum"),
                    site_area_m2=("effective_site_area_m2", "sum"),
                    building_area_m2=("effective_building_area_m2", "sum"),
                )
                .sort_values("total_floor_area_m2", ascending=False)
            )
            total_floor = float(grouped["total_floor_area_m2"].sum()) or 1.0
            total_count = float(grouped["record_count"].sum()) or 1.0
            use_rows = [
                {
                    "main_use_group": str(index),
                    "record_count": int(row.record_count),
                    "unique_pnu_count": int(row.unique_pnu_count),
                    "total_floor_area_m2": float(row.total_floor_area_m2),
                    "share_floor_area": float(row.total_floor_area_m2 / total_floor),
                    "share_count": float(row.record_count / total_count),
                }
                for index, row in grouped.head(8).iterrows()
            ]

            count_grouped = (
                subset.groupby("main_use_group", dropna=False)
                .size()
                .sort_values(ascending=False)
            )
            use_rows_by_count = [
                {
                    "main_use_group": str(index),
                    "record_count": int(value),
                    "share_count": float(value / total_count),
                }
                for index, value in count_grouped.head(8).items()
            ]

            summaries.append(
                {
                    "region_group": f"{region_key}_{scope}",
                    "region_id": region_key,
                    "scope": scope,
                    "record_count": int(len(subset)),
                    "unique_pnu_count": int(subset["pnu"].nunique()),
                    "total_floor_area_m2": float(subset["effective_floor_area_m2"].sum()),
                    "site_area_m2": float(subset["effective_site_area_m2"].sum()),
                    "building_area_m2": float(subset["effective_building_area_m2"].sum()),
                    "floor_count_median": float(pd.to_numeric(subset["floor_count"], errors="coerce").median()) if subset["floor_count"].notna().any() else None,
                    "approval_year_median": float(pd.to_numeric(subset["approval_year"], errors="coerce").median()) if subset["approval_year"].notna().any() else None,
                    "use_rows": use_rows,
                    "use_rows_by_count": use_rows_by_count,
                }
            )

    return summaries


def write_geojson(path: Path, gdf: gpd.GeoDataFrame) -> None:
    ensure_dir(path.parent)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()
    gdf.to_file(tmp_path, driver="GeoJSON")
    if path.exists():
        path.unlink()
    tmp_path.replace(path)


def pick_station_markers() -> gpd.GeoDataFrame:
    station = gpd.read_file(STATION_SRC)
    station = station[station["threshold_min"].eq(30)].copy()
    if station.empty:
        return station
    station["station_name"] = station["station_name"].map(decode_text)
    station["region_name"] = station["region_name"].map(decode_text)
    station["marker_region"] = station["station_name"].map({"판교역": "pangyo", "복정역": "wirye"}).fillna("pangyo")
    station["marker_label"] = station["station_name"]
    station = station[station["station_name"].isin(["판교역", "복정역"])].copy()
    station = station.sort_values(["marker_region", "station_name"]).drop_duplicates(subset=["station_name"], keep="first")
    return station[["marker_region", "marker_label", "station_name", "region_id", "region_name", "geometry"]].copy()


def main() -> None:
    ensure_dir(FRONTEND_DST)
    copy_static_files()

    register = gpd.read_file(REGISTER_SRC)
    register = register[register["region_id"].isin({"pangyo_core", "pangyo_station_support_zone", "wirye_core", "wirye_station_support_zone"})].copy()
    register["parcel_pnu"] = register["parcel_pnu"].astype(str)
    register["pnu"] = register["pnu"].astype(str)

    # Filter to the four target raw sources and summarize building usage directly from them.
    raw_frames = []
    for source in RAW_BUILDING_SOURCES:
        frame = gpd.read_file(source)
        keep = frame[[col for col in frame.columns if col.startswith("A")]].copy()
        raw_frames.append(keep)
    raw_df = pd.concat(raw_frames, ignore_index=True)
    raw_df = decode_frame_columns(raw_df, ["A0", "A1", "A2", "A3", "A5", "A9", "A11", "A21", "A28", "A29", "A30", "A34", "A35", "A38"])

    # Keep the existing feature-level joins for click interactions and geometry.
    register["region_group"] = register["region_id"].map(normalize_scope_scope)
    register["building_label"] = register["buld_nm"].fillna(register["dong_nm"]).fillna(register["parcel_pnu"]).fillna(register["gis_building_id"])

    for column in ["main_use_group", "main_use_text", "approval_year", "approval_date", "total_floor_area_m2", "site_area_m2", "building_area_m2", "far_percent", "bcr_percent", "ground_floor_co", "undgrnd_floor_co", "match_method", "match_strength", "source_mode"]:
        if column in register.columns:
            register[column] = register[column].map(decode_text) if register[column].dtype == object else register[column]

    register["main_use_group"] = register["main_use_group"].map(decode_text)
    register["main_use_text"] = register["main_use_text"].map(decode_text)
    register["buld_nm"] = register["buld_nm"].map(decode_text)
    register["dong_nm"] = register["dong_nm"].map(decode_text)

    summary_rows = []
    for region_key in ("pangyo", "wirye"):
        region_ids = REGION_SPECS[region_key]["region_ids"]
        region_all = register[register["region_id"].isin(region_ids)].copy()
        region_core = register[register["region_id"].eq(REGION_SPECS[region_key]["core_region_id"])].copy()

        def summarize(gdf: gpd.GeoDataFrame, label: str) -> dict[str, object]:
            if gdf.empty:
                return {
                    "region_group": label,
                    "building_count": 0,
                    "core_count": 0,
                    "support_count": 0,
                    "total_floor_area_m2": 0.0,
                    "average_far_percent": None,
                    "average_bcr_percent": None,
                    "weighted_far_percent": None,
                    "weighted_bcr_percent": None,
                    "zero_far_rate": None,
                    "zero_bcr_rate": None,
                    "zero_site_area_rate": None,
                    "approval_year_median": None,
                    "top_uses": [],
                }
            total_floor = pd.to_numeric(gdf["total_floor_area_m2"], errors="coerce").fillna(0)
            site_area = pd.to_numeric(gdf["site_area_m2"], errors="coerce")
            building_area = pd.to_numeric(gdf["building_area_m2"], errors="coerce")
            far_vals = pd.to_numeric(gdf["far_percent"], errors="coerce")
            bcr_vals = pd.to_numeric(gdf["bcr_percent"], errors="coerce")
            valid_site = site_area.notna() & site_area.gt(0)
            weighted_far = float(total_floor[valid_site].sum() / site_area[valid_site].sum() * 100) if valid_site.any() else None
            weighted_bcr = float(building_area[valid_site].fillna(0).sum() / site_area[valid_site].sum() * 100) if valid_site.any() else None
            use_floor = (
                gdf.assign(total_floor_area_m2=total_floor)
                .groupby("main_use_group", dropna=False)["total_floor_area_m2"]
                .sum()
                .sort_values(ascending=False)
            )
            return {
                "region_group": label,
                "building_count": int(len(gdf)),
                "core_count": int((gdf["region_id"] == REGION_SPECS[region_key]["core_region_id"]).sum()),
                "support_count": int(gdf["region_id"].astype(str).str.contains("support").sum()),
                "total_floor_area_m2": float(total_floor.sum()),
                "average_far_percent": float(pd.to_numeric(gdf["far_percent"], errors="coerce").mean()),
                "average_bcr_percent": float(pd.to_numeric(gdf["bcr_percent"], errors="coerce").mean()),
                "weighted_far_percent": weighted_far,
                "weighted_bcr_percent": weighted_bcr,
                "zero_far_rate": float((far_vals.fillna(0) <= 0).mean()),
                "zero_bcr_rate": float((bcr_vals.fillna(0) <= 0).mean()),
                "zero_site_area_rate": float((site_area.fillna(0) <= 0).mean()),
                "approval_year_median": float(pd.to_numeric(gdf["approval_year"], errors="coerce").median()),
                "top_uses": [
                    {
                        "main_use_group": str(name),
                        "floor_area_m2": float(value),
                        "share": float(value / total_floor.sum()) if total_floor.sum() else None,
                    }
                    for name, value in use_floor.head(6).items()
                ],
            }

        summary_rows.append(summarize(region_all, f"{region_key}_full"))
        summary_rows.append(summarize(region_core, f"{region_key}_core"))

        write_geojson(FRONTEND_DST / f"buildings_full_{region_key}_v35.geojson", region_all)
        write_geojson(FRONTEND_DST / f"buildings_core_{region_key}_v35.geojson", region_core)

    (FRONTEND_DST / "buildings_summary_v35.json").write_text(
        json.dumps(summary_rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    pd.DataFrame(summary_rows).to_csv(FRONTEND_DST / "buildings_summary_v35.csv", index=False, encoding="utf-8-sig")

    gis_summary_rows = summarize_raw_buildings(raw_df, register)
    (FRONTEND_DST / "buildings_gis_summary_v35.json").write_text(
        json.dumps({"version": "v35", "source": "raw AL_D162 / AL_D164", "rows": gis_summary_rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    station = pick_station_markers()
    if not station.empty:
        write_geojson(FRONTEND_DST / "station_markers_v35.geojson", station)

    manifest = {
        "files": [
            "buildings_full_pangyo_v35.geojson",
            "buildings_full_wirye_v35.geojson",
            "buildings_core_pangyo_v35.geojson",
            "buildings_core_wirye_v35.geojson",
            "buildings_summary_v35.json",
            "buildings_summary_v35.csv",
            "buildings_gis_summary_v35.json",
            "station_markers_v35.geojson",
            *STATIC_FILES,
        ]
    }
    (FRONTEND_DST / "manifest_v35.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
