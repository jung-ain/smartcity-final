from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from pathlib import Path

import geopandas as gpd
import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(r"D:\smart_3\smartcity-final")
RAW = Path(r"D:\smart_3\data\raw")
PROC = ROOT / "data" / "processed" / "v11"
MAPS = ROOT / "outputs" / "maps"
INVENTORY = ROOT / "data" / "inventory"

SGIS_DIR = RAW / "_census_reqdoc_1781628003293"
GYEONGGI_LANDUSE = RAW / "토지이용계획도_경기_20260529_5186"
SEOUL_LANDUSE = RAW / "토지이용계획도_서울_20260529_5186"

BLOCK_SHP = {
    "11": RAW / "bnd_oa_11_2025_2Q" / "bnd_oa_11_2025_2Q.shp",
    "31": RAW / "bnd_oa_31_2025_2Q" / "bnd_oa_31_2025_2Q.shp",
}

POP_CSV_SUFFIX = "년_인구총괄(총인구).csv"
WORKER_CSV_SUFFIX = "년_산업분류별(10차_대분류)_총괄종사자수.csv"

CORE_BOUNDARIES = {
    "pangyo": ROOT / "data" / "processed" / "01_바운더리" / "10_과정" / "boundary_pangyo_core_draft_v1.geojson",
    "wirye": ROOT / "data" / "processed" / "01_바운더리" / "10_과정" / "boundary_wirye_core_draft_v1.geojson",
}

FULL_LANDUSE_FILTERS = {
    "pangyo": {
        "path": GYEONGGI_LANDUSE,
        "zone_name": "성남판교지구 택지개발사업",
    },
    "wirye": {
        "path": SEOUL_LANDUSE,
        "zone_name": "위례 택지개발사업 예정지구",
    },
}

REGION_NAMES = {
    "pangyo": "Pangyo",
    "wirye": "Wirye",
}

AREA_NAMES = {
    "core": "business",
    "full": "planning",
}

PALETTES = {
    "population_alloc": [
        (255, 247, 236),
        (253, 204, 138),
        (252, 141, 89),
        (227, 74, 51),
        (179, 0, 0),
    ],
    "worker_alloc": [
        (247, 252, 253),
        (199, 233, 192),
        (123, 204, 196),
        (67, 162, 202),
        (8, 81, 156),
    ],
}


def find_one(base: Path, pattern: str) -> Path:
    matches = list(base.rglob(pattern))
    if len(matches) != 1:
        raise FileNotFoundError(f"expected exactly one match for {pattern}, got {matches}")
    return matches[0]


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for font_path in [
        Path(r"C:\Windows\Fonts\malgun.ttf"),
        Path(r"C:\Windows\Fonts\malgunbd.ttf"),
        Path(r"C:\Windows\Fonts\arial.ttf"),
    ]:
        if font_path.exists():
            try:
                return ImageFont.truetype(str(font_path), size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def read_total_csv(path: Path, value_name: str) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="cp949", header=None, names=["base_date", "tot_oa_cd", "measure_code", value_name])
    df["tot_oa_cd"] = df["tot_oa_cd"].astype(str)
    return df.drop_duplicates("tot_oa_cd", keep="first")[["tot_oa_cd", value_name]]


def load_blocks() -> gpd.GeoDataFrame:
    frames = []
    for sigungu, shp in BLOCK_SHP.items():
        gdf = gpd.read_file(shp)
        gdf["tot_oa_cd"] = gdf["TOT_OA_CD"].astype(str)

        pop_csv = next(p for p in SGIS_DIR.iterdir() if p.suffix.lower() == ".csv" and p.name.startswith(f"{sigungu}_2023") and p.name.endswith(POP_CSV_SUFFIX))
        worker_csv = next(p for p in SGIS_DIR.iterdir() if p.suffix.lower() == ".csv" and p.name.startswith(f"{sigungu}_2023") and p.name.endswith(WORKER_CSV_SUFFIX))

        pop = read_total_csv(pop_csv, "population_total")
        workers = read_total_csv(worker_csv, "worker_total")
        gdf = gdf.merge(pop, on="tot_oa_cd", how="left").merge(workers, on="tot_oa_cd", how="left")
        frames.append(gdf[["tot_oa_cd", "population_total", "worker_total", "geometry"]])

    blocks = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), geometry="geometry")
    blocks["population_total"] = blocks["population_total"].fillna(0.0)
    blocks["worker_total"] = blocks["worker_total"].fillna(0.0)
    return blocks


