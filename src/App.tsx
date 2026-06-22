import { useEffect, useMemo, useRef, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import maplibregl from 'maplibre-gl';
import {
  Activity,
  ArrowRightLeft,
  BadgeInfo,
  BarChart3,
  Building2,
  Compass,
  MapPinned,
  Shield,
  Sparkles,
  TrainFront,
  TreePine,
  Users,
  Warehouse,
} from 'lucide-react';

type RegionId = 'pangyo' | 'wirye';
type ScopeMode = 'planning' | 'core' | 'station';
type TransportMode = 'subway' | 'bus';
type MetricMode = 'workers' | 'population';
type SelectedKind = 'landuse' | 'isochrone' | 'network' | 'building' | null;
type GeoJson = { type: 'FeatureCollection'; features: Array<any>; [key: string]: any };

type LayerFlags = {
  landuse: boolean;
  fullBoundary: boolean;
  coreBoundary: boolean;
  supportBoundary: boolean;
  stationMarkers: boolean;
  accessibilityBuffer: boolean;
  buildings: boolean;
};

type SelectedFeature = {
  kind: SelectedKind;
  regionId: RegionId;
  title: string;
  properties: Record<string, any>;
};

type AccessibilityRow = {
  origin_region_id: string;
  origin_station_name: string;
  station_label: string;
  mode: TransportMode;
  threshold_min: number;
  accessible_population: number;
  accessible_workers: number;
  accessible_businesses: number;
  reachable_station_count: number;
  reachable_link_count: number;
  accessible_area_km2: number;
};

type BusAccessStationRow = {
  origin_key: string;
  origin_name: string;
  selected_station_name: string;
  selected_station_id: string;
  selected_station_no?: string | null;
  selected_travel_time_min: number;
  station_count: number;
  mean_resident_population_500m: number;
  mean_worker_population_500m: number;
  max_resident_population_500m: number;
  max_worker_population_500m: number;
};

type BusAccessSelectedRow = {
  origin_key: string;
  origin_name: string;
  selected_station_name: string;
  selected_station_id: string;
  selected_station_no?: string | null;
  selected_travel_time_min: number;
  resident_population_500m: number;
  worker_population_500m: number;
  buffer_area_m2?: number | null;
  coverage_ratio?: number | null;
  intersected_grid_count?: number | null;
  selection_reason?: string | null;
};

type BusAccessCandidateRow = {
  origin_key: string;
  origin_name: string;
  target_station_id: string;
  target_station_name: string;
  target_station_no?: string | null;
  travel_time_min: number;
  resident_population_500m: number;
  worker_population_500m: number;
  buffer_area_m2?: number | null;
  coverage_ratio?: number | null;
  intersected_grid_count?: number | null;
  selected?: boolean | null;
};

type BusAccessDashboard = {
  table: BusAccessStationRow[];
  selected: BusAccessSelectedRow[];
  candidates: BusAccessCandidateRow[];
};

type Subway750TableRow = {
  station_name: string;
  origin_station_line?: string | null;
  station_count: number;
  mean_population_750m: number;
  mean_worker_750m: number;
  max_population_750m: number;
  max_worker_750m: number;
  representative_line_name: string;
  representative_node_id: number;
  station_total_population_750m?: number | null;
  station_total_worker_750m?: number | null;
};

type Subway750SelectedRow = {
  origin_region_id?: string;
  origin_station_name?: string;
  origin_station_line?: string | null;
  station_name: string;
  line_name: string;
  node_id: number;
  population_750m: number;
  worker_750m: number;
  station_total_population_750m?: number | null;
  station_total_worker_750m?: number | null;
  min_travel_time_min?: number | null;
  buffer_area_m2?: number | null;
  coverage_ratio?: number | null;
  intersected_grid_count?: number | null;
  selected?: boolean | null;
  selection_reason?: string | null;
};

type Subway750CandidateRow = Subway750SelectedRow;

type Subway750CurveCandidateRow = Subway750CandidateRow & {
  min_travel_time_min?: number | null;
  travel_time_min?: number | null;
  selected_travel_time_min?: number | null;
};

type Subway750Dashboard = {
  table: Subway750TableRow[];
  selected: Subway750SelectedRow[];
  candidates: Subway750CandidateRow[];
};

type SgisRow = {
  region_id: string;
  worker_density_per_km2?: number | null;
  business_density_per_km2?: number | null;
  population_density_per_km2?: number | null;
  jobs_to_population_ratio?: number | null;
  workers_per_business?: number | null;
  interpretation_note?: string | null;
};

type PerformanceRowV14 = {
  region_id: string;
  region_label?: string | null;
  area_km2?: number | null;
  population?: number | null;
  households?: number | null;
  businesses?: number | null;
  workers?: number | null;
  population_density_per_km2?: number | null;
  business_density_per_km2?: number | null;
  worker_density_per_km2?: number | null;
  jobs_housing_ratio?: number | null;
  average_far_percent_v11?: number | null;
  average_bcr_percent_v11?: number | null;
  building_count_v11?: number | null;
  office_floor_area_share_v11?: number | null;
  residential_floor_area_share_v11?: number | null;
  commercial_floor_area_share_v11?: number | null;
  reliability_level?: string | null;
  interpretation_note?: string | null;
};

type BuildingGisRow = {
  region_group: string;
  region_id: string;
  scope: 'full' | 'core';
  record_count: number;
  unique_pnu_count: number;
  total_floor_area_m2: number;
  site_area_m2: number;
  building_area_m2: number;
  floor_count_median: number | null;
  approval_year_median: number | null;
  use_rows: Array<{
    main_use_group: string;
    record_count: number;
    unique_pnu_count: number;
    total_floor_area_m2: number;
    share_floor_area: number;
    share_count: number;
  }>;
  use_rows_by_count: Array<{
    main_use_group: string;
    record_count: number;
    share_count: number;
  }>;
};

type BuildingSummaryRow = {
  region_group: string;
  building_count: number;
  core_count?: number;
  support_count?: number;
  total_floor_area_m2: number;
  average_far_percent: number | null;
  average_bcr_percent: number | null;
  weighted_far_percent?: number | null;
  weighted_bcr_percent?: number | null;
  approval_year_median: number | null;
  top_uses: Array<{ main_use_group: string; floor_area_m2: number; share: number | null }>;
};

type BoundaryFarSummaryRow = {
  area_name: 'pangyo' | 'wirye';
  region_label: string;
  boundary_rows: number;
  boundary_site_area_m2: number;
  boundary_weighted_far_percent: number;
  office_rows: number;
  office_site_area_m2: number;
  office_weighted_far_percent: number;
};

type PlanningBoundaryPopWorkerRow = {
  region_id: RegionId;
  region_name: string;
  area_type: 'core' | 'full';
  boundary_area_m2: number;
  boundary_area_km2: number;
  split_polygons: number;
  source_blocks: number;
  population_total: number;
  worker_total: number;
  coverage_ratio: number;
};

type Slice = { label: string; value: number; share: number; color: string };

type RegionData = {
  id: RegionId;
  label: string;
  shortLabel: string;
  stationName: string;
  center: [number, number];
  planningLanduse: GeoJson;
  scopeLanduse: GeoJson;
  fullBoundary: GeoJson;
  coreBoundary: GeoJson;
  supportBoundary: GeoJson;
  stationMarkers: GeoJson;
  isochrones: GeoJson;
  subwayNetworkNodes: GeoJson;
  subwayNetworkRoutes: GeoJson;
  subwayLineNetwork: GeoJson;
  subwayReachStations: GeoJson;
  busStations: GeoJson;
  busPathEdges: GeoJson;
  buildingsFull: GeoJson;
  buildingsCore: GeoJson;
  landusePlanningSlices: Slice[];
  landuseScopeSlices: Record<ScopeMode, Slice[]>;
  buildingSummaryFull: BuildingSummaryRow | null;
  buildingSummaryCore: BuildingSummaryRow | null;
  buildingGisFull: BuildingGisRow | null;
  buildingGisCore: BuildingGisRow | null;
  planningPerformance: PerformanceRowV14 | null;
  corePerformance: PerformanceRowV14 | null;
  sgisCore: SgisRow | null;
  sgisAnalysis: SgisRow | null;
};

type AppData = {
  pangyo: RegionData;
  wirye: RegionData;
  accessibilityRows: AccessibilityRow[];
  accessibilityCurveRows: AccessibilityRow[];
  buildingSummaryRows: BuildingSummaryRow[];
  buildingGisRows: BuildingGisRow[];
  boundaryFarSummaryRows: BoundaryFarSummaryRow[];
  planningBoundaryPopWorkerRows: PlanningBoundaryPopWorkerRow[];
};

type BusAccessDashboardData = BusAccessDashboard | null;

const BASE = import.meta.env.BASE_URL || '/';
const dataUrl = (name: string) => `${BASE}data/${name}`;
const OSM_TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';

const REGION_META: Record<RegionId, { label: string; shortLabel: string; stationName: string; center: [number, number] }> = {
  pangyo: { label: '판교테크노밸리', shortLabel: '판교', stationName: '판교', center: [127.1096, 37.3949] },
  wirye: { label: '위례신도시 업무·상업지구', shortLabel: '위례', stationName: '복정', center: [127.1268, 37.4708] },
};

const EMPTY_GEOJSON: GeoJson = { type: 'FeatureCollection', features: [] };

function createEmptyRegion(regionId: RegionId): RegionData {
  const meta = REGION_META[regionId];
  return {
    id: regionId,
    label: meta.label,
    shortLabel: meta.shortLabel,
    stationName: meta.stationName,
    center: meta.center,
    planningLanduse: EMPTY_GEOJSON,
    scopeLanduse: EMPTY_GEOJSON,
    fullBoundary: EMPTY_GEOJSON,
    coreBoundary: EMPTY_GEOJSON,
    supportBoundary: EMPTY_GEOJSON,
    stationMarkers: EMPTY_GEOJSON,
    isochrones: EMPTY_GEOJSON,
    subwayNetworkNodes: EMPTY_GEOJSON,
    subwayNetworkRoutes: EMPTY_GEOJSON,
    subwayLineNetwork: EMPTY_GEOJSON,
    subwayReachStations: EMPTY_GEOJSON,
    busStations: EMPTY_GEOJSON,
    busPathEdges: EMPTY_GEOJSON,
    buildingsFull: EMPTY_GEOJSON,
    buildingsCore: EMPTY_GEOJSON,
    landusePlanningSlices: [],
    landuseScopeSlices: { planning: [], core: [], station: [] },
    buildingSummaryFull: null,
    buildingSummaryCore: null,
    buildingGisFull: null,
    buildingGisCore: null,
    planningPerformance: null,
    corePerformance: null,
    sgisCore: null,
    sgisAnalysis: null,
  };
}

const TRANSPORT_LABEL: Record<TransportMode, string> = {
  subway: '지하철',
  bus: '버스',
};

const TRANSPORT_COLOR: Record<TransportMode, string> = {
  subway: '#2f6bff',
  bus: '#8b5cf6',
};

const TRANSPORT_FILL: Record<TransportMode, string> = {
  subway: 'rgba(47, 107, 255, 0.22)',
  bus: 'rgba(139, 92, 246, 0.22)',
};

const LANDUSE_COLORS: Record<string, string> = {
  '업무·도시지원': '#65b8ff',
  업무: '#3b82f6',
  상업: '#ef4444',
  주거: '#f59e0b',
  '주거·혼합': '#fbbf24',
  '준주거·혼합': '#38bdf8',
  '공공·교육': '#8b5cf6',
  공공: '#8b5cf6',
  교육: '#a855f7',
  '녹지·공원': '#86efac',
  녹지: '#86efac',
  교통: '#64748b',
  기타: '#94a3b8',
  unknown: '#cbd5e1',
};

const BUILDING_COLORS: Record<string, string> = {
  업무: '#2563eb',
  상업: '#f97316',
  주거: '#facc15',
  교육: '#8b5cf6',
  공공: '#06b6d4',
  생활서비스: '#10b981',
  '산업·물류': '#64748b',
  기타: '#94a3b8',
  unknown: '#cbd5e1',
};

const LAYER_DEFAULTS: LayerFlags = {
  landuse: true,
  fullBoundary: true,
  coreBoundary: true,
  supportBoundary: false,
  stationMarkers: true,
  accessibilityBuffer: false,
  buildings: false,
};

function loadJson<T>(name: string): Promise<T> {
  return fetch(dataUrl(name)).then(async (response) => {
    if (!response.ok) throw new Error(`Failed to load ${name} (${response.status})`);
    return JSON.parse(await response.text()) as T;
  });
}

function splitCsvLine(line: string) {
  const values: string[] = [];
  let current = '';
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    if (char === '"') {
      if (quoted && line[index + 1] === '"') {
        current += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }
      continue;
    }
    if (char === ',' && !quoted) {
      values.push(current);
      current = '';
      continue;
    }
    current += char;
  }
  values.push(current);
  return values;
}

function loadCsvRows<T extends Record<string, any>>(name: string): Promise<T[]> {
  return fetch(dataUrl(name)).then(async (response) => {
    if (!response.ok) throw new Error(`Failed to load ${name} (${response.status})`);
    const text = (await response.text()).replace(/^\uFEFF/, '');
    const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    if (!lines.length) return [];
    const headers = splitCsvLine(lines[0]).map((header) => header.trim());
    return lines.slice(1).map((line) => {
      const values = splitCsvLine(line);
      const row: Record<string, any> = {};
      headers.forEach((header, index) => {
        row[header] = values[index] ?? '';
      });
      return row as T;
    });
  });
}

function asFeatureCollection(value: any): GeoJson {
  if (value && value.type === 'FeatureCollection' && Array.isArray(value.features)) return value as GeoJson;
  return { type: 'FeatureCollection', features: [] };
}

function cloneFeatureCollection(fc: GeoJson): GeoJson {
  const value = asFeatureCollection(fc);
  return {
    ...value,
    features: value.features.map((feature) => ({
      ...feature,
      properties: { ...(feature.properties ?? {}) },
    })),
  };
}

function filterFeatureCollection(fc: GeoJson, predicate: (feature: any) => boolean): GeoJson {
  const value = asFeatureCollection(fc);
  return {
    ...value,
    features: value.features.filter(predicate).map((feature) => ({
      ...feature,
      properties: { ...(feature.properties ?? {}) },
    })),
  };
}

function dedupeFeatureCollection(fc: GeoJson, keyFn: (feature: any) => string, scoreFn?: (feature: any) => number): GeoJson {
  const value = asFeatureCollection(fc);
  const seen = new Map<string, any>();
  for (const feature of value.features) {
    const key = keyFn(feature);
    if (!key) continue;
    const score = scoreFn ? scoreFn(feature) : 0;
    const current = seen.get(key);
    if (!current) {
      seen.set(key, { feature, score });
      continue;
    }
    if (score < current.score) seen.set(key, { feature, score });
  }
  return {
    ...value,
    features: Array.from(seen.values()).map((entry) => ({
      ...entry.feature,
      properties: { ...(entry.feature.properties ?? {}) },
    })),
  };
}

function mapFeatureCollection(fc: GeoJson, mapper: (feature: any) => any): GeoJson {
  const value = asFeatureCollection(fc);
  return {
    ...value,
    features: value.features.map((feature) => {
      const next = mapper(feature) ?? {};
      return {
        ...feature,
        ...next,
        properties: { ...(feature.properties ?? {}), ...(next.properties ?? {}) },
      };
    }),
  };
}

function recoverGeoJson(value: any): GeoJson {
  return cloneFeatureCollection(asFeatureCollection(value));
}

function formatNumber(value: unknown, digits = 0) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 'N/A';
  return number.toLocaleString('ko-KR', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function formatCompactNumber(value: unknown, digits = 1) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 'N/A';
  return new Intl.NumberFormat('ko-KR', { notation: 'compact', maximumFractionDigits: digits }).format(number);
}

function formatPercent(value: unknown, digits = 1) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 'N/A';
  const pct = Math.abs(number) <= 1 ? number * 100 : number;
  return `${pct.toFixed(digits)}%`;
}

