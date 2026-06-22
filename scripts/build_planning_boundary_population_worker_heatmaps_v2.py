from __future__ import annotations

from math import sqrt
from pathlib import Path
from typing import Iterable

import geopandas as gpd
import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(r"D:\smart_3\smartcity-final")
RAW = ROOT / "data" / "raw" / "04_sgis"
PROC = ROOT / "data" / "processed"
MAPS = ROOT / "outputs" / "maps"
INVENTORY = ROOT / "data" / "inventory"

OUT_CSV = PROC / "v10" / "planning_boundary_population_workers_split_v1.csv"
OUT_GEOJSON = PROC / "v10" / "planning_boundary_population_workers_split_v1.geojson"
OUT_MD = INVENTORY / "planning_boundary_population_worker_heatmap_v1.md"
OUT_COMBINED = MAPS / "planning_boundary_population_workers_heatmap_v1.png"

REGION_LABELS = {
    "pangyo": "판교",
    "wirye": "위례",
}

POP_PALETTE = [
    (255, 247, 236),
    (253, 204, 138),
    (252, 141, 89),
    (227, 74, 51),
    (179, 0, 0),
]

WORKER_PALETTE = [
    (247, 252, 253),
    (199, 233, 192),
    (123, 204, 196),
    (67, 162, 202),
    (8, 81, 156),
]


def find_one(base: Path, pattern: str) -> Path:
    matches = list(base.rglob(pattern))
    if len(matches) != 1:
        raise FileNotFoundError(f"expected exactly one match for {pattern}, got {matches}")
    return matches[0]


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for font_path in [
        Path(r"C:\Windows\Fonts\malgun.ttf"),
        Path(r"C:\Windows\Fonts\malgunbd.ttf"),
        Path(r"C:\Windows\Fonts\gulim.ttc"),
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
    census_dir = RAW / "_census_reqdoc_1781628003293"
    for sigungu in ["11", "31"]:
        shp = find_one(RAW, f"bnd_oa_{sigungu}_2025_2Q.shp")
        gdf = gpd.read_file(shp)
        gdf["tot_oa_cd"] = gdf["TOT_OA_CD"].astype(str)

        pop_csv = next(
            p for p in census_dir.iterdir()
            if p.suffix.lower() == ".csv" and p.name.startswith(f"{sigungu}_2023") and "인구총괄(총인구)" in p.name
        )
        workers_csv = next(
            p for p in census_dir.iterdir()
            if p.suffix.lower() == ".csv" and p.name.startswith(f"{sigungu}_2023") and "산업분류별(10차_대분류)_총괄종사자수" in p.name
        )

        pop = read_total_csv(pop_csv, "population_total")
        workers = read_total_csv(workers_csv, "worker_total")
        gdf = gdf.merge(pop, on="tot_oa_cd", how="left").merge(workers, on="tot_oa_cd", how="left")
        frames.append(gdf[["tot_oa_cd", "population_total", "worker_total", "geometry"]])

    blocks = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), geometry="geometry")
    blocks["population_total"] = blocks["population_total"].fillna(0.0)
    blocks["worker_total"] = blocks["worker_total"].fillna(0.0)
    return blocks


def load_boundary(region: str) -> gpd.GeoDataFrame:
    return gpd.read_file(find_one(PROC, f"boundary_{region}_draft_v1.geojson"))