def load_core_boundary(region: str) -> gpd.GeoDataFrame:
    return gpd.read_file(CORE_BOUNDARIES[region])


def load_full_boundary(region: str) -> gpd.GeoDataFrame:
    cfg = FULL_LANDUSE_FILTERS[region]
    shp = find_one(cfg["path"], "the_geom.shp")
    gdf = gpd.read_file(shp, encoding="cp949")
    zone_norm = gdf["zoneName"].astype(str).str.replace(" ", "", regex=False)
    target = cfg["zone_name"].replace(" ", "")
    selected = gdf.loc[zone_norm == target].copy()
    if selected.empty:
        raise ValueError(f"no rows matched full boundary filter for {region}: {cfg['zone_name']}")
    boundary = gpd.GeoDataFrame(geometry=[selected.geometry.union_all()], crs=gdf.crs)
    boundary["region_id"] = region
    boundary["area_type"] = "full"
    return boundary


def ensure_calculation_crs(blocks: gpd.GeoDataFrame, boundaries: dict[tuple[str, str], gpd.GeoDataFrame]) -> tuple[gpd.GeoDataFrame, dict[tuple[str, str], gpd.GeoDataFrame], str]:
    calc_crs = blocks.crs
    if calc_crs is None or calc_crs.is_geographic:
        calc_crs = "EPSG:5186"
    if blocks.crs != calc_crs:
        blocks = blocks.to_crs(calc_crs)
    converted: dict[tuple[str, str], gpd.GeoDataFrame] = {}
    for key, boundary in boundaries.items():
        converted[key] = boundary.to_crs(calc_crs) if boundary.crs != calc_crs else boundary.copy()
    return blocks, converted, str(calc_crs)


