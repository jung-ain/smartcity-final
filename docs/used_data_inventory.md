# Used Data Inventory

`src/App.tsx`에서 `loadJson`, `loadCsvRows`, `dataUrl`로 직접 참조하는 파일만 유지 대상으로 정리했다.

| 파일 경로 | 사용 위치 | 용도 | 유지 여부 |
| --- | --- | --- | --- |
| `public/data/map_full_planning_landuse_pangyo_v24.geojson` | `src/App.tsx` | 판교 택지 범위 토지이용 지도 | 유지 |
| `public/data/map_full_planning_landuse_wirye_v24.geojson` | `src/App.tsx` | 위례 택지 범위 토지이용 지도 | 유지 |
| `public/data/final_landuse_scope_boundaries_v16.geojson` | `src/App.tsx` | 분석 범위 및 토지이용 scope 경계 | 유지 |
| `public/data/full_boundary_v25.geojson` | `src/App.tsx` | 택지개발지역 전체 경계 | 유지 |
| `public/data/final_core_boundaries_v14.geojson` | `src/App.tsx` | 업무지구 core 경계 | 유지 |
| `public/data/final_station_support_boundaries_v14.geojson` | `src/App.tsx` | 역세권/지원지역 경계 | 유지 |
| `public/data/station_markers_v35.geojson` | `src/App.tsx` | 핵심역 마커 | 유지 |
| `public/data/bus_access_pangyo_bokjeong_0_60min_station_population_workers_500m.geojson` | `src/App.tsx` | 버스 정류장 도달권 지도 마커 | 유지 |
| `public/data/dashboard_bus_access_pangyo_bokjeong_0_60min_station_population_workers_500m.json` | `src/App.tsx` | 버스 접근성 카드/차트 집계 | 유지 |
| `public/data/subway_station_population_workers_750m_grid_v2.csv` | `src/App.tsx` | 지하철역 750m 격자 기반 접근 인구·종사자 | 유지 |
| `public/data/pangyo_bokjeong_mode_accessibility_summary_v30.json` | `src/App.tsx` | 교통 접근성 요약 지표 | 유지 |
| `public/data/pangyo_bokjeong_mode_accessibility_curve_v30.json` | `src/App.tsx` | 접근성 곡선 기본 데이터 | 유지 |
| `public/data/buildings_gis_summary_v35.json` | `src/App.tsx` | 건축물 GIS 용도 구성 요약 | 유지 |
| `public/data/buildings_summary_v35.json` | `src/App.tsx` | 건축물 요약 통계 | 유지 |
| `public/data/final_core_performance_v14.json` | `src/App.tsx` | core 구역 성과 지표 | 유지 |
| `public/data/final_station_support_v14.json` | `src/App.tsx` | station/support 구역 성과 지표 | 유지 |
| `public/data/sgis_core_key_indicators_v2.json` | `src/App.tsx` | SGIS 기반 핵심 인구사회 지표 | 유지 |
| `public/data/pangyo_bokjeong_mode_isochrones_v30.geojson` | `src/App.tsx` | 버스/지하철 등시간권 레이어 | 유지 |
| `public/data/subway_network_lines_edit_v1.geojson` | `src/App.tsx` | 지하철 노선 배경 레이어 | 유지 |
| `public/data/reachable_subway_routes_pangyo_bokjeong_v36.geojson` | `src/App.tsx` | 접근 가능한 지하철 route 레이어 | 유지 |
| `public/data/reachable_subway_nodes_pangyo_bokjeong_v36.geojson` | `src/App.tsx` | 접근 가능한 지하철 node 레이어 | 유지 |
| `public/data/bus_access_pangyo_bokjeong_0_60min_path_edges.geojson` | `src/App.tsx` | 버스 경로 edge 레이어 | 유지 |
| `public/data/buildings_full_pangyo_v35.geojson` | `src/App.tsx` | 판교 전체 건축물 지도 | 유지 |
| `public/data/buildings_full_wirye_v35.geojson` | `src/App.tsx` | 위례 전체 건축물 지도 | 유지 |
| `public/data/buildings_core_pangyo_v35.geojson` | `src/App.tsx` | 판교 core 건축물 지도 | 유지 |
| `public/data/buildings_core_wirye_v35.geojson` | `src/App.tsx` | 위례 core 건축물 지도 | 유지 |
| `public/data/pangyo_planning_population_heatmap_v2.png` | `src/App.tsx` | 판교 택지 범위 인구 히트맵 | 유지 |
| `public/data/pangyo_business_population_heatmap_v2.png` | `src/App.tsx` | 판교 업무지구 범위 인구 히트맵 | 유지 |
| `public/data/wirye_planning_population_heatmap_v2.png` | `src/App.tsx` | 위례 택지 범위 인구 히트맵 | 유지 |
| `public/data/wirye_business_population_heatmap_v2.png` | `src/App.tsx` | 위례 업무지구 범위 인구 히트맵 | 유지 |

## 대용량 유지 파일

`public/data/bus_access_pangyo_bokjeong_0_60min_path_edges.geojson`는 약 47.6MB로 가장 크지만, 현재 대시보드의 버스 경로 레이어가 직접 참조하므로 유지한다.