function formatArea(value: unknown, digits = 0) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 'N/A';
  return `${number.toLocaleString('ko-KR', { minimumFractionDigits: digits, maximumFractionDigits: digits })}㎡`;
}

function formatYear(value: unknown) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 'N/A';
  return `${Math.round(number)}년`;
}

function stationMatches(regionId: RegionId, feature: any) {
  const props = feature?.properties ?? {};
  const candidates = [props.station_name, props.origin_station_name, props.station_label, props.marker_label].filter(Boolean).join('|').toLowerCase();
  return regionId === 'pangyo' ? candidates.includes('판교') || candidates.includes('pangyo') : candidates.includes('복정') || candidates.includes('bokjeong');
}

function getIsoStation(props: Record<string, any>) {
  return String(props.station_label ?? props.station_name ?? props.origin_station_name ?? props.origin ?? props.station ?? '');
}

function getIsoMode(props: Record<string, any>) {
  return String(props.mode ?? props.access_mode ?? props.transport_mode ?? '');
}

function getIsoMinute(props: Record<string, any>) {
  return Number(props.minute ?? props.threshold_min ?? props.travel_time_min ?? props.threshold ?? props.cutoff_min ?? props.time ?? 0);
}

function getNetworkOrigin(props: Record<string, any>) {
  return String(props.origin_name ?? props.origin_station_name ?? props.origin_station ?? props.origin ?? props.station_name ?? '');
}

function getNetworkTarget(props: Record<string, any>) {
  return String(props.target_name ?? props.target_station_name ?? props.target ?? props.station_name ?? props.route_id ?? '');
}

function getNetworkRoute(props: Record<string, any>) {
  return String(props.route_id ?? props.line_name ?? props.route_name ?? props.source ?? '');
}

function getNetworkTime(props: Record<string, any>) {
  return Number(props.reachable_time_min ?? props.time_min ?? props.cumulative_time_min ?? props.threshold_min ?? 0);
}

function summarizeByKey(features: any[], keyGetter: (props: Record<string, any>) => string, valueGetter: (props: Record<string, any>) => number): Slice[] {
  const totals = new Map<string, number>();
  for (const feature of features) {
    const props = feature?.properties ?? {};
    const key = keyGetter(props) || 'unknown';
    const value = Number(valueGetter(props));
    totals.set(key, (totals.get(key) ?? 0) + (Number.isFinite(value) ? value : 0));
  }
  const total = [...totals.values()].reduce((sum, value) => sum + value, 0);
  return [...totals.entries()]
    .map(([label, value]) => ({
      label,
      value,
      share: total > 0 ? value / total : 0,
      color: LANDUSE_COLORS[label] ?? BUILDING_COLORS[label] ?? '#94a3b8',
    }))
    .filter((item) => item.value > 0)
    .sort((a, b) => b.value - a.value)
    .slice(0, 6);
}

function summarizeBuildingsUseRow(rows: any[], field: 'share_floor_area' | 'share_count') {
  return rows
    .map((row) => ({
      label: String(row.main_use_group ?? 'unknown'),
      value: Number(field === 'share_floor_area' ? row.total_floor_area_m2 ?? row.main_use_floor_area_m2 ?? 0 : row.record_count ?? row.building_count ?? 0),
      share: Number(row[field] ?? 0),
      color: BUILDING_COLORS[String(row.main_use_group ?? 'unknown')] ?? '#94a3b8',
    }))
    .filter((item) => item.value >= 0)
    .sort((a, b) => b.value - a.value)
    .slice(0, 6);
}

function nearestMinute(target: number, candidates: number[]) {
  if (!candidates.length) return target;
  let best = candidates[0];
  let gap = Math.abs(best - target);
  for (const value of candidates) {
    const nextGap = Math.abs(value - target);
    if (nextGap < gap) {
      best = value;
      gap = nextGap;
    }
  }
  return best;
}

function featureCollectionBounds(fc: GeoJson): maplibregl.LngLatBounds | null {
  const bounds = new maplibregl.LngLatBounds();
  let hasPoint = false;
  const pushCoords = (coords: any) => {
    if (!coords) return;
    if (Array.isArray(coords) && typeof coords[0] === 'number' && typeof coords[1] === 'number') {
      bounds.extend(coords as [number, number]);
      hasPoint = true;
      return;
    }
    if (Array.isArray(coords)) for (const item of coords) pushCoords(item);
  };
  for (const feature of asFeatureCollection(fc).features) pushCoords(feature.geometry?.coordinates);
  return hasPoint ? bounds : null;
}

function filteredPointBounds(fc: GeoJson, predicate: (feature: any) => boolean): maplibregl.LngLatBounds | null {
  const bounds = new maplibregl.LngLatBounds();
  let hasPoint = false;
  for (const feature of asFeatureCollection(fc).features) {
    if (!predicate(feature)) continue;
    const coords = feature.geometry?.coordinates;
    if (!Array.isArray(coords) || typeof coords[0] !== 'number' || typeof coords[1] !== 'number') continue;
    bounds.extend(coords as [number, number]);
    hasPoint = true;
  }
  return hasPoint ? bounds : null;
}

function getLanduseFillColor(props: Record<string, any>) {
  const key = String(props.display_color_key ?? props.category_group ?? props.zone_group ?? props.planned_use_group ?? props.block_type ?? props.planned_use_detail ?? '기타');
  return LANDUSE_COLORS[key] ?? LANDUSE_COLORS[String(props.zone_group ?? props.category_group ?? 'unknown')] ?? LANDUSE_COLORS.unknown;
}

function getLanduseFillOpacity(props: Record<string, any>) {
  const key = String(props.display_color_key ?? props.category_group ?? props.zone_group ?? props.planned_use_group ?? props.block_type ?? props.planned_use_detail ?? '기타');
  if (key.includes('녹지') || key.includes('공원')) return 0.18;
  return 0.86;
}

function geometryToSvgPaths(geometry: any, project: (coord: [number, number]) => { x: number; y: number }) {
  const paths: string[] = [];
  const ringToPath = (ring: any[]) => {
    if (!Array.isArray(ring) || ring.length < 3) return;
    const commands: string[] = [];
    for (let index = 0; index < ring.length; index += 1) {
      const coord = ring[index];
      if (!Array.isArray(coord) || coord.length < 2) continue;
      const point = project([Number(coord[0]), Number(coord[1])]);
      commands.push(`${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`);
    }
    if (commands.length >= 3) paths.push(`${commands.join(' ')} Z`);
  };
  if (!geometry) return paths;
  if (geometry.type === 'Polygon') {
    for (const ring of geometry.coordinates ?? []) ringToPath(ring);
  } else if (geometry.type === 'MultiPolygon') {
    for (const polygon of geometry.coordinates ?? []) {
      for (const ring of polygon ?? []) ringToPath(ring);
    }
  }
  return paths;
}

function getCurveValue(rows: AccessibilityRow[], stationName: string, mode: TransportMode, minute: number, metric: MetricMode) {
  const curve = rows
    .filter((row) => row.origin_station_name === stationName && row.mode === mode)
    .sort((a, b) => Number(a.threshold_min) - Number(b.threshold_min))
    .map((row) => ({ minute: Number(row.threshold_min), value: metric === 'workers' ? Number(row.accessible_workers ?? 0) : Number(row.accessible_population ?? 0) }));
  if (!curve.length) return 0;
  const exact = curve.find((row) => row.minute === minute);
  if (exact) return exact.value;
  let left = curve[0];
  let right = curve[curve.length - 1];
  for (const row of curve) {
    if (row.minute < minute) left = row;
    if (row.minute > minute) {
      right = row;
      break;
    }
  }
  if (left.minute === right.minute) return left.value;
  const ratio = (minute - left.minute) / (right.minute - left.minute);
  return left.value + (right.value - left.value) * ratio;
}

function sumBusCandidates(rows: BusAccessCandidateRow[], originKey: 'pangyo' | 'bokjeong', minute: number, metric: MetricMode) {
  return rows
    .filter((row) => row.origin_key === originKey && Number(row.travel_time_min ?? 0) <= minute)
    .reduce((sum, row) => sum + Number(metric === 'workers' ? row.worker_population_500m ?? 0 : row.resident_population_500m ?? 0), 0);
}

function buildBusCurveRows(rows: BusAccessCandidateRow[], originKey: 'pangyo' | 'bokjeong', metric: MetricMode) {
  const points: AccessibilityRow[] = [];
  for (let minute = 0; minute <= 60; minute += 5) {
    const value = sumBusCandidates(rows, originKey, minute, metric);
    points.push({
      origin_region_id: `${originKey}_bus`,
      origin_station_name: originKey === 'pangyo' ? '판교' : '복정',
      station_label: originKey === 'pangyo' ? '판교역' : '복정역',
      mode: 'bus',
      threshold_min: minute,
      accessible_population: metric === 'population' ? value : 0,
      accessible_workers: metric === 'workers' ? value : 0,
      accessible_businesses: 0,
      reachable_station_count: 0,
      reachable_link_count: 0,
      accessible_area_km2: 0,
    });
  }
  return points;
}

function getBusCandidateSummary(rows: BusAccessCandidateRow[], originKey: 'pangyo' | 'bokjeong', minute: number) {
  const filtered = rows.filter((row) => row.origin_key === originKey && Number(row.travel_time_min ?? 0) <= minute);
  return {
    resident_population_500m: filtered.reduce((sum, row) => sum + Number(row.resident_population_500m ?? 0), 0),
    worker_population_500m: filtered.reduce((sum, row) => sum + Number(row.worker_population_500m ?? 0), 0),
    station_count: filtered.length,
  };
}

function normalizeStationLabel(value: unknown) {
  return String(value ?? '').replace(/\s+/g, '').trim();
}

function stationLabelMatches(value: unknown, target: string) {
  const normalizedValue = normalizeStationLabel(value);
  const normalizedTarget = normalizeStationLabel(target);
  return normalizedValue === normalizedTarget || normalizedValue.includes(normalizedTarget);
}

function getSubwaySelectedRow(dashboard: Subway750Dashboard | null, stationName: '판교' | '복정') {
  if (!dashboard) return null;
  return (
    dashboard.selected.find((row) => stationLabelMatches(row.station_name, stationName) && row.selected) ??
    dashboard.selected.find((row) => stationLabelMatches(row.station_name, stationName)) ??
    dashboard.table.find((row) => stationLabelMatches(row.station_name, stationName)) ??
    null
  );
}

function getSubwayCandidateTravelTime(row: Subway750CurveCandidateRow) {
  return Number(row.min_travel_time_min ?? row.travel_time_min ?? row.selected_travel_time_min ?? 0);
}

function getSubwayStationKey(row: Subway750CurveCandidateRow) {
  return `${String(row.origin_region_id ?? '')}|${String(row.origin_station_name ?? '')}|${normalizeStationLabel(row.station_norm ?? row.station_name ?? row.node_id ?? '')}`;
}

function pickEarliestSubwayRows(rows: Subway750CurveCandidateRow[]) {
  const bestRows = new Map<string, Subway750CurveCandidateRow>();
  for (const row of rows) {
    const key = getSubwayStationKey(row);
    if (!key.replace(/\|/g, '').trim()) continue;
    const current = bestRows.get(key);
    if (!current) {
      bestRows.set(key, row);
      continue;
    }
    const currentThreshold = Number(current.threshold_min ?? Number.POSITIVE_INFINITY);
    const nextThreshold = Number(row.threshold_min ?? Number.POSITIVE_INFINITY);
    const currentTravel = getSubwayCandidateTravelTime(current);
    const nextTravel = getSubwayCandidateTravelTime(row);
    if (nextThreshold < currentThreshold || (nextThreshold === currentThreshold && nextTravel < currentTravel)) {
      bestRows.set(key, row);
    }
  }
  return Array.from(bestRows.values());
}

function buildSubwayReachStationsFromCsv(rows: Subway750CurveCandidateRow[]): GeoJson {
  return {
    type: 'FeatureCollection',
    features: rows.map((row, index) => ({
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: [Number(row.longitude ?? 0), Number(row.latitude ?? 0)],
      },
      properties: {
        row_id: index,
        origin_region_id: row.origin_region_id,
        origin_station_name: row.origin_station_name,
        origin_station_line: row.origin_station_line ?? null,
        station_name: row.station_name,
        station_label: row.station_name,
        line_name: row.line_name,
        node_id: Number(row.node_id ?? 0),
        threshold_min: Number(row.threshold_min ?? 0),
        min_travel_time_min: Number(row.min_travel_time_min ?? row.threshold_min ?? 0),
        travel_time_min: Number(row.min_travel_time_min ?? row.threshold_min ?? 0),
        selected_travel_time_min: Number(row.selected_travel_time_min ?? row.min_travel_time_min ?? row.threshold_min ?? 0),
        population_750m: Number(row.population_750m ?? 0),
        worker_750m: Number(row.worker_750m ?? 0),
        buffer_area_m2: Number(row.buffer_area_m2 ?? 0),
        covered_area_m2: Number(row.covered_area_m2 ?? 0),
        coverage_ratio: Number(row.coverage_ratio ?? 0),
        intersected_grid_count: Number(row.intersected_grid_count ?? 0),
      },
    })),
  };
}

function subwayTimeFilterExpression(selectedTime: number) {
  return ['<=', ['to-number', ['coalesce', ['get', 'min_travel_time_min'], ['get', 'travel_time_min'], ['get', 'cumulative_time_min'], ['get', 'threshold_min'], 0]], selectedTime] as any;
}

function subwayPointTimeFilterExpression(selectedTime: number) {
  return ['<=', ['to-number', ['coalesce', ['get', 'min_travel_time_min'], ['get', 'travel_time_min'], ['get', 'selected_travel_time_min'], ['get', 'threshold_min'], 0]], selectedTime] as any;
}

type SubwayResolvedRow = Subway750CurveCandidateRow & {
  travel_time_min: number;
  min_travel_time_min: number;
};

function resolveSubwayRows(
  nodeFeatures: GeoJson | null,
  metricRows: Subway750CurveCandidateRow[],
  stationName: '판교' | '복정',
) {
  const nodes = asFeatureCollection(nodeFeatures).features;
  const nodeMap = new Map<string, SubwayResolvedRow>();
  const metricBuckets = new Map<string, Subway750CurveCandidateRow[]>();
  const originKey = stationName === '판교' ? 'pangyo' : 'wirye';
  for (const row of metricRows) {
    if (!String(row.origin_region_id ?? '').toLowerCase().includes(originKey)) continue;
    const key = normalizeStationLabel(row.station_name ?? '');
    if (!key) continue;
    const bucket = metricBuckets.get(key) ?? [];
    bucket.push(row);
    metricBuckets.set(key, bucket);
  }
  const pickMetricRow = (stationKey: string, lineName: string) => {
    const bucket = metricBuckets.get(stationKey) ?? [];
    if (!bucket.length) return null;
    const exact = bucket.filter((row) => normalizeStationLabel(row.line_name ?? '') === normalizeStationLabel(lineName));
    const pool = exact.length ? exact : bucket;
    return pool.slice().sort((a, b) => getSubwayCandidateTravelTime(a) - getSubwayCandidateTravelTime(b))[0] ?? null;
  };
  for (const feature of nodes) {
    const props = feature.properties ?? {};
    const originRegion = String(props.origin_region_id ?? '').toLowerCase();
    if (!originRegion.includes(originKey) && !stationLabelMatches(props.origin_station_name, stationName) && !stationLabelMatches(props.origin_station_label, stationName)) continue;
    const stationKey = normalizeStationLabel(props.station_name ?? props.station_label ?? '');
    if (!stationKey) continue;
    const travel = Number(props.travel_time_min ?? props.min_travel_time_min ?? props.selected_travel_time_min ?? props.threshold_min ?? 0);
    if (!Number.isFinite(travel)) continue;
    const current = nodeMap.get(stationKey);
    if (current && travel >= current.travel_time_min) continue;
    const metricRow = pickMetricRow(stationKey, String(props.line_name ?? ''));
    nodeMap.set(stationKey, {
      ...(metricRow ?? {}),
      ...props,
      origin_station_name: stationName,
      station_label: stationName,
      travel_time_min: travel,
      min_travel_time_min: travel,
      population_750m: Number(metricRow?.population_750m ?? props.population_750m ?? 0),
      worker_750m: Number(metricRow?.worker_750m ?? props.worker_750m ?? 0),
    } as SubwayResolvedRow);
  }
  return Array.from(nodeMap.values()).sort((a, b) => a.travel_time_min - b.travel_time_min);
}