def split_blocks_by_boundary(blocks: gpd.GeoDataFrame, boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    boundary_geom = boundary.geometry.union_all()
    idx = list(blocks.sindex.query(boundary_geom, predicate="intersects"))
    if not idx:
        return gpd.GeoDataFrame(columns=[
            "region_id",
            "area_type",
            "tot_oa_cd",
            "population_total",
            "worker_total",
            "weight",
            "intersection_area_m2",
            "block_area_m2",
            "population_alloc",
            "worker_alloc",
            "population_density_alloc",
            "worker_density_alloc",
            "geometry",
        ], geometry="geometry", crs=blocks.crs)

    candidates = blocks.iloc[idx].copy()
    candidates["block_area_m2"] = candidates.geometry.area
    clip = gpd.GeoDataFrame(geometry=[boundary_geom], crs=blocks.crs)
    inter = gpd.overlay(candidates, clip, how="intersection")
    inter["intersection_area_m2"] = inter.geometry.area
    inter["weight"] = inter["intersection_area_m2"] / inter["block_area_m2"]
    inter["population_alloc"] = inter["population_total"] * inter["weight"]
    inter["worker_alloc"] = inter["worker_total"] * inter["weight"]
    inter["population_density_alloc"] = inter["population_alloc"] / inter["intersection_area_m2"] * 1_000_000
    inter["worker_density_alloc"] = inter["worker_alloc"] / inter["intersection_area_m2"] * 1_000_000
    return inter


def summarize(region: str, area_type: str, split: gpd.GeoDataFrame, boundary: gpd.GeoDataFrame) -> dict[str, float]:
    boundary_geom = boundary.geometry.union_all()
    boundary_area_m2 = float(boundary_geom.area)
    return {
        "region_id": region,
        "region_name": REGION_NAMES[region],
        "area_type": area_type,
        "boundary_area_m2": boundary_area_m2,
        "boundary_area_km2": boundary_area_m2 / 1_000_000.0,
        "split_polygons": int(len(split)),
        "source_blocks": int(split["tot_oa_cd"].nunique()) if len(split) else 0,
        "population_total": float(split["population_alloc"].sum()) if len(split) else 0.0,
        "worker_total": float(split["worker_alloc"].sum()) if len(split) else 0.0,
        "coverage_ratio": float(split["intersection_area_m2"].sum() / boundary_area_m2) if boundary_area_m2 and len(split) else 0.0,
    }


def palette_color(value: float, vmax: float, palette: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    if vmax <= 0:
        return palette[0]
    x = max(0.0, min(1.0, value / vmax))
    x = sqrt(x)
    seg = x * (len(palette) - 1)
    idx = min(int(seg), len(palette) - 2)
    t = seg - idx
    a = palette[idx]
    b = palette[idx + 1]
    return (
        int(round(a[0] + (b[0] - a[0]) * t)),
        int(round(a[1] + (b[1] - a[1]) * t)),
        int(round(a[2] + (b[2] - a[2]) * t)),
    )


def geometry_parts(geom):
    if geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    if geom.geom_type == "MultiPolygon":
        return list(geom.geoms)
    return []


def project_point(x: float, y: float, bounds: tuple[float, float, float, float], size: tuple[int, int], pad: int) -> tuple[int, int]:
    minx, miny, maxx, maxy = bounds
    w, h = size
    inner_w = w - pad * 2
    inner_h = h - pad * 2
    px = pad + (x - minx) / (maxx - minx) * inner_w if maxx > minx else pad + inner_w / 2
    py = pad + (maxy - y) / (maxy - miny) * inner_h if maxy > miny else pad + inner_h / 2
    return int(round(px)), int(round(py))


def draw_ring(draw: ImageDraw.ImageDraw, coords, bounds, size, pad, fill=None, outline=None, width: int = 1):
    pts = [project_point(c[0], c[1], bounds, size, pad) for c in coords]
    if len(pts) >= 3 and fill is not None:
        draw.polygon(pts, fill=fill, outline=outline)
    if outline is not None and len(pts) >= 2 and width > 1:
        draw.line(pts + [pts[0]], fill=outline, width=width)


def draw_geometry(draw: ImageDraw.ImageDraw, geom, bounds, size, pad, fill=None, outline=None, width: int = 1):
    for poly in geometry_parts(geom):
        draw_ring(draw, poly.exterior.coords, bounds, size, pad, fill=fill, outline=outline, width=width)
        for interior in poly.interiors:
            draw_ring(draw, interior.coords, bounds, size, pad, fill=(255, 255, 255), outline=outline, width=width)


def render_map(
    split: gpd.GeoDataFrame,
    boundary: gpd.GeoDataFrame,
    region: str,
    area_type: str,
    metric: str,
    out_path: Path,
) -> None:
    width, height = 1800, 1800
    pad = 70
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    title_font = load_font(40)
    body_font = load_font(20)
    small_font = load_font(16)

    boundary_geom = boundary.geometry.union_all()
    minx, miny, maxx, maxy = boundary_geom.bounds
    dx = maxx - minx
    dy = maxy - miny
    bounds = (minx - dx * 0.02, miny - dy * 0.02, maxx + dx * 0.02, maxy + dy * 0.02)

    area_label = "Business district" if area_type == "core" else "Planning area"
    metric_label = "Population" if metric == "population_alloc" else "Workers"
    title = f"{REGION_NAMES[region]} {area_label} {metric_label} heatmap"

    draw.text((40, 24), title, fill=(20, 20, 20), font=title_font)
    draw.text((40, 76), "Zoomed crop with thick black boundary outline.", fill=(70, 70, 70), font=body_font)

    palette = PALETTES[metric]
    vmax = float(split[metric].quantile(0.98)) if len(split) else 1.0
    if vmax <= 0:
        vmax = float(split[metric].max()) if len(split) else 1.0

    for _, row in split.iterrows():
        fill = palette_color(float(row[metric]), vmax, palette)
        draw_geometry(draw, row.geometry, bounds, (width, height), pad, fill=fill, outline=(235, 235, 235), width=1)

    for _, row in split.iterrows():
        draw_geometry(draw, row.geometry, bounds, (width, height), pad, fill=None, outline=(180, 180, 180), width=1)

    for geom in boundary.geometry:
        draw_geometry(draw, geom, bounds, (width, height), pad, fill=None, outline=(0, 0, 0), width=8)

    bar_x = width - 150
    bar_y = 180
    bar_w = 28
    bar_h = 520
    for i in range(bar_h):
        ratio = 1 - i / max(bar_h - 1, 1)
        draw.line([(bar_x, bar_y + i), (bar_x + bar_w, bar_y + i)], fill=palette_color(ratio * vmax, vmax, palette), width=1)
    draw.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], outline=(70, 70, 70), width=1)
    draw.text((bar_x - 8, bar_y - 30), metric, fill=(30, 30, 30), font=body_font, anchor="ra")
    draw.text((bar_x + bar_w + 10, bar_y - 2), f"{vmax:,.0f}", fill=(30, 30, 30), font=small_font)
    draw.text((bar_x + bar_w + 10, bar_y + bar_h - 14), "0", fill=(30, 30, 30), font=small_font)

    draw.text(
        (40, height - 42),
        f"boundary crop; polygons={len(split)}; source blocks={split['tot_oa_cd'].nunique()}",
        fill=(70, 70, 70),
        font=small_font,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)