def split_blocks_by_boundary(blocks: gpd.GeoDataFrame, boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if blocks.crs != boundary.crs:
        boundary = boundary.to_crs(blocks.crs)
    boundary_geom = boundary.geometry.union_all()
    candidate_idx = list(blocks.sindex.query(boundary_geom, predicate="intersects"))
    candidates = blocks.iloc[candidate_idx].copy()
    candidates["block_area_m2"] = candidates.geometry.area

    inter = gpd.overlay(candidates, gpd.GeoDataFrame(geometry=[boundary_geom], crs=blocks.crs), how="intersection")
    inter["intersection_area_m2"] = inter.geometry.area
    inter["weight"] = inter["intersection_area_m2"] / inter["block_area_m2"]
    inter["population_alloc"] = inter["population_total"] * inter["weight"]
    inter["worker_alloc"] = inter["worker_total"] * inter["weight"]
    inter["population_density_alloc"] = inter["population_alloc"] / inter["intersection_area_m2"] * 1_000_000
    inter["worker_density_alloc"] = inter["worker_alloc"] / inter["intersection_area_m2"] * 1_000_000
    return inter


def summarize(region: str, split: gpd.GeoDataFrame, boundary: gpd.GeoDataFrame) -> dict[str, float]:
    boundary_geom = boundary.geometry.union_all()
    boundary_area_m2 = float(boundary.iloc[0]["area_m2"]) if "area_m2" in boundary.columns else float(boundary_geom.area)
    return {
        "region_id": region,
        "boundary_area_m2": boundary_area_m2,
        "split_polygons": int(len(split)),
        "source_blocks": int(split["tot_oa_cd"].nunique()),
        "population_total": float(split["population_alloc"].sum()),
        "worker_total": float(split["worker_alloc"].sum()),
        "coverage_ratio": float(split["intersection_area_m2"].sum() / boundary_area_m2) if boundary_area_m2 else 0.0,
    }


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def lerp(a: int, b: int, t: float) -> int:
    return int(round(a + (b - a) * t))


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
    return (lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t))


def geometry_parts(geom) -> Iterable:
    if geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    if geom.geom_type == "MultiPolygon":
        return list(geom.geoms)
    return []


def map_bounds(split: gpd.GeoDataFrame, boundary: gpd.GeoDataFrame) -> tuple[float, float, float, float]:
    minx1, miny1, maxx1, maxy1 = split.total_bounds
    minx2, miny2, maxx2, maxy2 = boundary.total_bounds
    minx = min(minx1, minx2)
    miny = min(miny1, miny2)
    maxx = max(maxx1, maxx2)
    maxy = max(maxy1, maxy2)
    dx = maxx - minx
    dy = maxy - miny
    pad_x = dx * 0.05 if dx else 1.0
    pad_y = dy * 0.05 if dy else 1.0
    return minx - pad_x, miny - pad_y, maxx + pad_x, maxy + pad_y


def to_px(x: float, y: float, bounds: tuple[float, float, float, float], size: tuple[int, int], pad: int) -> tuple[int, int]:
    minx, miny, maxx, maxy = bounds
    w, h = size
    inner_w = w - pad * 2
    inner_h = h - pad * 2
    px = pad + (x - minx) / (maxx - minx) * inner_w if maxx > minx else pad + inner_w / 2
    py = pad + (maxy - y) / (maxy - miny) * inner_h if maxy > miny else pad + inner_h / 2
    return int(round(px)), int(round(py))


def draw_geom(draw: ImageDraw.ImageDraw, geom, bounds, size, fill, outline, width: int = 1):
    for poly in geometry_parts(geom):
        exterior = [to_px(x, y, bounds, size, pad=70) for x, y in poly.exterior.coords]
        if len(exterior) >= 3:
            draw.polygon(exterior, fill=fill, outline=outline)
        if width > 1:
            draw.line(exterior + [exterior[0]], fill=outline, width=width)
        for interior in poly.interiors:
            ring = [to_px(x, y, bounds, size, pad=70) for x, y in interior.coords]
            if len(ring) >= 3:
                draw.polygon(ring, fill=(255, 255, 255), outline=outline)