function getSubwayCandidateSummary(rows: Subway750CurveCandidateRow[], stationName: '판교' | '복정', minute: number) {
  const filtered = rows.filter((row) => stationLabelMatches(row.origin_station_name, stationName) && Number(row.threshold_min ?? 0) <= minute);
  return {
    population_750m: filtered.reduce((sum, row) => sum + Number(row.population_750m ?? 0), 0),
    worker_750m: filtered.reduce((sum, row) => sum + Number(row.worker_750m ?? 0), 0),
    station_count: filtered.length,
  };
}

function buildSubwayDashboardFromCsv(rows: Subway750CurveCandidateRow[]): Subway750Dashboard {
  const normalizeMinute = (value: unknown) => Number(value ?? 0);
  const numericRows = rows
    .map((row) => ({
      ...row,
      threshold_min: normalizeMinute(row.threshold_min),
      population_750m: Number(row.population_750m ?? 0),
      worker_750m: Number(row.worker_750m ?? 0),
      min_travel_time_min: Number(row.min_travel_time_min ?? row.threshold_min ?? 0),
      selected_travel_time_min: Number(row.selected_travel_time_min ?? row.min_travel_time_min ?? row.threshold_min ?? 0),
    }))
    .sort((a, b) => {
      const regionOrder = a.origin_region_id.localeCompare(b.origin_region_id);
      if (regionOrder !== 0) return regionOrder;
      const stationOrder = String(a.origin_station_name ?? '').localeCompare(String(b.origin_station_name ?? ''));
      if (stationOrder !== 0) return stationOrder;
      const lineOrder = String(a.origin_station_line ?? '').localeCompare(String(b.origin_station_line ?? ''));
      if (lineOrder !== 0) return lineOrder;
      return Number(a.threshold_min ?? 0) - Number(b.threshold_min ?? 0);
    });
  const earliestRows = pickEarliestSubwayRows(numericRows).sort((a, b) => {
    const regionOrder = a.origin_region_id.localeCompare(b.origin_region_id);
    if (regionOrder !== 0) return regionOrder;
    const stationOrder = String(a.origin_station_name ?? '').localeCompare(String(b.origin_station_name ?? ''));
    if (stationOrder !== 0) return stationOrder;
    const thresholdOrder = Number(a.threshold_min ?? 0) - Number(b.threshold_min ?? 0);
    if (thresholdOrder !== 0) return thresholdOrder;
    return String(a.station_name ?? '').localeCompare(String(b.station_name ?? ''));
  });

  const stationBuckets = new Map<string, Subway750CurveCandidateRow[]>();
  for (const row of numericRows) {
    const key = getSubwayStationKey(row);
    const bucket = stationBuckets.get(key) ?? [];
    bucket.push(row);
    stationBuckets.set(key, bucket);
  }

  const table = Array.from(stationBuckets.entries()).map(([key, bucket]) => {
    const [, , station_name] = key.split('|');
    const lastRow = bucket[bucket.length - 1] ?? bucket[0];
    return {
      station_name,
      origin_station_line: lastRow.origin_station_line ?? null,
      station_count: bucket.length,
      mean_population_750m: bucket.reduce((sum, row) => sum + Number(row.population_750m ?? 0), 0) / Math.max(bucket.length, 1),
      mean_worker_750m: bucket.reduce((sum, row) => sum + Number(row.worker_750m ?? 0), 0) / Math.max(bucket.length, 1),
      max_population_750m: Math.max(...bucket.map((row) => Number(row.population_750m ?? 0))),
      max_worker_750m: Math.max(...bucket.map((row) => Number(row.worker_750m ?? 0))),
      representative_line_name: String(lastRow.line_name ?? ''),
      representative_node_id: Number(lastRow.node_id ?? 0),
      station_total_population_750m: bucket.reduce((sum, row) => sum + Number(row.population_750m ?? 0), 0),
      station_total_worker_750m: bucket.reduce((sum, row) => sum + Number(row.worker_750m ?? 0), 0),
    };
  });

  return {
    table,
    selected: [],
    candidates: earliestRows,
  };
}

function sumSubwayCandidates(rows: Subway750CurveCandidateRow[], stationName: '판교' | '복정', minute: number, metric: MetricMode) {
  return rows
    .filter((row) => stationLabelMatches(row.origin_station_name, stationName) && Number(row.threshold_min ?? 0) <= minute)
    .reduce((sum, row) => sum + Number(metric === 'workers' ? row.worker_750m ?? 0 : row.population_750m ?? 0), 0);
}

function buildSubwayCurveRows(rows: Subway750CurveCandidateRow[], stationName: '판교' | '복정', metric: MetricMode) {
  const filtered = rows.filter((row) => stationLabelMatches(row.origin_station_name, stationName));
  if (!filtered.length) {
    return [
      {
        origin_region_id: `${stationName}_subway_750m`,
        origin_station_name: stationName,
        station_label: `${stationName}역`,
        mode: 'subway' as TransportMode,
        threshold_min: 0,
        accessible_population: 0,
        accessible_workers: 0,
        accessible_businesses: 0,
        reachable_station_count: 0,
        reachable_link_count: 0,
        accessible_area_km2: 0,
      },
    ] as AccessibilityRow[];
  }

  const points: AccessibilityRow[] = [];
  for (let minute = 0; minute <= 60; minute += 5) {
    const value = sumSubwayCandidates(filtered, stationName, minute, metric);
    points.push({
      origin_region_id: `${stationName}_subway_750m`,
      origin_station_name: stationName,
      station_label: `${stationName}역`,
      mode: 'subway' as TransportMode,
      threshold_min: minute,
      accessible_population: metric === 'population' ? value : 0,
      accessible_workers: metric === 'workers' ? value : 0,
      accessible_businesses: 0,
      reachable_station_count: 0,
      reachable_link_count: 0,
      accessible_area_km2: 0,
    });
  }
  return points;
}

function buildRegionData(
  regionId: RegionId,
  raw: {
    planningLanduse: GeoJson;
    scopeLanduse: GeoJson;
    fullBoundary: GeoJson;
    coreBoundary: GeoJson;
    supportBoundary: GeoJson;
    stationMarkers: GeoJson;
    isochrones: GeoJson;
    subwayNetworkNodes: GeoJson;
    subwayNetworkRoutes: GeoJson;
    subwayLineNetwork: GeoJson;
    subwayReachStations: GeoJson;
    busStations: GeoJson;
    busPathEdges: GeoJson;
    buildingsFull: GeoJson;
    buildingsCore: GeoJson;
    sgisCoreRows: SgisRow[];
    accessibilityRows: AccessibilityRow[];
    corePerformanceRows: PerformanceRowV14[];
    planningPerformanceRows: PerformanceRowV14[];
    buildingSummaryRows: BuildingSummaryRow[];
    buildingGisRows: BuildingGisRow[];
  },
): RegionData {
  const meta = REGION_META[regionId];
  const prefix = regionId === 'pangyo' ? 'pangyo' : 'wirye';
  const busOriginKey = regionId === 'pangyo' ? 'pangyo' : 'bokjeong';
  const planningLanduse = filterFeatureCollection(raw.planningLanduse, (feature) => stationMatches(regionId, feature) || String(feature.properties?.region_id ?? '').includes(prefix));
  const scopeLanduse = filterFeatureCollection(raw.scopeLanduse, (feature) => String(feature.properties?.region_id ?? '').includes(prefix));
  const fullBoundary = filterFeatureCollection(raw.fullBoundary, (feature) => String(feature.properties?.region_id ?? '').includes(prefix));
  const coreBoundary = filterFeatureCollection(raw.coreBoundary, (feature) => String(feature.properties?.region_id ?? '').includes(prefix));
  const supportBoundary = filterFeatureCollection(raw.supportBoundary, (feature) => String(feature.properties?.region_id ?? '').includes(prefix));
  const stationMarkers = filterFeatureCollection(raw.stationMarkers, (feature) => String(feature.properties?.marker_region ?? '').includes(prefix) || stationMatches(regionId, feature));
  const isochrones = filterFeatureCollection(raw.isochrones, (feature) => String(feature.properties?.origin_region_id ?? '').includes(prefix) && stationMatches(regionId, feature));
  const subwayNetworkNodes = filterFeatureCollection(raw.subwayNetworkNodes, (feature) => String(feature.properties?.origin_region_id ?? '').includes(prefix));
  const subwayNetworkRoutes = filterFeatureCollection(raw.subwayNetworkRoutes, (feature) => String(feature.properties?.origin_region_id ?? '').includes(prefix));
  const subwayLineNetwork = filterFeatureCollection(raw.subwayLineNetwork, (feature) => String(feature.properties?.line_name ?? feature.properties?.linenm ?? '').length > 0);
  const subwayReachStations = dedupeFeatureCollection(
    filterFeatureCollection(raw.subwayReachStations, (feature) => String(feature.properties?.origin_region_id ?? '').includes(prefix)),
    (feature) => normalizeStationLabel(feature.properties?.station_name ?? feature.properties?.station_label ?? ''),
    (feature) => Number(feature.properties?.travel_time_min ?? feature.properties?.min_travel_time_min ?? feature.properties?.selected_travel_time_min ?? feature.properties?.threshold_min ?? 0),
  );
  const busStations = dedupeFeatureCollection(
    filterFeatureCollection(raw.busStations, (feature) => String(feature.properties?.origin_key ?? '') === busOriginKey || stationMatches(regionId, feature)),
    (feature) => `${String(feature.properties?.origin_key ?? busOriginKey)}|${String(feature.properties?.target_station_id ?? feature.properties?.station_name ?? feature.properties?.station_label ?? '')}`,
    (feature) => Number(feature.properties?.travel_time_min ?? feature.properties?.raw_network_time_min ?? feature.properties?.time_min ?? 0),
  );
  const busPathEdges = filterFeatureCollection(raw.busPathEdges, (feature) => String(feature.properties?.origin_key ?? '') === busOriginKey || stationMatches(regionId, feature));
  const buildingsFull = mapFeatureCollection(
    filterFeatureCollection(raw.buildingsFull, (feature) => String(feature.properties?.region_group ?? '').includes(prefix) || String(feature.properties?.region_id ?? '').includes(prefix)),
    (feature) => ({
      properties: {
        fill_color: BUILDING_COLORS[String(feature.properties?.main_use_group ?? 'unknown')] ?? BUILDING_COLORS.unknown,
        building_label: feature.properties?.building_label ?? feature.properties?.buld_nm ?? feature.properties?.gis_building_id ?? '건물',
      },
    }),
  );
  const buildingsCore = mapFeatureCollection(
    filterFeatureCollection(raw.buildingsCore, (feature) => String(feature.properties?.region_group ?? '').includes(prefix) || String(feature.properties?.region_id ?? '').includes(prefix)),
    (feature) => ({
      properties: {
        fill_color: BUILDING_COLORS[String(feature.properties?.main_use_group ?? 'unknown')] ?? BUILDING_COLORS.unknown,
        building_label: feature.properties?.building_label ?? feature.properties?.buld_nm ?? feature.properties?.gis_building_id ?? '건물',
      },
    }),
  );

  const landusePlanningSlices = summarizeByKey(planningLanduse.features, (props) => String(props.category_group ?? props.zone_group ?? props.planned_use_group ?? 'unknown'), (props) => Number(props.area_m2 ?? 0));
  const landuseScopeSlices = {
    planning: landusePlanningSlices,
    core: summarizeByKey(scopeLanduse.features.filter((feature) => String(feature.properties?.boundary_role ?? 'core') === 'core'), (props) => String(props.planned_use_group ?? props.category_group ?? 'unknown'), (props) => Number(props.area_m2 ?? 0)),
    station: summarizeByKey(scopeLanduse.features.filter((feature) => String(feature.properties?.boundary_role ?? '') === 'station_support'), (props) => String(props.planned_use_group ?? props.category_group ?? 'unknown'), (props) => Number(props.area_m2 ?? 0)),
  };

  const buildingSummaryFull = raw.buildingSummaryRows.find((row) => row.region_group === `${prefix}_full`) ?? null;
  const buildingSummaryCore = raw.buildingSummaryRows.find((row) => row.region_group === `${prefix}_core`) ?? null;
  const buildingGisFull = raw.buildingGisRows.find((row) => row.region_group === `${prefix}_full`) ?? null;
  const buildingGisCore = raw.buildingGisRows.find((row) => row.region_group === `${prefix}_core`) ?? null;
  const planningPerformance = raw.planningPerformanceRows.find((row) => row.region_id === `${prefix}_station_support_zone`) ?? null;
  const corePerformance = raw.corePerformanceRows.find((row) => row.region_id === `${prefix}_core`) ?? null;
  const sgisCore = raw.sgisCoreRows.find((row) => row.region_id === `${prefix}_core`) ?? null;
  const sgisAnalysis = sgisCore;

  return {
    id: regionId,
    label: meta.label,
    shortLabel: meta.shortLabel,
    stationName: meta.stationName,
    center: meta.center,
    planningLanduse,
    scopeLanduse,
    fullBoundary,
    coreBoundary,
    supportBoundary,
    stationMarkers,
    isochrones,
    subwayNetworkNodes,
    subwayNetworkRoutes,
    subwayLineNetwork,
    subwayReachStations,
    busStations,
    busPathEdges,
    buildingsFull,
    buildingsCore,
    landusePlanningSlices,
    landuseScopeSlices,
    buildingSummaryFull,
    buildingSummaryCore,
    buildingGisFull,
    buildingGisCore,
    planningPerformance,
    corePerformance,
    sgisCore,
    sgisAnalysis,
  };
}

function SectionTitle({ kicker, title, subtitle }: { kicker: string; title: string; subtitle: string }) {
  return (
    <div className="section-title">
      <div>
        <div className="section-kicker">{kicker}</div>
        <h2>{title}</h2>
        {subtitle ? <p>{subtitle}</p> : null}
      </div>
    </div>
  );
}

function MetricCard({
  icon,
  title,
  tooltip,
  leftLabel,
  leftValue,
  rightLabel,
  rightValue,
  note,
}: {
  icon: ReactNode;
  title: string;
  tooltip: string;
  leftLabel: string;
  leftValue: string;
  rightLabel: string;
  rightValue: string;
  note: string;
}) {
  return (
    <article className="metric-card">
      <div className="metric-top">
        <div className="metric-icon">{icon}</div>
        <div>
          <div className="metric-title-row">
            <h3>{title}</h3>
            <span className="metric-help" title={tooltip}>
              ?
            </span>
          </div>
          <p>{note}</p>
        </div>
      </div>
      <div className="metric-values">
        <div>
          <span>{leftLabel}</span>
          <strong>{leftValue}</strong>
        </div>
        <div>
          <span>{rightLabel}</span>
          <strong>{rightValue}</strong>
        </div>
      </div>
    </article>
  );
}

function ToggleButton({
  label,
  active,
  onClick,
  icon,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  icon: ReactNode;
}) {
  return (
    <button type="button" className={`toggle-button ${active ? 'active' : ''}`} onClick={onClick}>
      <span className="toggle-button-icon">{icon}</span>
      <span>{label}</span>
    </button>
  );
}