@dataclass
class Result:
    region_id: str
    area_type: str
    boundary: gpd.GeoDataFrame
    split: gpd.GeoDataFrame
    summary: dict[str, float]


def main() -> None:
    blocks = load_blocks()
    boundaries = {
        ("pangyo", "core"): load_core_boundary("pangyo"),
        ("wirye", "core"): load_core_boundary("wirye"),
        ("pangyo", "full"): load_full_boundary("pangyo"),
        ("wirye", "full"): load_full_boundary("wirye"),
    }

    blocks, boundaries, calc_crs = ensure_calculation_crs(blocks, boundaries)

    results: list[Result] = []
    split_rows = []
    boundary_rows = []

    for (region, area_type), boundary in boundaries.items():
        split = split_blocks_by_boundary(blocks, boundary)
        summary = summarize(region, area_type, split, boundary)
        results.append(Result(region, area_type, boundary, split, summary))

        boundary_geom = boundary.geometry.union_all()
        boundary_rows.append({
            "region_id": region,
            "area_type": area_type,
            "boundary_area_m2": float(boundary_geom.area),
            "boundary_area_km2": float(boundary_geom.area) / 1_000_000.0,
            "calc_crs": calc_crs,
        })

        for _, row in split.iterrows():
            split_rows.append({
                "region_id": region,
                "area_type": area_type,
                "tot_oa_cd": row["tot_oa_cd"],
                "population_alloc": float(row["population_alloc"]),
                "worker_alloc": float(row["worker_alloc"]),
                "weight": float(row["weight"]),
                "intersection_area_m2": float(row["intersection_area_m2"]),
                "block_area_m2": float(row["block_area_m2"]),
            })

    PROC.mkdir(parents=True, exist_ok=True)
    MAPS.mkdir(parents=True, exist_ok=True)
    INVENTORY.mkdir(parents=True, exist_ok=True)

    summary_df = pd.DataFrame([r.summary for r in results]).sort_values(["region_id", "area_type"])
    summary_csv = PROC / "planning_boundary_population_workers_area_v2.csv"
    summary_df.to_csv(summary_csv, index=False, encoding="utf-8-sig")

    split_df = pd.DataFrame(split_rows)
    split_csv = PROC / "planning_boundary_population_workers_area_split_v2.csv"
    split_df.to_csv(split_csv, index=False, encoding="utf-8-sig")

    boundary_df = pd.DataFrame(boundary_rows)
    boundary_csv = PROC / "planning_boundary_population_workers_area_boundary_v2.csv"
    boundary_df.to_csv(boundary_csv, index=False, encoding="utf-8-sig")

    split_geojson = gpd.GeoDataFrame(
        pd.concat(
            [
                r.split.assign(region_id=r.region_id, area_type=r.area_type)[
                    [
                        "region_id",
                        "area_type",
                        "tot_oa_cd",
                        "population_alloc",
                        "worker_alloc",
                        "weight",
                        "intersection_area_m2",
                        "block_area_m2",
                        "geometry",
                    ]
                ]
                for r in results
            ],
            ignore_index=True,
        ),
        geometry="geometry",
        crs=blocks.crs,
    ).to_crs(4326)
    split_geojson_path = PROC / "planning_boundary_population_workers_area_split_v2.geojson"
    split_geojson.to_file(split_geojson_path, driver="GeoJSON")

    for r in results:
        for metric in ["population_alloc", "worker_alloc"]:
            out_name = f"{r.region_id}_{AREA_NAMES[r.area_type]}_{'population' if metric == 'population_alloc' else 'worker'}_heatmap_v2.png"
            render_map(
                r.split,
                r.boundary,
                r.region_id,
                r.area_type,
                metric,
                MAPS / out_name,
            )

    old_core_csv = ROOT / "data" / "processed" / "v10" / "planning_boundary_population_workers_v1.csv"
    old_core = pd.read_csv(old_core_csv)
    compare_rows = []
    for region in ["pangyo", "wirye"]:
        new_core = summary_df[(summary_df["region_id"] == region) & (summary_df["area_type"] == "core")].iloc[0]
        new_full = summary_df[(summary_df["region_id"] == region) & (summary_df["area_type"] == "full")].iloc[0]
        old = old_core[old_core["region_id"] == region].iloc[0]
        compare_rows.append({
            "region_id": region,
            "old_population_total": float(old["population_total"]),
            "old_worker_total": float(old["worker_total"]),
            "new_core_population_total": float(new_core["population_total"]),
            "new_core_worker_total": float(new_core["worker_total"]),
            "new_full_population_total": float(new_full["population_total"]),
            "new_full_worker_total": float(new_full["worker_total"]),
            "full_minus_core_population": float(new_full["population_total"] - new_core["population_total"]),
            "full_minus_core_worker": float(new_full["worker_total"] - new_core["worker_total"]),
            "full_over_core_population_ratio": float(new_full["population_total"] / new_core["population_total"]) if new_core["population_total"] else None,
            "full_over_core_worker_ratio": float(new_full["worker_total"] / new_core["worker_total"]) if new_core["worker_total"] else None,
            "old_minus_new_core_population": float(old["population_total"] - new_core["population_total"]),
            "old_minus_new_core_worker": float(old["worker_total"] - new_core["worker_total"]),
        })

    compare_df = pd.DataFrame(compare_rows)
    compare_csv = PROC / "planning_boundary_population_workers_area_compare_v2.csv"
    compare_df.to_csv(compare_csv, index=False, encoding="utf-8-sig")

    md_lines = [
        "# Planning boundary population-worker recalculation v2",
        "",
        "- Scope: business district vs full planning area for Pangyo and Wirye.",
        "- Full planning areas were extracted from land-use planning maps using exact zone names:",
        "  - Pangyo: `성남판교지구 택지개발사업`",
        "  - Wirye: `위례 택지개발사업 예정지구`",
        "- Allocation method: SGIS census blocks were intersected with each boundary and population/workers were assigned by intersection area ratio.",
        "",
        "## Summary",
        "",
        summary_df.to_string(index=False),
        "",
        "## Comparison vs previous data",
        "",
        compare_df.to_string(index=False),
        "",
        "## Outputs",
        "",
        f"- summary csv: `{summary_csv}`",
        f"- split csv: `{split_csv}`",
        f"- boundary csv: `{boundary_csv}`",
        f"- split geojson: `{split_geojson_path}`",
        f"- compare csv: `{compare_csv}`",
    ]
    INVENTORY.mkdir(parents=True, exist_ok=True)
    (INVENTORY / "planning_boundary_population_workers_area_v2.md").write_text("\n".join(md_lines), encoding="utf-8")

    print(summary_csv)
    print(split_csv)
    print(boundary_csv)
    print(split_geojson_path)
    print(compare_csv)


if __name__ == "__main__":
    main()