def draw_colorbar(draw: ImageDraw.ImageDraw, x0: int, y0: int, width: int, height: int, vmax: float, palette, label: str, font, small_font):
    steps = height
    for i in range(steps):
        ratio = 1 - i / max(steps - 1, 1)
        color = palette_color(ratio * vmax, vmax, palette)
        draw.line([(x0, y0 + i), (x0 + width, y0 + i)], fill=color, width=1)
    draw.rectangle([x0, y0, x0 + width, y0 + height], outline=(80, 80, 80), width=1)
    draw.text((x0, y0 - 24), label, fill=(30, 30, 30), font=font)
    draw.text((x0 + width + 8, y0 - 2), f"{vmax:,.0f}", fill=(30, 30, 30), font=small_font)
    draw.text((x0 + width + 8, y0 + height - 14), "0", fill=(30, 30, 30), font=small_font)


def render_panel(region: str, metric: str, title: str, split: gpd.GeoDataFrame, boundary: gpd.GeoDataFrame, palette, metric_label: str) -> Image.Image:
    width, height = 1100, 980
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    title_font = load_font(30)
    body_font = load_font(20)
    small_font = load_font(16)

    bounds = map_bounds(split, boundary)

    draw.text((40, 24), title, fill=(20, 20, 20), font=title_font)
    summary = f"집계구 조각 수 {len(split)}개  ·  원 집계구 {split['tot_oa_cd'].nunique()}개  ·  면적가중 배분"
    draw.text((40, 64), summary, fill=(70, 70, 70), font=body_font)

    # Draw clipped blocks and boundary.
    for _, row in split.iterrows():
        color = palette_color(float(row[metric]), float(split[metric].quantile(0.98)) or 1.0, palette)
        draw_geom(draw, row.geometry, bounds, (width, height), fill=color, outline=(255, 255, 255), width=1)

    # Census block borders are already represented by the clipped pieces; reinforce with light edges.
    for _, row in split.iterrows():
        draw_geom(draw, row.geometry, bounds, (width, height), fill=None, outline=(180, 180, 180), width=1)

    # Boundary outline on top.
    for geom in boundary.geometry:
        draw_geom(draw, geom, bounds, (width, height), fill=None, outline=(0, 0, 0), width=3)

    vmax = float(split[metric].quantile(0.98))
    if vmax <= 0:
        vmax = float(split[metric].max()) if len(split) else 1.0
    draw_colorbar(draw, width - 140, 120, 24, 360, vmax, palette, metric_label, body_font, small_font)

    stat_y = 520
    stats = [
        f"배분 총량: {split[metric].sum():,.1f}",
        f"상위 1% 기준: {vmax:,.1f}",
        f"평균 가중치: {split['weight'].mean():.4f}",
        f"최소/최대 가중치: {split['weight'].min():.4f} / {split['weight'].max():.4f}",
    ]
    for s in stats:
        draw.text((width - 240, stat_y), s, fill=(40, 40, 40), font=small_font)
        stat_y += 24

    foot = "집계구 경계를 경계면에서 절단한 뒤 교차면적 비율로 인구·종사자를 배분"
    draw.text((40, height - 34), foot, fill=(80, 80, 80), font=small_font)
    return img


def save_panel(split: gpd.GeoDataFrame, boundary: gpd.GeoDataFrame, region: str, metric: str, palette, metric_label: str, out_path: Path) -> None:
    title = f"{REGION_LABELS[region]} {metric_label}"
    panel = render_panel(region, metric, title, split, boundary, palette, metric_label)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    panel.save(out_path)