function DonutPanel({ label, slices }: { label: string; slices: Slice[] }) {
  const total = slices.reduce((sum, item) => sum + item.value, 0);
  const viewBox = 164;
  const cx = 82;
  const cy = 82;
  const outer = 68;
  const inner = 38;
  let cursor = -90;
  const paths = slices.map((slice, index) => {
    const share = total > 0 ? slice.value / total : 0;
    const angle = Math.max(share * 360, share > 0 ? 2 : 0);
    const start = cursor;
    const end = cursor + angle;
    cursor = end;
    const startRad = (Math.PI / 180) * start;
    const endRad = (Math.PI / 180) * end;
    const x1 = cx + outer * Math.cos(startRad);
    const y1 = cy + outer * Math.sin(startRad);
    const x2 = cx + outer * Math.cos(endRad);
    const y2 = cy + outer * Math.sin(endRad);
    const ix1 = cx + inner * Math.cos(endRad);
    const iy1 = cy + inner * Math.sin(endRad);
    const ix2 = cx + inner * Math.cos(startRad);
    const iy2 = cy + inner * Math.sin(startRad);
    const largeArc = angle > 180 ? 1 : 0;
    const d = [`M ${x1.toFixed(2)} ${y1.toFixed(2)}`, `A ${outer} ${outer} 0 ${largeArc} 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`, `L ${ix1.toFixed(2)} ${iy1.toFixed(2)}`, `A ${inner} ${inner} 0 ${largeArc} 0 ${ix2.toFixed(2)} ${iy2.toFixed(2)}`, 'Z'].join(' ');
    return <path key={`${label}-${index}`} d={d} fill={slice.color} stroke="white" strokeWidth={1.2} />;
  });
  return (
    <div className="donut-panel">
      <div className="donut-label">{label}</div>
      <svg viewBox={`0 0 ${viewBox} ${viewBox}`} aria-label={label}>
        <circle cx={cx} cy={cy} r={inner - 2} fill="#f8fbff" />
        {paths}
      </svg>
      <div className="donut-mini-legend">
        {slices.slice(0, 4).map((slice) => (
          <div key={`${label}-${slice.label}`} className="donut-mini-row">
            <span className="dot" style={{ background: slice.color }} />
            <span>{slice.label}</span>
            <strong>{formatPercent(slice.share)}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

function PieChartCard({
  title,
  subtitle,
  leftLabel,
  rightLabel,
  left,
  right,
  valueMode,
  legendName,
}: {
  title: string;
  subtitle: string;
  leftLabel: string;
  rightLabel: string;
  left: Slice[];
  right: Slice[];
  valueMode: string;
  legendName: string;
}) {
  return (
    <section className="chart-card panel-card">
      <div className="chart-head">
        <div>
          <div className="chart-kicker">
            <BarChart3 size={14} />
            <span>{subtitle}</span>
          </div>
          <h3>{title}</h3>
        </div>
        <div className="chart-chip">{valueMode}</div>
      </div>
      <div className="pie-comparison">
        <DonutPanel label={leftLabel} slices={left} />
        <DonutPanel label={rightLabel} slices={right} />
      </div>
      <div className="chart-legend">
        <span>{legendName}</span>
        {left.slice(0, 5).map((item) => (
          <span key={`${title}-${item.label}`}>
            <i style={{ background: item.color }} />
            {item.label}
          </span>
        ))}
      </div>
    </section>
  );
}

function LineChartCard({
  rows,
  mode,
  metric,
  selectedTime,
  onModeChange,
  onMetricChange,
}: {
  rows: AccessibilityRow[];
  mode: TransportMode;
  metric: MetricMode;
  selectedTime: number;
  onModeChange: (mode: TransportMode) => void;
  onMetricChange: (metric: MetricMode) => void;
}) {
  const pangyo = rows.filter((row) => row.origin_station_name === '판교' && row.mode === mode).sort((a, b) => Number(a.threshold_min) - Number(b.threshold_min));
  const bokjeong = rows.filter((row) => row.origin_station_name === '복정' && row.mode === mode).sort((a, b) => Number(a.threshold_min) - Number(b.threshold_min));
  const series = (source: AccessibilityRow[]) => source.map((row) => ({ minute: Number(row.threshold_min), value: metric === 'workers' ? Number(row.accessible_workers ?? 0) : Number(row.accessible_population ?? 0) }));
  const left = series(pangyo);
  const right = series(bokjeong);
  const maxY = Math.max(...[...left, ...right].map((row) => row.value), 1);
  const width = 1000;
  const height = 220;
  const pad = { left: 48, right: 18, top: 14, bottom: 28 };
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const x = (minute: number) => pad.left + (minute / 60) * plotWidth;
  const y = (value: number) => pad.top + (1 - value / maxY) * plotHeight;
  const pathFor = (points: { minute: number; value: number }[]) => points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${x(point.minute).toFixed(2)} ${y(point.value).toFixed(2)}`).join(' ');
  const currentX = x(selectedTime);
  const selectedLeft = getCurveValue(rows, '판교', mode, selectedTime, metric);
  const selectedRight = getCurveValue(rows, '복정', mode, selectedTime, metric);
  const subwayMode = mode === 'subway';
  const chartTitle = '누적 접근성 곡선';
  const chartDesc = '소요시간 t분 이내 도달가능 인구·종사자를 t에 대한 곡선으로 표현합니다.';
  const axisLabel = subwayMode ? '도보권 단계(750m)' : '이동 시간(분)';
  const guideText = `${selectedTime}분`;
  const legendScope = subwayMode ? '지하철역 기준 반경 750m' : '버스 정류장 기준 반경 500m';
  const legendMetric = metric === 'workers' ? '종사자 수' : '거주 인구수';
  return (
    <section className="chart-card panel-card curve-card">
      <div className="chart-head">
        <div>
          <div className="chart-kicker">
            <Activity size={14} />
            <span>{subwayMode ? '지하철 750m 기준' : '버스 500m 기준'}</span>
          </div>
          <h3>{chartTitle}</h3>
          <p>{chartDesc}</p>
        </div>
        <div className="curve-controls">
          <SegmentedControl label="수단" value={mode} options={[{ value: 'subway', label: '지하철' }, { value: 'bus', label: '버스' }]} onChange={(value) => onModeChange(value as TransportMode)} />
          <SegmentedControl label="지표" value={metric} options={[{ value: 'workers', label: '도달 종사자' }, { value: 'population', label: '도달 인구' }]} onChange={(value) => onMetricChange(value as MetricMode)} />
        </div>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="curve-svg" role="img" aria-label={subwayMode ? '지하철 750m 도보권 누적 접근성 곡선' : '누적 접근성 곡선'}>
        {[0, 0.25, 0.5, 0.75, 1].map((t) => {
          const yy = pad.top + t * plotHeight;
          const value = maxY * (1 - t);
          return (
            <g key={t}>
              <line x1={pad.left} x2={width - pad.right} y1={yy} y2={yy} className="curve-grid" />
              <text x={10} y={yy + 4} className="curve-axis-label">
                {formatCompactNumber(value, 1)}
              </text>
            </g>
          );
        })}
        {Array.from({ length: 13 }, (_, index) => index * 5).map((minute) => (
          <line key={minute} x1={x(minute)} x2={x(minute)} y1={pad.top} y2={height - pad.bottom} className="curve-grid" />
        ))}
        <line x1={currentX} x2={currentX} y1={pad.top} y2={height - pad.bottom} className="curve-guide" />
        <text x={currentX + 6} y={pad.top + 12} className="curve-guide-label">
          {guideText}
        </text>
        <path d={pathFor(left)} fill="none" stroke="#1e62d0" strokeWidth={3} strokeLinecap="round" strokeLinejoin="round" />
        <path d={pathFor(right)} fill="none" stroke="#ef6f19" strokeWidth={3} strokeLinecap="round" strokeLinejoin="round" />
        {left.map((point, index) => <circle key={`l-${index}`} cx={x(point.minute)} cy={y(point.value)} r={3.5} fill="#1e62d0" />)}
        {right.map((point, index) => <circle key={`r-${index}`} cx={x(point.minute)} cy={y(point.value)} r={3.5} fill="#ef6f19" />)}
        <text x={width / 2} y={height - 10} textAnchor="middle" className="curve-axis-label">
          {axisLabel}
        </text>
      </svg>
      <div className="curve-legend">
        <span>
          <i style={{ background: '#1e62d0' }} />
          {`판교역 ${legendScope} ${legendMetric}`}
        </span>
        <span>
          <i style={{ background: '#ef6f19' }} />
          {`복정역 ${legendScope} ${legendMetric}`}
        </span>
        <span className="muted">수직 가이드: {guideText}</span>
      </div>
    </section>
  );
}

function SegmentedControl({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
}) {
  return (
    <div className="segmented-group">
      <span className="segmented-label">{label}</span>
      <div className="segmented-control">
        {options.map((option) => (
          <button key={option.value} type="button" className={value === option.value ? 'active' : ''} onClick={() => onChange(option.value)}>
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function MapView({
  region,
  selectedMode,
  selectedTime,
  layers,
  scopeMode,
  selected,
  onPickFeature,
}: {
  region: RegionData;
  selectedMode: TransportMode;
  selectedTime: number;
  layers: LayerFlags;
  scopeMode: ScopeMode;
  selected: SelectedFeature | null;
  onPickFeature: (feature: SelectedFeature) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [fallback, setFallback] = useState(false);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [overlayMarkup, setOverlayMarkup] = useState('');
  const activeLanduse = scopeMode === 'planning' ? region.planningLanduse : region.scopeLanduse;
  const displayMinute = selectedTime;
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: { version: 8, sources: {}, layers: [] },
      center: region.center,
      zoom: region.id === 'pangyo' ? 13.55 : 13.35,
      minZoom: 11,
      maxZoom: 18.5,
      attributionControl: false,
      pitchWithRotate: false,
      dragRotate: false,
      touchZoomRotate: false,
    });
    mapRef.current = map;
    ((window as any).__smartcityMaps ??= {})[region.id] = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    map.addControl(new maplibregl.ScaleControl({ maxWidth: 120, unit: 'metric' }), 'bottom-right');
    map.on('load', () => {
      try {
        setMapLoaded(true);
        map.addSource('basemap', {
          type: 'raster',
          tiles: [OSM_TILE_URL],
          tileSize: 256,
        });
        map.addLayer({
          id: 'basemap',
          type: 'raster',
          source: 'basemap',
          paint: {
            'raster-opacity': 1,
            'raster-brightness-min': 0.82,
            'raster-brightness-max': 0.98,
          },
        });
        const addSource = (id: string, data: GeoJson) => map.addSource(id, { type: 'geojson', data });
        addSource('landuse', cloneFeatureCollection(activeLanduse));
        addSource('full-boundary', cloneFeatureCollection(region.fullBoundary));
        addSource('core-boundary', cloneFeatureCollection(region.coreBoundary));
        addSource('support-boundary', cloneFeatureCollection(region.supportBoundary));
        addSource('markers', cloneFeatureCollection(region.stationMarkers));
        addSource('isochrones', cloneFeatureCollection(region.isochrones));
        addSource('subway-network-routes', cloneFeatureCollection(region.subwayNetworkRoutes));
        addSource('subway-network-nodes', cloneFeatureCollection(region.subwayNetworkNodes));
        addSource('subway-line-network', cloneFeatureCollection(region.subwayLineNetwork));
        addSource('subway-reach-stations', cloneFeatureCollection(region.subwayReachStations));
        addSource('bus-stations', cloneFeatureCollection(region.busStations));
        addSource('bus-path-edges', cloneFeatureCollection(region.busPathEdges));
        addSource('buildings-full', cloneFeatureCollection(region.buildingsFull));
        addSource('buildings-core', cloneFeatureCollection(region.buildingsCore));

        map.addLayer({
          id: 'landuse-fill',
          type: 'fill',
          source: 'landuse',
          paint: {
            'fill-color': [
              'match',
              ['coalesce', ['get', 'display_color_key'], ['get', 'category_group'], ['get', 'zone_group'], ['get', 'planned_use_group'], ['get', 'block_type']],
              '업무·도시지원',
              '#65b8ff',
              '준주거·혼합',
              '#38bdf8',
              '상업',
              '#ef4444',
              '주거',
              '#f4c84a',
              '녹지·공원',
              '#22c55e',
              '공공·교육',
              '#8b5cf6',
              '교통·기타',
              '#64748b',
              '#cbd5e1',
            ],
            'fill-opacity': 0.42,
            'fill-outline-color': 'rgba(255,255,255,0.92)',
          },
        });
        map.addLayer({ id: 'landuse-outline-shadow', type: 'line', source: 'landuse', paint: { 'line-color': 'rgba(15, 23, 42, 0.14)', 'line-width': 1.2 } });
        map.addLayer({ id: 'landuse-line', type: 'line', source: 'landuse', paint: { 'line-color': 'rgba(255,255,255,0.9)', 'line-width': 0.75 } });
        map.addLayer({ id: 'buildings-full-fill', type: 'fill', source: 'buildings-full', paint: { 'fill-color': ['coalesce', ['get', 'fill_color'], '#94a3b8'], 'fill-opacity': 0.1, 'fill-outline-color': '#ffffff' } });
        map.addLayer({ id: 'buildings-full-line', type: 'line', source: 'buildings-full', paint: { 'line-color': '#64748b', 'line-width': 0.6 } });
        map.addLayer({ id: 'buildings-core-fill', type: 'fill', source: 'buildings-core', paint: { 'fill-color': ['coalesce', ['get', 'fill_color'], '#94a3b8'], 'fill-opacity': 0.12, 'fill-outline-color': '#ffffff' } });
        map.addLayer({ id: 'buildings-core-line', type: 'line', source: 'buildings-core', paint: { 'line-color': '#475569', 'line-width': 0.7 } });
        map.addLayer({ id: 'full-boundary-line', type: 'line', source: 'full-boundary', paint: { 'line-color': '#1f3f8a', 'line-width': 2.4 } });
        map.addLayer({ id: 'core-boundary-line', type: 'line', source: 'core-boundary', paint: { 'line-color': '#ef4444', 'line-width': 2, 'line-dasharray': [2, 2] } });
        map.addLayer({
          id: 'bus-route-network',
          type: 'line',
          source: 'bus-path-edges',
          paint: {
            'line-color': '#e85d04',
            'line-width': 2.1,
            'line-opacity': 0.68,
          },
          layout: {
            'line-cap': 'round',
            'line-join': 'round',
            visibility: 'none',
          },
          filter: ['all', ['==', ['get', 'mode'], 'bus'], ['==', ['get', 'origin_key'], region.id === 'pangyo' ? 'pangyo' : 'bokjeong'], ['<=', ['to-number', ['get', 'travel_time_min']], selectedTime]],
        });
        map.addLayer({
          id: 'bus-station-points',
          type: 'circle',
          source: 'bus-stations',
          paint: {
            'circle-radius': 4,
            'circle-color': '#1d4ed8',
            'circle-stroke-color': '#ffffff',
            'circle-stroke-width': 1.5,
            'circle-opacity': 1,
          },
          filter: ['all', ['==', ['get', 'origin_key'], region.id === 'pangyo' ? 'pangyo' : 'bokjeong'], ['<=', ['to-number', ['get', 'travel_time_min']], selectedTime]],
        });
        map.addLayer({ id: 'subway-selected-line', type: 'line', source: 'subway-network-routes', paint: { 'line-color': '#0f4fb8', 'line-width': 4.8, 'line-opacity': 0.96 }, layout: { 'line-cap': 'round', 'line-join': 'round' }, filter: ['all', ['==', ['get', 'kind'], 'subway'], ['<=', ['to-number', ['coalesce', ['get', 'cumulative_time_min'], ['get', 'travel_time_min'], ['get', 'threshold_min'], 0]], selectedTime], ['==', ['get', 'origin_region_id'], region.id === 'pangyo' ? 'pangyo_core' : 'wirye_core']] });
        map.addLayer({
          id: 'subway-line-network',
          type: 'line',
          source: 'subway-line-network',
          paint: {
            'line-color': ['coalesce', ['get', 'color'], '#1e62d0'],
            'line-width': ['interpolate', ['linear'], ['zoom'], 11, 1.2, 13, 1.8, 15, 2.6, 17, 3.2],
            'line-opacity': 0.4,
          },
          layout: { 'line-cap': 'round', 'line-join': 'round' },
        });
        map.addLayer({ id: 'subway-selected-node', type: 'circle', source: 'subway-reach-stations', paint: { 'circle-radius': 5.1, 'circle-color': '#dbeafe', 'circle-stroke-color': '#0f4fb8', 'circle-stroke-width': 1.6, 'circle-opacity': 0.98 }, filter: ['all', ['==', ['get', 'origin_region_id'], region.id === 'pangyo' ? 'pangyo_core' : 'wirye_core'], subwayPointTimeFilterExpression(selectedTime)] });
        map.addLayer({ id: 'bus30-fill', type: 'fill', source: 'isochrones', paint: { 'fill-color': TRANSPORT_FILL.bus, 'fill-opacity': 0.04, 'fill-outline-color': 'rgba(255,255,255,0.25)' }, layout: { visibility: 'none' }, filter: ['all', ['==', ['get', 'mode'], 'bus'], ['==', ['to-number', ['get', 'threshold_min']], 30], ['==', ['get', 'origin_region_id'], region.id === 'pangyo' ? 'pangyo_core' : 'wirye_core']] });
        map.addLayer({ id: 'bus30-line', type: 'line', source: 'isochrones', paint: { 'line-color': '#0f766e', 'line-width': 3.4, 'line-opacity': 0.8 }, layout: { 'line-cap': 'round', 'line-join': 'round', visibility: 'none' }, filter: ['all', ['==', ['get', 'mode'], 'bus'], ['==', ['to-number', ['get', 'threshold_min']], 30], ['==', ['get', 'origin_region_id'], region.id === 'pangyo' ? 'pangyo_core' : 'wirye_core']] });
        map.addLayer({ id: 'bus60-fill', type: 'fill', source: 'isochrones', paint: { 'fill-color': 'rgba(179, 145, 255, 0.03)', 'fill-opacity': 0.02, 'fill-outline-color': 'rgba(255,255,255,0.22)' }, layout: { visibility: 'none' }, filter: ['all', ['==', ['get', 'mode'], 'bus'], ['==', ['to-number', ['get', 'threshold_min']], 60], ['==', ['get', 'origin_region_id'], region.id === 'pangyo' ? 'pangyo_core' : 'wirye_core']] });
        map.addLayer({ id: 'bus60-line', type: 'line', source: 'isochrones', paint: { 'line-color': '#9bd5cf', 'line-width': 2.4, 'line-opacity': 0.55, 'line-dasharray': [2, 2] }, layout: { 'line-cap': 'round', 'line-join': 'round', visibility: 'none' }, filter: ['all', ['==', ['get', 'mode'], 'bus'], ['==', ['to-number', ['get', 'threshold_min']], 60], ['==', ['get', 'origin_region_id'], region.id === 'pangyo' ? 'pangyo_core' : 'wirye_core']] });
        map.addLayer({ id: 'selected-subway-line', type: 'line', source: 'subway-network-routes', paint: { 'line-color': '#0b3f99', 'line-width': 6.4, 'line-opacity': 0.98 }, layout: { 'line-cap': 'round', 'line-join': 'round' }, filter: ['all', ['==', ['get', 'kind'], 'subway'], ['<=', ['to-number', ['coalesce', ['get', 'cumulative_time_min'], ['get', 'travel_time_min'], ['get', 'threshold_min'], 0]], selectedTime], ['==', ['get', 'origin_region_id'], region.id === 'pangyo' ? 'pangyo_core' : 'wirye_core']] });
        map.addLayer({ id: 'selected-bus-line', type: 'line', source: 'isochrones', paint: { 'line-color': '#0f766e', 'line-width': 4.2, 'line-opacity': 0.5 }, layout: { 'line-cap': 'round', 'line-join': 'round', visibility: 'none' }, filter: ['==', ['get', 'origin_region_id'], '__none__'] });
        map.addLayer({ id: 'markers-circle', type: 'circle', source: 'markers', paint: { 'circle-radius': 9, 'circle-color': '#ffffff', 'circle-stroke-color': '#1e62d0', 'circle-stroke-width': 4 } });
        map.addLayer({ id: 'markers-label', type: 'symbol', source: 'markers', layout: { 'text-field': ['get', 'marker_label'], 'text-size': 12, 'text-offset': [0, 1.25], 'text-anchor': 'top', 'text-allow-overlap': true }, paint: { 'text-color': '#0f2d66', 'text-halo-color': '#ffffff', 'text-halo-width': 2.5 } });

        const bounds = featureCollectionBounds(region.fullBoundary) ?? featureCollectionBounds(region.planningLanduse) ?? featureCollectionBounds(region.scopeLanduse);
        if (bounds) map.fitBounds(bounds, { padding: 18, duration: 0, maxZoom: region.id === 'pangyo' ? 15.6 : 15.3 });

        const clickable = ['landuse-fill', 'subway30-fill', 'subway60-fill', 'bus30-fill', 'bus60-fill', 'buildings-full-fill', 'buildings-core-fill', 'markers-circle', 'markers-label', 'subway-selected-line', 'subway-selected-node', 'bus-station-points', 'bus-route-network'];
        for (const layerId of clickable) {
          map.on('mouseenter', layerId, () => (map.getCanvas().style.cursor = 'pointer'));
          map.on('mouseleave', layerId, () => (map.getCanvas().style.cursor = ''));
        }
        map.on('click', (event) => {
          const landuseMatches = map.queryRenderedFeatures(event.point, { layers: ['landuse-fill'] });
          const buildingMatches = map.queryRenderedFeatures(event.point, { layers: ['buildings-core-fill', 'buildings-full-fill'] });
          const routeMatches = map.queryRenderedFeatures(event.point, { layers: ['subway-selected-line', 'subway-selected-node', 'bus-route-network', 'bus-station-points'] });
          const isochroneMatches = layers.accessibilityBuffer ? map.queryRenderedFeatures(event.point, { layers: ['subway30-fill', 'subway60-fill', 'bus30-fill', 'bus60-fill'] }) : [];
          const markerMatches = map.queryRenderedFeatures(event.point, { layers: ['markers-circle', 'markers-label'] });
          const landuseFeature = landuseMatches[0];
          if (landuseFeature) {
            onPickFeature({ kind: 'landuse', regionId: region.id, title: String(landuseFeature.properties?.planned_use_detail ?? landuseFeature.properties?.zone_name ?? '용도지역'), properties: landuseFeature.properties ?? {} });
            return;
          }
          const buildingFeature = buildingMatches[0];
          if (buildingFeature) {
            onPickFeature({ kind: 'building', regionId: region.id, title: String(buildingFeature.properties?.building_label ?? buildingFeature.properties?.buld_nm ?? '건물'), properties: buildingFeature.properties ?? {} });
            return;
          }
          const routeFeature = routeMatches[0];
          if (routeFeature) {
            onPickFeature({ kind: 'network', regionId: region.id, title: `${getNetworkOrigin(routeFeature.properties ?? {})} → ${getNetworkTarget(routeFeature.properties ?? {})}`.trim(), properties: routeFeature.properties ?? {} });
            return;
          }
          const isochroneFeature = isochroneMatches[0];
          if (isochroneFeature) {
            onPickFeature({ kind: 'isochrone', regionId: region.id, title: `${getIsoStation(isochroneFeature.properties ?? {})} ${getIsoMode(isochroneFeature.properties ?? {})} ${getIsoMinute(isochroneFeature.properties ?? {})}분`, properties: isochroneFeature.properties ?? {} });
            return;
          }
          const markerFeature = markerMatches[0];
          if (markerFeature) {
            onPickFeature({ kind: 'network', regionId: region.id, title: String(markerFeature.properties?.marker_label ?? markerFeature.properties?.station_label ?? '핵심역'), properties: markerFeature.properties ?? {} });
          }
        });
      } catch {
        setFallback(true);
      }
    });
    return () => {
      delete (window as any).__smartcityMaps?.[region.id];
      map.remove();
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const container = containerRef.current;
    if (!map || !container || fallback || !mapLoaded) return;
    let raf = 0;
    const updateOverlay = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const width = container.clientWidth;
        const height = container.clientHeight;
        if (!width || !height || !map) return;
        const layersEnabled = layers.landuse;
        const landuseFeatures = layersEnabled ? asFeatureCollection(activeLanduse).features : [];
        const landusePaths: string[] = [];
        for (const feature of landuseFeatures) {
          const geometry = feature.geometry;
          const props = feature.properties ?? {};
          const fill = getLanduseFillColor(props);
          const fillOpacity = getLanduseFillOpacity(props);
          const paths = geometryToSvgPaths(geometry, (coord) => map.project(coord as [number, number]));
          for (const d of paths) {
            landusePaths.push(
              `<path d="${d}" fill="${fill}" fill-opacity="${fillOpacity.toFixed(2)}" stroke="rgba(255,255,255,0.98)" stroke-width="0.7" vector-effect="non-scaling-stroke" />`,
            );
          }
        }
        const subwayLineMarkup = asFeatureCollection(region.subwayLineNetwork).features
          .flatMap((feature) => {
            const lineStyle = String(feature.properties?.style ?? '');
            const dashAttr = lineStyle === 'dashed' ? ' stroke-dasharray="8 6"' : '';
            return geometryToSvgPaths(feature.geometry, (coord) => map.project(coord as [number, number])).map(
              (d) =>
                `<path d="${d}" fill="none" stroke="#0f4fb8" stroke-opacity="0.72" stroke-width="3.2"${dashAttr} vector-effect="non-scaling-stroke" />`,
            );
          })
          .join('');
        const originRegion = region.id === 'pangyo' ? 'pangyo_core' : 'wirye_core';
        const boundaryPaths = asFeatureCollection(region.fullBoundary).features.flatMap((feature) => geometryToSvgPaths(feature.geometry, (coord) => map.project(coord as [number, number])));
        const boundaryMarkup = boundaryPaths
          .map((d) => `<path d="${d}" fill="none" stroke="rgba(31,63,138,0.9)" stroke-width="2.2" vector-effect="non-scaling-stroke" />`)
          .join('');
        const coreMarkup = asFeatureCollection(region.coreBoundary).features
          .flatMap((feature) => geometryToSvgPaths(feature.geometry, (coord) => map.project(coord as [number, number])))
          .map((d) => `<path d="${d}" fill="none" stroke="rgba(239,68,68,0.88)" stroke-width="2" stroke-dasharray="5 4" vector-effect="non-scaling-stroke" />`)
          .join('');
        const supportMarkup = '';
        const markerMarkup = asFeatureCollection(region.stationMarkers).features
          .flatMap((feature) => {
            const coords = feature.geometry?.coordinates;
            if (!Array.isArray(coords) || coords.length < 2) return [];
            const point = map.project([Number(coords[0]), Number(coords[1])] as [number, number]);
            const label = String(feature.properties?.marker_label ?? feature.properties?.station_label ?? '');
            return [
              `<circle cx="${point.x.toFixed(2)}" cy="${point.y.toFixed(2)}" r="9.5" fill="#ffffff" stroke="#1e62d0" stroke-width="4" vector-effect="non-scaling-stroke" />`,
              `<circle cx="${point.x.toFixed(2)}" cy="${point.y.toFixed(2)}" r="4.2" fill="#1e62d0" />`,
              `<text x="${point.x.toFixed(2)}" y="${(point.y - 14).toFixed(2)}" text-anchor="middle" font-size="12" font-weight="900" fill="#0f2d66" stroke="#ffffff" stroke-width="3" paint-order="stroke">${label}</text>`,
            ];
          })
          .join('');
        const busStationMarkup = selectedMode !== 'bus'
          ? ''
          : asFeatureCollection(region.busStations).features
              .flatMap((feature) => {
                const coords = feature.geometry?.coordinates;
                if (!Array.isArray(coords) || coords.length < 2) return [];
                const travelTime = Number(feature.properties?.travel_time_min ?? feature.properties?.raw_network_time_min ?? feature.properties?.time_min ?? 0);
                if (!Number.isFinite(travelTime) || travelTime > selectedTime) return [];
                const point = map.project([Number(coords[0]), Number(coords[1])] as [number, number]);
                const radius = 4.2;
                return [
                  `<circle cx="${point.x.toFixed(2)}" cy="${point.y.toFixed(2)}" r="${radius.toFixed(2)}" fill="#16a34a" fill-opacity="0.95" stroke="#ffffff" stroke-width="1.6" vector-effect="non-scaling-stroke" />`,
                  `<circle cx="${point.x.toFixed(2)}" cy="${point.y.toFixed(2)}" r="1.6" fill="#ffffff" />`,
                ];
              })
              .join('');
        setOverlayMarkup(
          `<svg class="map-svg-overlay" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" aria-hidden="true">${landusePaths.join('')}${subwayLineMarkup}${boundaryMarkup}${coreMarkup}${markerMarkup}${busStationMarkup}</svg>`,
        );
      });
    };
    updateOverlay();
    map.on('load', updateOverlay);
    map.on('move', updateOverlay);
    map.on('zoom', updateOverlay);
    map.on('resize', updateOverlay);
    map.on('moveend', updateOverlay);
    return () => {
      cancelAnimationFrame(raf);
      map.off('load', updateOverlay);
      map.off('move', updateOverlay);
      map.off('zoom', updateOverlay);
      map.off('resize', updateOverlay);
      map.off('moveend', updateOverlay);
    };
  }, [activeLanduse, fallback, layers.landuse, mapLoaded, region, selectedMode, selectedTime, scopeMode]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || typeof map.getSource !== 'function' || !mapLoaded || fallback) return;
    const setData = (id: string, data: GeoJson) => {
      const source = map.getSource(id) as maplibregl.GeoJSONSource | undefined;
      if (source) source.setData(cloneFeatureCollection(data));
    };
    setData('landuse', activeLanduse);
    setData('full-boundary', region.fullBoundary);
    setData('core-boundary', region.coreBoundary);
    setData('support-boundary', region.supportBoundary);
    setData('markers', region.stationMarkers);
    setData('isochrones', region.isochrones);
    setData('subway-network-routes', region.subwayNetworkRoutes);
    setData('subway-network-nodes', region.subwayNetworkNodes);
    setData('subway-line-network', region.subwayLineNetwork);
    setData('subway-reach-stations', region.subwayReachStations);
    setData('buildings-full', region.buildingsFull);
    setData('buildings-core', region.buildingsCore);
    const visibility = (id: string, active: boolean) => {
      if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', active ? 'visible' : 'none');
    };
    const selectedBusOrigin = String(selected?.properties?.origin_key ?? '');
    const selectedBusTarget = String(selected?.properties?.target_station_id ?? '');
    const activeBufferMinute = nearestMinute(selectedTime, [30, 60]);
    visibility('landuse-fill', layers.landuse);
    visibility('landuse-line', layers.landuse);
    visibility('landuse-outline-shadow', layers.landuse);
    visibility('full-boundary-line', layers.fullBoundary);
    visibility('core-boundary-line', layers.coreBoundary);
    visibility('support-boundary-line', false);
    visibility('markers-circle', layers.stationMarkers);
    visibility('markers-label', layers.stationMarkers);
    visibility('buildings-full-fill', layers.buildings);
    visibility('buildings-full-line', layers.buildings);
    visibility('buildings-core-fill', layers.buildings);
    visibility('buildings-core-line', layers.buildings);
    visibility('subway30-fill', layers.accessibilityBuffer && selectedMode === 'subway' && activeBufferMinute === 30);
    visibility('subway30-line', layers.accessibilityBuffer && selectedMode === 'subway' && activeBufferMinute === 30);
    visibility('subway60-fill', layers.accessibilityBuffer && selectedMode === 'subway' && activeBufferMinute === 60);
    visibility('subway60-line', layers.accessibilityBuffer && selectedMode === 'subway' && activeBufferMinute === 60);
    visibility('bus30-fill', layers.accessibilityBuffer && selectedMode === 'bus' && activeBufferMinute === 30);
    visibility('bus30-line', layers.accessibilityBuffer && selectedMode === 'bus' && activeBufferMinute === 30);
    visibility('bus60-fill', layers.accessibilityBuffer && selectedMode === 'bus' && activeBufferMinute === 60);
    visibility('bus60-line', layers.accessibilityBuffer && selectedMode === 'bus' && activeBufferMinute === 60);
    visibility('selected-subway-line', selectedMode === 'subway');
    visibility('subway-selected-node', selectedMode === 'subway');
    visibility('bus-station-points', selectedMode === 'bus');
    if (map.getLayer('selected-subway-line')) map.setFilter('selected-subway-line', ['all', ['==', ['get', 'kind'], 'subway'], subwayTimeFilterExpression(selectedTime), ['==', ['get', 'origin_region_id'], region.id === 'pangyo' ? 'pangyo_core' : 'wirye_core']]);
    if (map.getLayer('subway-selected-node')) map.setFilter('subway-selected-node', ['all', ['==', ['get', 'origin_region_id'], region.id === 'pangyo' ? 'pangyo_core' : 'wirye_core'], subwayPointTimeFilterExpression(selectedTime)]);
    if (selectedMode === 'subway') {
      const originRegionId = region.id === 'pangyo' ? 'pangyo_core' : 'wirye_core';
      const reachBounds = filteredPointBounds(region.subwayReachStations, (feature) => {
        const props = feature.properties ?? {};
        return String(props.origin_region_id ?? '') === originRegionId && Number(props.threshold_min ?? props.min_travel_time_min ?? props.travel_time_min ?? 0) <= selectedTime;
      });
      if (reachBounds) {
        const nextBounds = featureCollectionBounds(region.fullBoundary) ?? new maplibregl.LngLatBounds();
        nextBounds.extend(reachBounds.getSouthWest());
        nextBounds.extend(reachBounds.getNorthEast());
        map.fitBounds(nextBounds, {
          padding: selectedTime >= 30 ? 44 : 30,
          duration: 0,
          maxZoom: selectedTime <= 10 ? 13.2 : selectedTime <= 20 ? 11.8 : 10.6,
        });
      }
    }
    const busOriginKey = region.id === 'pangyo' ? 'pangyo' : 'bokjeong';
    visibility('bus-route-network', selectedMode === 'bus' && selected?.kind === 'network' && selectedBusOrigin === busOriginKey && selectedBusTarget.length > 0);
    if (map.getLayer('bus-station-points')) map.setFilter('bus-station-points', ['all', ['==', ['get', 'origin_key'], busOriginKey], ['<=', ['to-number', ['get', 'travel_time_min']], selectedTime]]);
    if (map.getLayer('bus-route-network')) {
      const hasBusSelection = selected?.kind === 'network' && selectedBusOrigin === busOriginKey && selectedBusTarget.length > 0;
      map.setFilter(
        'bus-route-network',
        hasBusSelection
          ? ['all', ['==', ['get', 'mode'], 'bus'], ['==', ['get', 'origin_key'], selectedBusOrigin], ['==', ['get', 'target_station_id'], selectedBusTarget], ['<=', ['to-number', ['get', 'travel_time_min']], selectedTime]]
          : ['all', ['==', ['get', 'mode'], 'bus'], ['==', ['get', 'origin_key'], busOriginKey], ['<=', ['to-number', ['get', 'travel_time_min']], selectedTime]],
      );
    }
    if (map.getLayer('markers-label')) map.setLayoutProperty('markers-label', 'text-allow-overlap', true);
    map.resize();
  }, [activeLanduse, fallback, layers, mapLoaded, region, selected, selectedMode, selectedTime]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const ro = new ResizeObserver(() => map.resize());
    if (containerRef.current) ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  return (
    <article className="map-card panel-card">
      <div className="map-head">
        <div className="map-title-block">
          <div className="chart-kicker">
            {region.id === 'pangyo' ? <TrainFront size={14} /> : <MapPinned size={14} />}
            <span>{region.label}</span>
          </div>
          <h3>{region.shortLabel} 비교지도</h3>
          <p>
            {scopeMode === 'planning' ? 'Planning context' : 'Core'} · {TRANSPORT_LABEL[selectedMode]} {displayMinute}분 · {region.stationName} 기준
          </p>
        </div>
        <div className="map-chip-stack">
          <span className="map-chip">{scopeMode.toUpperCase()}</span>
          <span className="map-chip subtle">{TRANSPORT_LABEL[selectedMode]}</span>
          <span className="map-chip subtle">{displayMinute}분</span>
        </div>
      </div>
      <div className="map-frame">
        <div ref={containerRef} className="map-canvas" />
        {overlayMarkup ? <div className="map-svg-holder" dangerouslySetInnerHTML={{ __html: overlayMarkup }} /> : null}
        {fallback ? (
          <div className="map-fallback">
            <Sparkles size={16} />
            <span>지도를 다시 불러오는 중입니다.</span>
          </div>
        ) : null}
        <div className="map-overlay legend-card">
          <div className="legend-item">
            <i style={{ background: '#2563eb', borderRadius: '999px' }} />
            <span>지하철 마킹</span>
          </div>
          <div className="legend-item">
            <i style={{ background: '#16a34a', borderRadius: '999px' }} />
            <span>버스 마킹</span>
          </div>
          <div className="legend-item">
            <i
              style={{
                width: 16,
                height: 0,
                borderRadius: 0,
                border: 'none',
                borderTop: '2px dashed #ef4444',
                background: 'transparent',
              }}
            />
            <span>업무지구 면적</span>
          </div>
          <div className="legend-item">
            <i
              style={{
                width: 16,
                height: 0,
                borderRadius: 0,
                border: 'none',
                borderTop: '2px solid #1f3f8a',
                background: 'transparent',
              }}
            />
            <span>택지경계</span>
          </div>
          <div className="legend-item">
            <i style={{ background: '#ffffff', border: '3px solid #1e62d0', borderRadius: '999px' }} />
            <span>핵심역 마킹</span>
          </div>
        </div>
        <div className="map-overlay data-badge">
          <span>{region.stationName} 핵심역</span>
          <strong>{region.shortLabel}</strong>
          <span>토지이용계획도 · 경계 · 경로</span>
        </div>
      </div>
    </article>
  );
}

function DetailRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="detail-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SelectedPanel({
  selected,
  rows,
}: {
  selected: SelectedFeature | null;
  rows: AccessibilityRow[];
}) {
  if (!selected) {
    return (
      <section className="selected-card">
        <div className="selected-head">
          <div>
            <div className="chart-kicker">
              <Compass size={14} />
              <span>선택 객체 정보</span>
            </div>
            <h3>대상 미선택</h3>
            <p>지도에서 토지이용, 등시간권, 건축물을 선택하면 상세 정보가 표시됩니다.</p>
          </div>
          <span className="selected-pill idle">Idle</span>
        </div>
        <div className="empty-state">
          <BadgeInfo size={18} />
          <p>토지이용 polygon, 등시간권 polygon, 건축물 레이어를 클릭하세요.</p>
        </div>
      </section>
    );
  }
  const props = selected.properties ?? {};
  const station = getIsoStation(props);
  const mode = getIsoMode(props) as TransportMode;
  const minute = getIsoMinute(props);
  const accessRow = station && mode ? rows.find((row) => row.origin_station_name === station.replace(/역$/, '') && row.mode === mode && Number(row.threshold_min) === minute) ?? null : null;
  const routeNames = props.route_names ?? props.route_name ?? getNetworkRoute(props) ?? 'N/A';
  const rowsToShow =
    selected.kind === 'landuse'
      ? [
          ['용도지역명', props.planned_use_detail ?? props.zone_name ?? props.zone_group ?? 'N/A'],
          ['표준 그룹', props.category_group ?? props.planned_use_group ?? 'N/A'],
          ['면적', formatArea(props.area_m2 ?? props.overlay_area_m2 ?? props.boundary_area_m2 ?? props.area ?? null)],
          ['비율', formatPercent(props.area_share ?? props.area_ratio ?? props.share ?? null)],
          ['출처', props.source_file ?? props.source_path ?? 'N/A'],
        ]
      : selected.kind === 'isochrone'
        ? [
            ['역명', station || 'N/A'],
            ['수단', TRANSPORT_LABEL[mode] ?? 'N/A'],
            ['시간', `${minute}분`],
            ['도달 인구', formatCompactNumber(props.accessible_population ?? accessRow?.accessible_population ?? null, 1)],
            ['도달 종사자', formatCompactNumber(props.accessible_workers ?? accessRow?.accessible_workers ?? null, 1)],
            ['도달 사업체', formatCompactNumber(props.accessible_businesses ?? accessRow?.accessible_businesses ?? null, 1)],
            ['산정 방식', '네트워크 기반 누적 접근성'],
          ]
        : selected.kind === 'network'
          ? [
              ['출발역', getNetworkOrigin(props) || 'N/A'],
              ['정류장명', getNetworkTarget(props) || 'N/A'],
              ['수단', TRANSPORT_LABEL[mode] ?? String(props.mode ?? 'N/A')],
              ['도달시간', `${formatNumber(getNetworkTime(props), 1)}분`],
              ['환승횟수', props.transfer_count ?? props.transfer ?? 'N/A'],
              ['이용노선', routeNames],
              ['경로요약', props.route_chain ?? props.geometry_source_summary ?? props.line_name ?? props.source ?? 'N/A'],
              ['출처', props.source ?? 'network'],
          ]
        : [
            ['건물명/관리번호', props.building_label ?? props.buld_nm ?? props.gis_building_id ?? props.id ?? 'N/A'],
            ['주용도', props.main_use_group ?? props.main_use_text ?? 'N/A'],
            ['세부 용도', props.main_use_text ?? props.dong_nm ?? 'N/A'],
            ['용도 그룹', props.main_use_group ?? 'N/A'],
            ['연면적', formatArea(props.total_floor_area_m2 ?? null)],
            ['대지면적', formatArea(props.site_area_m2 ?? null)],
            ['건축면적', formatArea(props.building_area_m2 ?? null)],
            ['용적률', formatPercent(props.far_percent ?? null)],
            ['건폐율', formatPercent(props.bcr_percent ?? null)],
            ['층수', `${formatNumber(props.ground_floor_co ?? 0)}F / B${formatNumber(props.undgrnd_floor_co ?? 0)}`],
            ['승인연도', formatYear(props.approval_year ?? props.approval_date)],
            ['PNU', props.pnu ?? 'N/A'],
            ['출처', props.source_mode ?? 'vworld_wfs'],
          ];
  return (
    <section className="selected-card">
      <div className="selected-head">
        <div>
          <div className="chart-kicker">
            <BadgeInfo size={14} />
            <span>선택 객체 정보</span>
          </div>
          <h3>{selected.title}</h3>
          <p>{selected.kind === 'landuse' ? '토지이용계획 polygon' : selected.kind === 'isochrone' ? '등시간권 polygon' : selected.kind === 'network' ? '접근성 네트워크 선' : '건축물 GIS'}</p>
        </div>
        <span className={`selected-pill ${selected.kind ?? 'idle'}`}>{selected.kind ?? 'idle'}</span>
      </div>
      <div className="detail-list">
        {rowsToShow.map(([label, value]) => (
          <DetailRow key={label} label={label} value={value} />
        ))}
      </div>
      <div className="selected-note">
        <div className="selected-note-title">
          <Compass size={14} />
          <span>현재 선택 시간</span>
        </div>
        <strong>{minute ? `${minute}분` : 'N/A'}</strong>
      </div>
    </section>
  );
}

function InfoBullets({ items }: { items: string[] }) {
  return (
    <div className="info-bullets">
      {items.map((item) => (
        <div className="info-bullet" key={item}>
          <Sparkles size={14} />
          <span>{item}</span>
        </div>
      ))}
    </div>
  );
}

function SocietyBar({
  label,
  value,
  max,
  color,
}: {
  label: string;
  value: number;
  max: number;
  color: string;
}) {
  const width = max > 0 ? Math.max((value / max) * 100, value > 0 ? 4 : 0) : 0;
  return (
    <div className="society-bar">
      <span className="society-bar-label">{label}</span>
      <div className="society-bar-track">
        <div className="society-bar-fill" style={{ width: `${width}%`, background: color }} />
      </div>
      <strong>{formatCompactNumber(value, 1)}</strong>
    </div>
  );
}

function SocietyComparisonCard({
  title,
  subtitle,
  regionLabel,
  full,
  core,
}: {
  title: string;
  subtitle: string;
  regionLabel: string;
  full: { population: number; workers: number };
  core: { population: number; workers: number };
}) {
  const populationMax = Math.max(full.population, core.population, 1);
  const workerMax = Math.max(full.workers, core.workers, 1);
  const fullRatio = full.population > 0 ? full.workers / full.population : null;
  const coreRatio = core.population > 0 ? core.workers / core.population : null;

  return (
    <section className="society-card panel-card">
      <div className="chart-head">
        <div>
          <div className="chart-kicker">
            <Users size={14} />
            <span>{subtitle}</span>
          </div>
          <h3>{title}</h3>
          <p>{regionLabel}</p>
        </div>
        <div className="chart-chip">full / core</div>
      </div>
      <div className="society-bars">
        <div className="society-bar-group">
          <div className="society-bar-group-title">거주 인구</div>
          <SocietyBar label="택지 범위" value={full.population} max={populationMax} color="#1e62d0" />
          <SocietyBar label="업무지구 범위(core)" value={core.population} max={populationMax} color="#ef6f19" />
        </div>
        <div className="society-bar-group">
          <div className="society-bar-group-title">종사자 수</div>
          <SocietyBar label="택지 범위" value={full.workers} max={workerMax} color="#1e62d0" />
          <SocietyBar label="업무지구 범위(core)" value={core.workers} max={workerMax} color="#ef6f19" />
        </div>
      </div>
      <div className="curve-mini">
        <span className="mini-pill">택지 직주비 {fullRatio == null ? 'N/A' : fullRatio.toFixed(2)}</span>
        <span className="mini-pill">업무지구 직주비 {coreRatio == null ? 'N/A' : coreRatio.toFixed(2)}</span>
      </div>
    </section>
  );
}