def main() -> None:
    blocks = load_blocks()
    boundaries = {
        "pangyo": load_boundary("pangyo"),
        "wirye": load_boundary("wirye"),
    }

    split_rows = []
    summary_rows = []
    splits: dict[str, gpd.GeoDataFrame] = {}

    for region, boundary in boundaries.items():
        split = split_blocks_by_boundary(blocks, boundary)
        split["region_id"] = region
        split["region_name"] = REGION_LABELS[region]
        splits[region] = split
        summary_rows.append(summarize(region, split, boundary))
        for _, row in split.iterrows():
            split_rows.append(
                {
                    "region_id": region,
                    "tot_oa_cd": row["tot_oa_cd"],
                    "population_alloc": float(row["population_alloc"]),
                    "worker_alloc": float(row["worker_alloc"]),
                    "weight": float(row["weight"]),
                    "intersection_area_m2": float(row["intersection_area_m2"]),
                    "block_area_m2": float(row["block_area_m2"]),
                }
            )

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    OUT_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    MAPS.mkdir(parents=True, exist_ok=True)
    INVENTORY.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(split_rows).to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    gpd.GeoDataFrame(
        pd.concat(
            [
                split[[
                    "region_id",
                    "tot_oa_cd",
                    "population_alloc",
                    "worker_alloc",
                    "weight",
                    "intersection_area_m2",
                    "block_area_m2",
                    "geometry",
                ]]
                for split in splits.values()
            ],
            ignore_index=True,
        ),
        geometry="geometry",
        crs=blocks.crs,
    ).to_crs(4326).to_file(OUT_GEOJSON, driver="GeoJSON")

    summary_df = pd.DataFrame(summary_rows)
    summary_md = [
        "# 판교·위례 집계구 분할 인구·종사자 히트맵 v1",
        "",
        "- 공간단위 통합 방식: SGIS 집계구 폴리곤을 사업지 경계로 절단한 뒤 `intersection_area / block_area` 비율로 인구와 종사자를 면적가중 배분",
        f"- split csv: `{OUT_CSV}`",
        f"- split geojson: `{OUT_GEOJSON}`",
        "",
        summary_df.to_string(index=False),
        "",
        "공간단위 통합 문장:",
        "본 분석은 SGIS 집계구를 기본 공간단위로 사용하되, 사업지 경계와 집계구 경계의 불일치를 해소하기 위해 집계구를 경계면에서 절단한 뒤 교차면적 비율로 인구와 종사자를 면적가중 배분하였다.",
    ]
    OUT_MD.write_text("\n".join(summary_md), encoding="utf-8")

    save_panel(
        splits["pangyo"],
        boundaries["pangyo"],
        "pangyo",
        "population_alloc",
        POP_PALETTE,
        "거주자 수",
        MAPS / "pangyo_planning_boundary_population_heatmap_v1.png",
    )
    save_panel(
        splits["pangyo"],
        boundaries["pangyo"],
        "pangyo",
        "worker_alloc",
        WORKER_PALETTE,
        "종사자 수",
        MAPS / "pangyo_planning_boundary_worker_heatmap_v1.png",
    )
    save_panel(
        splits["wirye"],
        boundaries["wirye"],
        "wirye",
        "population_alloc",
        POP_PALETTE,
        "거주자 수",
        MAPS / "wirye_planning_boundary_population_heatmap_v1.png",
    )
    save_panel(
        splits["wirye"],
        boundaries["wirye"],
        "wirye",
        "worker_alloc",
        WORKER_PALETTE,
        "종사자 수",
        MAPS / "wirye_planning_boundary_worker_heatmap_v1.png",
    )

    # Combined 2x2 sheet.
    panels = [
        Image.open(MAPS / "pangyo_planning_boundary_population_heatmap_v1.png"),
        Image.open(MAPS / "pangyo_planning_boundary_worker_heatmap_v1.png"),
        Image.open(MAPS / "wirye_planning_boundary_population_heatmap_v1.png"),
        Image.open(MAPS / "wirye_planning_boundary_worker_heatmap_v1.png"),
    ]
    w = max(img.width for img in panels)
    h = max(img.height for img in panels)
    canvas = Image.new("RGB", (w * 2 + 40, h * 2 + 40), "white")
    positions = [(0, 0), (w + 20, 0), (0, h + 20), (w + 20, h + 20)]
    for img, pos in zip(panels, positions):
        canvas.paste(img, pos)
    canvas.save(OUT_COMBINED)

    print(OUT_CSV)
    print(OUT_GEOJSON)
    print(OUT_MD)
    print(OUT_COMBINED)


if __name__ == "__main__":
    main()