function App() {
  const [data, setData] = useState<AppData | null>(null);
  const [busAccessDashboard, setBusAccessDashboard] = useState<BusAccessDashboard | null>(null);
  const [subwayAccessDashboard, setSubwayAccessDashboard] = useState<Subway750Dashboard | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadStage, setLoadStage] = useState('데이터를 불러오는 중입니다.');
  const [scopeMode, setScopeMode] = useState<ScopeMode>('planning');
  const [selectedMode, setSelectedMode] = useState<TransportMode>('bus');
  const [selectedMetric, setSelectedMetric] = useState<MetricMode>('workers');
  const [selectedTime, setSelectedTime] = useState(30);
  const [layers, setLayers] = useState<LayerFlags>(LAYER_DEFAULTS);
  const [selected, setSelected] = useState<SelectedFeature | null>(null);
  const [buildingMode, setBuildingMode] = useState<'full' | 'core'>('core');
  const [buildingMetric, setBuildingMetric] = useState<'count' | 'area'>('area');
  const [analysisOpen, setAnalysisOpen] = useState(true);
  const [analysisTab, setAnalysisTab] = useState<'accessibility' | 'buildingUse' | 'planning' | 'ratio' | 'society'>('accessibility');

  useEffect(() => {
    let active = true;
    async function run() {
      try {
        setLoadStage('토지이용계획과 경계 데이터를 불러오는 중입니다.');
        const [
          planPangyo,
          planWirye,
          scopeBoundaries,
          fullBoundary,
          coreBoundary,
          supportBoundary,
          stationMarkers,
          busStations,
          busAccessDashboardJson,
          subwayAccessRows,
          accessibilitySummary,
          accessibilityCurve,
          buildingGisSummary,
          buildingSummaryV35,
          boundaryFarSummary,
          planningBoundaryPopWorkerSummary,
          corePerformanceRowsResult,
          planningPerformanceRowsResult,
          sgisCoreRowsResult,
        ] = await Promise.all([
          loadJson<GeoJson>('map_full_planning_landuse_pangyo_v24.geojson'),
          loadJson<GeoJson>('map_full_planning_landuse_wirye_v24.geojson'),
          loadJson<GeoJson>('final_landuse_scope_boundaries_v16.geojson'),
          loadJson<GeoJson>('full_boundary_v25.geojson'),
          loadJson<GeoJson>('final_core_boundaries_v14.geojson'),
          loadJson<GeoJson>('final_station_support_boundaries_v14.geojson'),
          loadJson<GeoJson>('station_markers_v35.geojson'),
          loadJson<GeoJson>('bus_access_pangyo_bokjeong_0_60min_station_population_workers_500m.geojson'),
          loadJson<BusAccessDashboard>('dashboard_bus_access_pangyo_bokjeong_0_60min_station_population_workers_500m.json'),
          loadCsvRows<Subway750CurveCandidateRow>('subway_station_population_workers_750m_grid_v2.csv'),
          loadJson<{ rows: AccessibilityRow[] }>('pangyo_bokjeong_mode_accessibility_summary_v30.json'),
          loadJson<{ rows: AccessibilityRow[] }>('pangyo_bokjeong_mode_accessibility_curve_v30.json'),
          loadJson<{ rows: BuildingGisRow[] }>('buildings_gis_summary_v35.json'),
          loadJson<BuildingSummaryRow[]>('buildings_summary_v35.json'),
          loadJson<{ metadata?: Record<string, any>; rows: BoundaryFarSummaryRow[] }>('building_register_boundary_office_far_summary.json'),
          loadJson<{ metadata?: Record<string, any>; rows: PlanningBoundaryPopWorkerRow[] }>('planning_boundary_population_workers_area_v2.json'),
          loadJson<{ rows: PerformanceRowV14[] }>('final_core_performance_v14.json'),
          loadJson<{ rows: PerformanceRowV14[] }>('final_station_support_v14.json'),
          loadJson<SgisRow[]>('sgis_core_key_indicators_v2.json'),
        ]);

        if (!active) return;

        const accessibilityRows = accessibilitySummary.rows ?? [];
        const accessibilityCurveRows = accessibilityCurve.rows ?? [];
        const buildingGisRows = buildingGisSummary.rows ?? [];
        const buildingSummaryRows = buildingSummaryV35 ?? [];
        const boundaryFarSummaryRows = boundaryFarSummary?.rows ?? [];
        const planningBoundaryPopWorkerRows = planningBoundaryPopWorkerSummary?.rows ?? [];
        const corePerformanceRows = corePerformanceRowsResult?.rows ?? [];
        const planningPerformanceRows = planningPerformanceRowsResult?.rows ?? [];
        const sgisCoreRows = sgisCoreRowsResult ?? [];
        const normalizedBusDashboard = busAccessDashboardJson ?? { table: [], selected: [], candidates: [] };
        const normalizedSubwayDashboard = buildSubwayDashboardFromCsv(subwayAccessRows ?? []);
        const subwayReachGeoJson = buildSubwayReachStationsFromCsv(normalizedSubwayDashboard.candidates as Subway750CurveCandidateRow[]);

        const base = {
          planningLanduse: recoverGeoJson(planPangyo),
          scopeLanduse: recoverGeoJson(scopeBoundaries),
          fullBoundary: recoverGeoJson(fullBoundary),
          coreBoundary: recoverGeoJson(coreBoundary),
          supportBoundary: recoverGeoJson(supportBoundary),
          stationMarkers: recoverGeoJson(stationMarkers),
          busStations: recoverGeoJson(busStations),
          isochrones: { type: 'FeatureCollection', features: [] } as GeoJson,
          subwayNetworkNodes: { type: 'FeatureCollection', features: [] } as GeoJson,
          subwayNetworkRoutes: { type: 'FeatureCollection', features: [] } as GeoJson,
          subwayLineNetwork: { type: 'FeatureCollection', features: [] } as GeoJson,
          subwayReachStations: recoverGeoJson(subwayReachGeoJson),
          busPathEdges: { type: 'FeatureCollection', features: [] } as GeoJson,
          buildingsFull: { type: 'FeatureCollection', features: [] } as GeoJson,
          buildingsCore: { type: 'FeatureCollection', features: [] } as GeoJson,
          corePerformanceRows,
          planningPerformanceRows,
          sgisCoreRows,
          accessibilityRows,
          buildingSummaryRows,
          buildingGisRows,
        };

        const pangyo = buildRegionData('pangyo', base);
        const wirye = buildRegionData('wirye', {
          ...base,
          planningLanduse: recoverGeoJson(planWirye),
        });

        setData({
          pangyo,
          wirye,
          accessibilityRows,
          accessibilityCurveRows,
          buildingSummaryRows,
          buildingGisRows,
          boundaryFarSummaryRows,
          planningBoundaryPopWorkerRows,
        });
        setBusAccessDashboard(normalizedBusDashboard);
        setSubwayAccessDashboard(normalizedSubwayDashboard);
        setLoadStage('지도 세부 데이터를 백그라운드에서 불러오는 중입니다.');
        setLoadError(null);

        Promise.all([
          loadJson<GeoJson>('pangyo_bokjeong_mode_isochrones_v30.geojson'),
          loadJson<GeoJson>('subway_network_lines_edit_v1.geojson'),
          loadJson<GeoJson>('reachable_subway_routes_pangyo_bokjeong_v36.geojson'),
          loadJson<GeoJson>('reachable_subway_nodes_pangyo_bokjeong_v36.geojson'),
          loadJson<GeoJson>('bus_access_pangyo_bokjeong_0_60min_path_edges.geojson'),
          loadJson<GeoJson>('buildings_full_pangyo_v35.geojson'),
          loadJson<GeoJson>('buildings_full_wirye_v35.geojson'),
          loadJson<GeoJson>('buildings_core_pangyo_v35.geojson'),
          loadJson<GeoJson>('buildings_core_wirye_v35.geojson'),
        ])
        .then(([isochrones, subwayLineNetwork, subwayRoutes, subwayNodes, busEdges, buildingsFullPangyo, buildingsFullWirye, buildingsCorePangyo, buildingsCoreWirye]) => {
            if (!active) return;
            setData((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                pangyo: {
                  ...prev.pangyo,
                  isochrones: recoverGeoJson(isochrones),
                  subwayLineNetwork: recoverGeoJson(subwayLineNetwork),
                  subwayNetworkRoutes: recoverGeoJson(subwayRoutes),
                  subwayNetworkNodes: recoverGeoJson(subwayNodes),
                  subwayReachStations: prev.pangyo.subwayReachStations,
                  busPathEdges: recoverGeoJson(busEdges),
                  buildingsFull: recoverGeoJson(buildingsFullPangyo),
                  buildingsCore: recoverGeoJson(buildingsCorePangyo),
                },
                wirye: {
                  ...prev.wirye,
                  isochrones: recoverGeoJson(isochrones),
                  subwayLineNetwork: recoverGeoJson(subwayLineNetwork),
                  subwayNetworkRoutes: recoverGeoJson(subwayRoutes),
                  subwayNetworkNodes: recoverGeoJson(subwayNodes),
                  subwayReachStations: prev.wirye.subwayReachStations,
                  busPathEdges: recoverGeoJson(busEdges),
                  buildingsFull: recoverGeoJson(buildingsFullWirye),
                  buildingsCore: recoverGeoJson(buildingsCoreWirye),
                },
              };
            });
            setLoadStage('준비 완료');
          })
          .catch(() => {
            if (!active) return;
            setLoadStage('준비 완료');
          });
      } catch (error) {
        if (!active) return;
        setLoadError(error instanceof Error ? error.message : 'Unknown data loading error');
      }
    }
    run();
    return () => {
      active = false;
    };
  }, []);

  const left = data?.pangyo ?? createEmptyRegion('pangyo');
  const right = data?.wirye ?? createEmptyRegion('wirye');

  const topMetrics = useMemo(() => {
    const rows = data?.accessibilityRows ?? [];
    const busRows = busAccessDashboard?.candidates ?? [];
    const pickAccessibility = (station: '판교' | '복정', mode: TransportMode) => {
      const filtered = rows
        .filter((row) => row.origin_station_name === station && row.mode === mode)
        .sort((a, b) => Number(a.threshold_min) - Number(b.threshold_min));
      const minute = nearestMinute(selectedTime, filtered.map((row) => Number(row.threshold_min)));
      return filtered.find((row) => Number(row.threshold_min) === minute) ?? filtered[0] ?? null;
    };
    const pickBusSummary = (originKey: 'pangyo' | 'bokjeong') => {
      const selectedRow = busAccessDashboard?.selected.find((row) => row.origin_key === originKey);
      const summary = getBusCandidateSummary(busRows, originKey, selectedTime);
      return { selectedRow, summary };
    };
    const subwayRows = (subwayAccessDashboard?.candidates ?? []) as Subway750CurveCandidateRow[];
    const pangyoSubway = getSubwayCandidateSummary(subwayRows.filter((row) => String(row.origin_region_id ?? '').includes('pangyo')), '판교', selectedTime);
    const bokjeongSubway = getSubwayCandidateSummary(subwayRows.filter((row) => String(row.origin_region_id ?? '').includes('wirye')), '복정', selectedTime);
    const leftSgis = scopeMode === 'planning' ? left.planningPerformance ?? left.corePerformance : left.corePerformance ?? left.planningPerformance;
    const rightSgis = scopeMode === 'planning' ? right.planningPerformance ?? right.corePerformance : right.corePerformance ?? right.planningPerformance;
    const pangyoBus = pickBusSummary('pangyo');
    const bokjeongBus = pickBusSummary('bokjeong');
    const scopeLabel = scopeMode === 'planning' ? '택지 범위' : '업무지구 범위(core)';
    const pangyoBusLabel = `판교 (${pangyoBus.summary.station_count}개 정류장)`;
    const bokjeongBusLabel = `위례 (${bokjeongBus.summary.station_count}개 정류장)`;
    const pangyoSubwayLabel = `판교 (${pangyoSubway.station_count}개 역)`;
    const bokjeongSubwayLabel = `위례 (${bokjeongSubway.station_count}개 역)`;
    return [
      {
        icon: <Users size={16} />,
        title: '종사자 밀도',
        tooltip: '집계구 단위로 면적가중 배분해 산정한 2023년 기준 종사자 밀도입니다. 단위는 명/km²이며, 비교범위에 따라 택지 범위와 core 값이 달라집니다.',
        leftLabel: '판교',
        rightLabel: '위례',
        leftValue: formatCompactNumber(leftSgis?.worker_density_per_km2, 1),
        rightValue: formatCompactNumber(rightSgis?.worker_density_per_km2, 1),
        note: `${scopeLabel} · 2023`,
      },
      {
        icon: <Warehouse size={16} />,
        title: '사업체 밀도',
        tooltip: '집계구 단위로 면적가중 배분해 산정한 2023년 기준 사업체 밀도입니다. 단위는 개/km²이며, 비교범위에 따라 택지 범위와 core 값이 달라집니다.',
        leftLabel: '판교',
        rightLabel: '위례',
        leftValue: formatCompactNumber(leftSgis?.business_density_per_km2, 1),
        rightValue: formatCompactNumber(rightSgis?.business_density_per_km2, 1),
        note: `${scopeLabel} · 2023`,
      },
      {
        icon: <Sparkles size={16} />,
        title: '버스 누적 접근 인구수',
        tooltip: '버스 정류장 반경 500m 내 거주 인구수를 기준으로 산정한 누적 접근 인구수입니다.',
        leftLabel: pangyoBusLabel,
        rightLabel: bokjeongBusLabel,
        leftValue: formatCompactNumber(pangyoBus.summary.resident_population_500m, 1),
        rightValue: formatCompactNumber(bokjeongBus.summary.resident_population_500m, 1),
        note: `${selectedTime}분 기준`,
      },
      {
        icon: <Sparkles size={16} />,
        title: '버스 누적 접근 종사자 수',
        tooltip: '버스 정류장 반경 500m 내 접근 종사자수를 기준으로 산정한 누적 접근 종사자 수입니다.',
        leftLabel: pangyoBusLabel,
        rightLabel: bokjeongBusLabel,
        leftValue: formatCompactNumber(pangyoBus.summary.worker_population_500m, 1),
        rightValue: formatCompactNumber(bokjeongBus.summary.worker_population_500m, 1),
        note: `${selectedTime}분 기준`,
      },
      {
        icon: <MapPinned size={16} />,
        title: '지하철 누적 접근 인구수',
        tooltip: '지하철역 반경 750m 내 거주 인구수를 기준으로 산정한 누적 접근 인구수입니다.',
        leftLabel: pangyoSubwayLabel,
        rightLabel: bokjeongSubwayLabel,
        leftValue: formatCompactNumber(pangyoSubway.population_750m, 1),
        rightValue: formatCompactNumber(bokjeongSubway.population_750m, 1),
        note: `${selectedTime}분 기준`,
      },
      {
        icon: <MapPinned size={16} />,
        title: '지하철 누적 접근 종사자 수',
        tooltip: '지하철역 반경 750m 내 접근 종사자수를 기준으로 산정한 누적 접근 종사자 수입니다.',
        leftLabel: pangyoSubwayLabel,
        rightLabel: bokjeongSubwayLabel,
        leftValue: formatCompactNumber(pangyoSubway.worker_750m, 1),
        rightValue: formatCompactNumber(bokjeongSubway.worker_750m, 1),
        note: `${selectedTime}분 기준`,
      },
    ];
  }, [busAccessDashboard, data?.accessibilityRows, left, right, scopeMode, selectedTime, subwayAccessDashboard]);

  const accessibilityCurveSource = useMemo(() => {
    if (selectedMode === 'subway') {
      const subwayRows = (subwayAccessDashboard?.candidates ?? []) as Subway750CurveCandidateRow[];
      const pangyoRows = subwayRows.filter((row) => String(row.origin_region_id ?? '').includes('pangyo'));
      const bokjeongRows = subwayRows.filter((row) => String(row.origin_region_id ?? '').includes('wirye'));
      return [...buildSubwayCurveRows(pangyoRows, '판교', selectedMetric), ...buildSubwayCurveRows(bokjeongRows, '복정', selectedMetric)];
    }
    if (selectedMode === 'bus' && busAccessDashboard) {
      return [...buildBusCurveRows(busAccessDashboard.candidates ?? [], 'pangyo', selectedMetric), ...buildBusCurveRows(busAccessDashboard.candidates ?? [], 'bokjeong', selectedMetric)];
    }
    return data?.accessibilityRows ?? [];
  }, [busAccessDashboard, data?.accessibilityRows, selectedMetric, selectedMode, subwayAccessDashboard]);

  const landusePlanning = useMemo(() => {
    if (!left || !right) return { left: [], right: [] };
    const getSlices = (region: RegionData) => (scopeMode === 'planning' ? region.landusePlanningSlices : region.landuseScopeSlices[scopeMode]);
    return { left: getSlices(left), right: getSlices(right) };
  }, [left, right, scopeMode]);

  const buildingSlices = useMemo(() => {
    if (!data || !left || !right) return { left: [], right: [] };
    const pickRows = (region: RegionData) => {
      const row = data.buildingGisRows.find((item) => item.region_group === `${region.id}_${buildingMode}`) ?? region.buildingGisCore ?? region.buildingGisFull;
      if (!row) return [];
      return summarizeBuildingsUseRow(buildingMetric === 'area' ? row.use_rows : row.use_rows_by_count.map((item) => ({ ...item, total_floor_area_m2: item.record_count })), buildingMetric === 'area' ? 'share_floor_area' : 'share_count');
    };
    return { left: pickRows(left), right: pickRows(right) };
  }, [buildingMetric, buildingMode, data, left, right]);

  const planFunctionSlices = useMemo(() => {
    if (!left || !right) return { left: [], right: [] };
    const summarize = (region: RegionData) => summarizeByKey((scopeMode === 'planning' ? region.planningLanduse : region.scopeLanduse).features, (props) => String(props.category_group ?? props.planned_use_group ?? props.zone_group ?? 'unknown'), (props) => Number(props.area_m2 ?? 0));
    return { left: summarize(left), right: summarize(right) };
  }, [left, right, scopeMode]);

  const ratioSummary = useMemo(() => {
    if (!left || !right) return { left: null, right: null };
    const pick = (region: RegionData) => (scopeMode === 'planning' ? region.buildingSummaryFull ?? region.buildingSummaryCore : region.buildingSummaryCore ?? region.buildingSummaryFull);
    return { left: pick(left), right: pick(right) };
  }, [left, right, scopeMode]);

  const boundaryFarSummary = useMemo(() => {
    const rows = data?.boundaryFarSummaryRows ?? [];
    const findRow = (areaName: 'pangyo' | 'wirye') => rows.find((row) => row.area_name === areaName) ?? null;
    return {
      pangyo: findRow('pangyo'),
      wirye: findRow('wirye'),
    };
  }, [data?.boundaryFarSummaryRows]);

  const planningBoundarySummary = useMemo(() => {
    const rows = data?.planningBoundaryPopWorkerRows ?? [];
    const findRow = (regionId: RegionId, areaType: 'full' | 'core') => rows.find((row) => row.region_id === regionId && row.area_type === areaType) ?? null;
    const formatRow = (row: PlanningBoundaryPopWorkerRow | null) => ({
      population: Number(row?.population_total ?? 0),
      workers: Number(row?.worker_total ?? 0),
      coverage: Number(row?.coverage_ratio ?? 0),
      area_km2: Number(row?.boundary_area_km2 ?? 0),
    });
    return {
      pangyo: {
        full: formatRow(findRow('pangyo', 'full')),
        core: formatRow(findRow('pangyo', 'core')),
      },
      wirye: {
        full: formatRow(findRow('wirye', 'full')),
        core: formatRow(findRow('wirye', 'core')),
      },
    };
  }, [data?.planningBoundaryPopWorkerRows]);

  const keyInterpretation = useMemo(() => {
    if (!left || !right) return [];
    return [
      '판교는 업무·교육 중심 비중이 높고, 위례는 주거·생활서비스 비중이 상대적으로 큽니다.',
      '지하철 기반 30분 도달 종사자와 60분 누적 곡선이 비교 우위를 보여 줍니다.',
      '토지이용계획과 건축물 용도 분포를 함께 보면 실제 밀도 편차가 명확합니다.',
    ];
  }, [left, right]);

  const societyMetricCards = useMemo(() => {
    const format = (value: number) => formatCompactNumber(value, 1);
    return [
      {
        title: '판교 택지 범위',
        note: 'SGIS 집계구 면적비례 배분 · full',
        leftLabel: '총인구',
        leftValue: format(planningBoundarySummary.pangyo.full.population),
        rightLabel: '총종사자',
        rightValue: format(planningBoundarySummary.pangyo.full.workers),
      },
      {
        title: '판교 업무지구 범위(core)',
        note: 'SGIS 집계구 면적비례 배분 · core',
        leftLabel: '총인구',
        leftValue: format(planningBoundarySummary.pangyo.core.population),
        rightLabel: '총종사자',
        rightValue: format(planningBoundarySummary.pangyo.core.workers),
      },
      {
        title: '위례 택지 범위',
        note: 'SGIS 집계구 면적비례 배분 · full',
        leftLabel: '총인구',
        leftValue: format(planningBoundarySummary.wirye.full.population),
        rightLabel: '총종사자',
        rightValue: format(planningBoundarySummary.wirye.full.workers),
      },
      {
        title: '위례 업무지구 범위(core)',
        note: 'SGIS 집계구 면적비례 배분 · core',
        leftLabel: '총인구',
        leftValue: format(planningBoundarySummary.wirye.core.population),
        rightLabel: '총종사자',
        rightValue: format(planningBoundarySummary.wirye.core.workers),
      },
    ];
  }, [planningBoundarySummary]);

  if (loadError) {
    return (
      <div className="error-screen">
        <div className="panel-card error-card">
          <div className="loading-icon">
            <BadgeInfo size={24} />
          </div>
          <h2>데이터 로딩 실패</h2>
          <p>필수 데이터 파일을 읽지 못했습니다. `frontend2/public/data` 경로를 확인하세요.</p>
          <pre>{loadError}</pre>
          <div className="load-stage-text">{loadStage}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard-shell" style={{ '--theme-accent': '#1e62d0' } as CSSProperties}>
      <header className="dashboard-header">
        <div className="header-left">
          <div className="brand-mark">G</div>
          <div className="header-copy">
            <div className="dashboard-title">데이터로 진단하는 업무지구의 성과와 실패</div>
            <div className="dashboard-subtitle">판교테크노밸리 vs 위례신도시 비교분석 시스템</div>
          </div>
        </div>
        <div className="header-right">
          <span className="header-chip">2023 기준</span>
          <span className="header-chip">GitHub Pages Dashboard</span>
        </div>
      </header>

      <section className="kpi-grid">
      {topMetrics.map((metric, index) => (
        <MetricCard key={`${metric.title}-${index}`} {...metric} />
      ))}
      </section>

      <main className="workspace">
        <aside className="control-panel panel-card">
          <SectionTitle kicker="비교 조건" title="비교 범위" subtitle="택지 범위와 업무지구 범위를 빠르게 전환합니다." />
          <div className="scope-grid two">
            {[
              { value: 'planning', label: '택지 범위' },
              { value: 'core', label: '업무지구 범위(core)' },
            ].map((item) => (
              <button key={item.value} type="button" className={`scope-button ${scopeMode === item.value ? 'active' : ''}`} onClick={() => setScopeMode(item.value as ScopeMode)}>
                {item.label}
              </button>
            ))}
          </div>

          <SectionTitle kicker="교통수단" title="분석 수단" subtitle="" />
          <div className="scope-grid two">
            <button type="button" className={`scope-button ${selectedMode === 'subway' ? 'active' : ''}`} onClick={() => setSelectedMode('subway')}>
              지하철
            </button>
            <button type="button" className={`scope-button ${selectedMode === 'bus' ? 'active' : ''}`} onClick={() => setSelectedMode('bus')}>
              버스
            </button>
          </div>

          <SectionTitle kicker="시간 설정" title="0~60분 슬라이더" subtitle="선택 시간에 맞춰 곡선과 지도상의 대표 권역이 갱신됩니다." />
          <div className="slider-readout">현재 {selectedTime}분</div>
          <input aria-label="0 to 60 minute slider" type="range" min={0} max={60} step={5} value={selectedTime} onChange={(event) => setSelectedTime(Number(event.target.value))} />
          <div className="slider-labels">
            <span>0</span>
            <span>30</span>
            <span>60</span>
          </div>

          <SectionTitle kicker="지도 레이어" title="레이어 토글" subtitle="토지이용, 경계, 마커, 건축물을 개별 제어합니다." />
          <div className="toggle-grid">
            <ToggleButton label="토지이용계획도" active={layers.landuse} onClick={() => setLayers((prev) => ({ ...prev, landuse: !prev.landuse }))} icon={<TreePine size={14} />} />
            <ToggleButton label="업무지구(core)" active={layers.coreBoundary} onClick={() => setLayers((prev) => ({ ...prev, coreBoundary: !prev.coreBoundary }))} icon={<Shield size={14} />} />
            <ToggleButton label="택지 경계" active={layers.fullBoundary} onClick={() => setLayers((prev) => ({ ...prev, fullBoundary: !prev.fullBoundary }))} icon={<Shield size={14} />} />
            <ToggleButton label="건축물 GIS" active={layers.buildings} onClick={() => setLayers((prev) => ({ ...prev, buildings: !prev.buildings }))} icon={<Building2 size={14} />} />
          </div>
        </aside>

        <section className="map-column">
          <div className="map-grid">
            <MapView region={left} selectedMode={selectedMode} selectedTime={selectedTime} layers={layers} scopeMode={scopeMode} selected={selected} onPickFeature={setSelected} />
            <MapView region={right} selectedMode={selectedMode} selectedTime={selectedTime} layers={layers} scopeMode={scopeMode} selected={selected} onPickFeature={setSelected} />
          </div>
        </section>

        <aside className="selected-panel panel-card">
          <SelectedPanel selected={selected} rows={data?.accessibilityRows ?? []} />
          <div className="panel-divider" />
          <section className="quick-insight">
            <SectionTitle kicker="핵심 해석" title="요약 포인트" subtitle="화면 한 장으로 제출 가능한 해석 문장들입니다." />
            <InfoBullets items={keyInterpretation} />
          </section>
        </aside>
      </main>

      <section className={`analysis-drawer ${analysisOpen ? 'open' : 'collapsed'}`}>
        <div className="analysis-drawer-bar">
          <div className="drawer-toggle">하단 분석</div>
          <div className="analysis-drawer-tabs">
            <button type="button" className={`drawer-tab ${analysisTab === 'accessibility' ? 'active' : ''}`} onClick={() => setAnalysisTab('accessibility')}>접근성 곡선</button>
            <button type="button" className={`drawer-tab ${analysisTab === 'planning' ? 'active' : ''}`} onClick={() => setAnalysisTab('planning')}>토지이용계획 비율</button>
            <button type="button" className={`drawer-tab ${analysisTab === 'buildingUse' ? 'active' : ''}`} onClick={() => setAnalysisTab('buildingUse')}>건축물 용도 비율</button>
            <button type="button" className={`drawer-tab ${analysisTab === 'ratio' ? 'active' : ''}`} onClick={() => setAnalysisTab('ratio')}>용적률</button>
            <button type="button" className={`drawer-tab ${analysisTab === 'society' ? 'active' : ''}`} onClick={() => setAnalysisTab('society')}>인구사회</button>
          </div>
        </div>

        <div className="analysis-drawer-content">
          {analysisTab === 'accessibility' ? (
            <LineChartCard rows={accessibilityCurveSource} mode={selectedMode} metric={selectedMetric} selectedTime={selectedTime} onModeChange={setSelectedMode} onMetricChange={setSelectedMetric} />
          ) : null}
          {analysisTab === 'planning' ? (
            <PieChartCard title="토지이용계획 비율" subtitle="계획기능 구성비" leftLabel="판교" rightLabel="위례" left={planFunctionSlices.left} right={planFunctionSlices.right} legendName="계획 기능" valueMode={scopeMode} />
          ) : null}
          {analysisTab === 'buildingUse' ? (
            <PieChartCard
              title="건축물 주용도 구성비"
              subtitle="건축물 GIS"
              leftLabel="판교"
              rightLabel="위례"
              left={buildingSlices.left}
              right={buildingSlices.right}
              legendName={buildingMetric === 'area' ? '연면적 기준' : '건물 수 기준'}
              valueMode={`${buildingMode} / ${buildingMetric}`}
            />
          ) : null}
          {analysisTab === 'ratio' ? (
            <section className="chart-card panel-card">
              <div className="chart-head">
                <div>
                  <div className="chart-kicker">
                    <Building2 size={14} />
                    <span>경계·업무지구 용적률</span>
                  </div>
                  <h3>건축물대장 기반 용적률 비교</h3>
                  <p>판교·위례의 경계 용적률과 업무지구 용적률을 건축물대장으로 다시 산정한 값입니다.</p>
                </div>
                <div className="chart-chip">boundary / business</div>
              </div>
              <div className="curve-summary">
                <div className="curve-summary-card">
                  <span>판교 택지 범위 용적률</span>
                  <strong>{formatPercent(boundaryFarSummary.pangyo?.boundary_weighted_far_percent ?? null)}</strong>
                  <small>{formatCompactNumber(boundaryFarSummary.pangyo?.boundary_rows ?? null, 0)}개 건축물</small>
                </div>
                <div className="curve-summary-card">
                  <span>위례 택지 범위 용적률</span>
                  <strong>{formatPercent(boundaryFarSummary.wirye?.boundary_weighted_far_percent ?? null)}</strong>
                  <small>{formatCompactNumber(boundaryFarSummary.wirye?.boundary_rows ?? null, 0)}개 건축물</small>
                </div>
                <div className="curve-summary-card">
                  <span>판교 업무지구 범위(core) 용적률</span>
                  <strong>{formatPercent(boundaryFarSummary.pangyo?.office_weighted_far_percent ?? null)}</strong>
                  <small>{formatCompactNumber(boundaryFarSummary.pangyo?.office_rows ?? null, 0)}개 건축물</small>
                </div>
                <div className="curve-summary-card">
                  <span>위례 업무지구 범위(core) 용적률</span>
                  <strong>{formatPercent(boundaryFarSummary.wirye?.office_weighted_far_percent ?? null)}</strong>
                  <small>{formatCompactNumber(boundaryFarSummary.wirye?.office_rows ?? null, 0)}개 건축물</small>
                </div>
              </div>
              <div className="chart-note">경계 용적률은 Σ(용적률 × 대지면적) / Σ(대지면적)으로 계산했습니다.</div>
              <div className="chart-note">업무지구 용적률은 주용도코드명에 `업무`가 포함된 건축물만 대상으로 같은 방식으로 산정했습니다.</div>
            </section>
          ) : null}
          {analysisTab === 'society' ? (
            <section className="chart-card panel-card">
              <div className="chart-head">
                <div>
                  <div className="chart-kicker">
                    <Users size={14} />
                    <span>인구사회분석</span>
                  </div>
                  <h3>택지 범위와 업무지구 범위 비교</h3>
                  <p>SGIS 집계구를 면적비례 배분해 산정한 택지(full)와 업무지구(core)의 인구·종사자 총량입니다.</p>
                </div>
                <div className="chart-chip">SGIS 2023</div>
              </div>
              <div className="society-metric-grid">
                {societyMetricCards.map((metric) => (
                  <MetricCard
                    key={metric.title}
                    icon={<Users size={16} />}
                    title={metric.title}
                    tooltip="SGIS 집계구를 경계에 따라 면적비례로 배분해 합산한 값입니다."
                    leftLabel={metric.leftLabel}
                    leftValue={metric.leftValue}
                    rightLabel={metric.rightLabel}
                    rightValue={metric.rightValue}
                    note={metric.note}
                  />
                ))}
              </div>
              <div className="society-compare-grid">
                <SocietyComparisonCard
                  title="판교 인구·종사자 분포"
                  subtitle="판교 full vs core"
                  regionLabel="택지 전체와 업무지구 범위를 같은 기준으로 비교"
                  full={planningBoundarySummary.pangyo.full}
                  core={planningBoundarySummary.pangyo.core}
                />
                <SocietyComparisonCard
                  title="위례 인구·종사자 분포"
                  subtitle="위례 full vs core"
                  regionLabel="택지 전체와 업무지구 범위를 같은 기준으로 비교"
                  full={planningBoundarySummary.wirye.full}
                  core={planningBoundarySummary.wirye.core}
                />
              </div>
              <div className="heatmap-gallery">
                {[
                  { src: dataUrl('pangyo_planning_population_heatmap_v2.png'), label: '판교 택지 범위 인구 heatmap' },
                  { src: dataUrl('pangyo_business_population_heatmap_v2.png'), label: '판교 업무지구 범위 인구 heatmap' },
                  { src: dataUrl('wirye_planning_population_heatmap_v2.png'), label: '위례 택지 범위 인구 heatmap' },
                  { src: dataUrl('wirye_business_population_heatmap_v2.png'), label: '위례 업무지구 범위 인구 heatmap' },
                ].map((item) => (
                  <figure className="heatmap-card" key={item.label}>
                    <img src={item.src} alt={item.label} loading="lazy" />
                    <figcaption>{item.label}</figcaption>
                  </figure>
                ))}
              </div>
              <div className="chart-note">old core는 이전 버전의 핵심구역 기준이고, 현재 대시보드의 core는 경계 재정의 후 재산정된 값입니다.</div>
              <div className="chart-note">full은 택지 전체 범위, core는 업무지구 범위입니다. 두 값 모두 SGIS 집계구를 면적비례로 합산했습니다.</div>
              <InfoBullets items={keyInterpretation} />
            </section>
          ) : null}
        </div>
      </section>
    </div>
  );
}

export default App;
