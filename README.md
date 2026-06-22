# 판교테크노밸리·위례신도시 업무지구 비교분석 대시보드

판교테크노밸리와 위례신도시의 업무지구 성과를 공공데이터 기반으로 비교하는 정적 웹 대시보드입니다. 토지이용계획, 건축물대장, GIS 건물정보, SGIS 인구·사업체·종사자 통계, 버스·지하철 접근성을 결합해 두 지역의 계획 대비 기능 실현 정도를 시각화합니다.

배포 URL: <https://jung-ain.github.io/smartcity-final/>

## 분석 범위

| 구분 | 의미 | 주요 활용 |
| --- | --- | --- |
| 택지 범위, `full` | 판교·위례 택지개발지구 전체 또는 분석 대상 택지 범위 | 전체 인구·종사자, 토지이용 구성, 배경 비교 |
| 업무지구 범위, `core` | 업무·상업·자족기능이 집중되도록 재정의한 비교 경계 | 업무지구 성과, 건축물 용도, 용적률, 인구사회 집중도 |
| 역세권·접근성 범위 | 판교역·복정역을 대표 기점으로 산정한 도달권 | 30분·60분 누적 접근 가능 인구·종사자 |

`old core`는 이전 분석 단계에서 사용하던 레거시 핵심구역 경계입니다. 현재 대시보드는 재정의한 `core` 경계를 기준으로 산정한 값을 사용합니다.

## 기준 시점

데이터별 기준 시점이 서로 다르므로, 결과는 단일 시점 패널 분석으로 해석합니다.

| 데이터군 | 기준연도·기준월 | README 표기 기준 |
| --- | --- | --- |
| SGIS 인구·가구·주택·사업체·종사자 통계 | 2023년 | 통계청 제공 통계연도 |
| SGIS 집계구 경계 | 2025년, 2분기 자료 사용 | 파일명 및 SGIS 경계 제공연도 |
| SGIS 격자통계 인구·사업체·종사자 | 2023년 | 통계청 제공 통계연도 |
| SGIS 격자경계 다사 | 2025년 | 통계청 제공 격자경계연도 |
| LH 공공택지정보시스템 공간자료 | 2026년, 수집본 파일 기준 2026년 5월 | 택지정보 다운로드 자료 수집연도·파일명 |
| 연속지적도 서울·경기 | 2026년, 수집본 파일 기준 2026년 6월 | 브이월드 다운로드 자료 수집연도·파일명 |
| 건축물대장 표제부·총괄 표제부 | 2026년, 수집본 기준 2026년 6월 | 건축HUB 개방데이터 수집연도·파일명 |
| 서울 버스정류소 | 2023년 | 서울 열린데이터광장 제공 기준 |
| 성남·하남 버스정류소 | 2026년 | 경기데이터드림 제공 기준 |
| VWorld GIS 건물정보·Geocoder API | 2026년 수집·조회 | API 조회 시점 |
| OpenStreetMap 도로망 | 2026년 수집 | OSM 추출 시점 |

## 데이터 출처

| 분류 | 자료명 | 출처 | 기준 |
| --- | --- | --- | --- |
| 택지 경계 | 경기 지구 경계 공간자료 | LH 공공택지정보시스템. (2026). 공공택지정보시스템. <https://openapi.jigu.go.kr/down/detail.do?table=BLS5_GIS_LAD_USE_PLAN> | 2026년, 수집본 파일 기준 2026년 5월 |
| 토지이용 | 경기 토지이용계획도 공간자료 | LH 공공택지정보시스템. (2026). 공공택지정보시스템. <https://openapi.jigu.go.kr/down/detail.do?table=BLS5_GIS_LAD_USE_PLAN> | 2026년, 수집본 파일 기준 2026년 5월 |
| 획지·가구 | 경기 가구 및 획지 경계도 공간자료 | LH 공공택지정보시스템. (2026). 공공택지정보시스템. <https://openapi.jigu.go.kr/down/detail.do?table=BLS5_GIS_LAD_USE_PLAN> | 2026년, 수집본 파일 기준 2026년 5월 |
| 필지 | 연속지적도 서울 공간자료 | 국토교통부·브이월드. (2026). 브이월드 국가공간정보 다운로드 서비스. <https://www.vworld.kr/dtmk/dtmk_ntads_s002.do?datIde=30563&dsId=30563> | 2026년, 수집본 파일 기준 2026년 6월 |
| 필지 | 연속지적도 경기 공간자료 | 국토교통부·브이월드. (2026). 브이월드 국가공간정보 다운로드 서비스. | 2026년, 수집본 파일 기준 2026년 6월 |
| 건축물대장 | 건축물대장 표제부 데이터 | 국토교통부 건축HUB. (2026). 건축HUB 개방데이터. <https://www.hub.go.kr/portal/opn/tyb/idx-bdrg-ttlldr.do> | 2026년 6월 수집 |
| 건축물대장 | 건축물대장 총괄 표제부 데이터 | 국토교통부 건축HUB. (2026). 건축HUB 개방데이터. <https://www.hub.go.kr/portal/opn/tyb/idx-bdrg-ttlldr.do> | 2026년 6월 수집 |
| 인구사회 | 인구 통계 | 통계청. (2023). SGIS 통계지리정보서비스. <https://sgis.kostat.go.kr> | 2023년 |
| 인구사회 | 가구 통계 | 통계청. (2023). SGIS 통계지리정보서비스. <https://sgis.kostat.go.kr> | 2023년 |
| 인구사회 | 주택 통계 | 통계청. (2023). SGIS 통계지리정보서비스. <https://sgis.kostat.go.kr> | 2023년 |
| 경제활동 | 사업체 통계 | 통계청. (2023). SGIS 통계지리정보서비스. <https://sgis.kostat.go.kr> | 2023년 |
| 경제활동 | 종사자 통계 | 통계청. (2023). SGIS 통계지리정보서비스. <https://sgis.kostat.go.kr> | 2023년 |
| 집계구 | 경기 집계구 경계 공간자료 | 통계청. (2025). SGIS 통계지리정보서비스. <https://sgis.kostat.go.kr> | 2025년, 2분기 |
| 격자 | 격자통계(인구): 다사 500M | 통계청. (2023). SGIS 통계지리정보서비스. <https://sgis.mods.go.kr/view/index> | 2023년 |
| 격자 | 격자통계(사업체): 다사 500M | 통계청. (2023). SGIS 통계지리정보서비스. <https://sgis.mods.go.kr/view/index> | 2023년 |
| 격자 | 격자통계(종사자): 다사 500M | 통계청. (2023). SGIS 통계지리정보서비스. <https://sgis.mods.go.kr/view/index> | 2023년 |
| 격자 | 격자경계: 다사 100K·10K·1K·500M·100M | 통계청. (2025). SGIS 통계지리정보서비스. <https://sgis.mods.go.kr/view/index> | 2025년 |
| 도로망 | OpenStreetMap Road Network Data | OpenStreetMap contributors. (2026). OpenStreetMap. <https://www.openstreetmap.org> | 2026년 수집 |
| 버스 | 서울 버스정류소 위치정보 | 서울특별시. (2023). 서울 열린데이터광장. <https://data.seoul.go.kr/dataList/OA-15067/S/1/datasetView.do> | 2023년 |
| 버스 | 성남시 버스정류소 위치정보 | 경기도. (2026). 경기데이터드림. <https://data.gg.go.kr/portal/data/service/selectServicePage.do?infId=GDKWAGWYRKJYIRVX110226832213&infSeq=1> | 2026년 |
| 버스 | 하남시 버스정류소 위치정보 | 경기도. (2026). 경기데이터드림. <https://data.gg.go.kr/portal/data/service/selectServicePage.do?infId=GDKWAGWYRKJYIRVX110226832213&infSeq=1> | 2026년 |
| GIS 건물 | GIS건물집합정보 WMS 조회 서비스 | 브이월드. (2026). 브이월드 API 서비스. <https://www.vworld.kr/dtna/dtna_apiSvcFc_s001.do> | 2026년 조회 |
| GIS 건물 | GIS건물일반정보 WMS 조회 서비스 | 브이월드. (2026). 브이월드 API 서비스. <https://www.vworld.kr/dtna/dtna_apiSvcFc_s001.do> | 2026년 조회 |
| 지오코딩 | Geocoder API 2.0 레퍼런스 | 브이월드. (2026). 브이월드 개발자센터. <https://www.vworld.kr/dev/v4dv_geocoderguide2_s001.do> | 2026년 조회 |

## 전처리 과정

원자료는 용량과 라이선스 문제로 저장소에 포함하지 않습니다. 대시보드에는 전처리 후 정적 배포가 가능한 산출물만 `public/data/`에 포함합니다.

| 단계 | 주요 스크립트 | 처리 내용 | 주요 산출물 |
| --- | --- | --- | --- |
| 1. 경계·토지이용 정리 | `scripts/compute_boundary_area_population_workers_v2.py` | 판교·위례 택지 범위와 업무지구 범위의 면적, SGIS 결합용 경계 정리 | `planning_boundary_population_workers_area_v2.json` |
| 2. 건축물 GIS 수집·요약 | `scripts/fetch_vworld_gis_buildings_v11.py`, `scripts/merge_vworld_with_building_register_summary_v12.py` | VWorld GIS 건물정보와 건축물대장 속성을 결합해 용도·연면적·용적률 지표 생성 | `buildings_summary_v35.json`, `buildings_gis_summary_v35.json` |
| 3. 건축물대장 경계 필터 | `scripts/merge_vworld_with_building_register_summary_v12.py` | 건축물대장 후보를 판교·위례 경계에 매칭하고 업무용 건축물 용적률 산정 | `building_register_boundary_office_far_summary.json` |
| 4. 집계구 인구·종사자 배분 | `scripts/compute_boundary_area_population_workers_v2.py`, `scripts/build_planning_boundary_population_worker_heatmaps_v2.py` | SGIS 집계구 통계를 경계 중첩 면적비로 배분해 택지·업무지구 총량과 히트맵 생성 | `planning_boundary_population_workers_area_v2.json`, `*_population_heatmap_v2.png` |
| 5. 버스 접근성 | `scripts/fetch_and_process_bus_accessibility_v4.py`, `scripts/build_bus_station_population_workers_500m.py`, `scripts/export_bus_access_path_edges_vector.py` | 판교역·복정역 0~60분 버스 도달 정류장, 경로, 정류장 500m권 인구·종사자 산정 | `dashboard_bus_access_*.json`, `bus_access_*.geojson` |
| 6. 지하철 접근성 | `scripts/build_v29_pangyo_bokjeong_mode_accessibility.py`, `scripts/build_subway_station_population_workers_750m_grid_v2.py` | 지하철 네트워크 기반 0~60분 도달역 산정, 도달역 750m 도보권의 격자 인구·종사자 결합 | `pangyo_bokjeong_mode_accessibility_*.json`, `subway_station_population_workers_750m_grid_v2.csv` |
| 7. 대시보드 자산 빌드 | `scripts/build_frontend2_assets_v35.py` | 분석 산출물을 GitHub Pages용 정적 JSON·GeoJSON으로 정리 | `public/data/*.json`, `public/data/*.geojson` |

## 주요 산정 기준

- SGIS 집계구 통계는 분석 경계와 집계구가 겹치는 면적 비율로 배분했습니다.
- SGIS 격자통계는 500m 격자를 사용해 버스 정류장 500m권과 지하철역 750m 도보권의 인구·사업체·종사자를 산정했습니다.
- 지하철 15분 도보권은 보고서 작성 시 평균 보행권 반경인 750m 기준으로 설명합니다.
- 버스 접근성은 판교역·복정역 출발 기준 0~60분 누적 도달 정류장과 해당 정류장 주변 500m 통계를 사용합니다.
- 지하철 접근성은 판교역·복정역 출발 기준 0~60분 내 도달 가능한 역 목록을 만든 뒤, 각 역 750m권의 인구·종사자를 합산합니다.
- 용적률은 `Σ(용적률 × 대지면적) / Σ(대지면적)`으로 산정했습니다.
- 업무지구 용적률은 건축물대장 `주용도코드명`에 `업무`가 포함된 건축물만 대상으로 같은 방식으로 산정했습니다.
- VWorld Geocoder API 결과 좌표는 약관을 고려해 저장하지 않고, 실행 중 경계 포함 여부 판정에만 사용했습니다.

## 대시보드 데이터 구성

대시보드가 직접 읽는 파일 목록은 `docs/used_data_inventory.md`에 정리되어 있습니다. 주요 파일은 다음과 같습니다.

| 파일 | 용도 |
| --- | --- |
| `public/data/final_landuse_scope_boundaries_v16.geojson` | 판교·위례 분석 범위 경계 |
| `public/data/full_boundary_v25.geojson` | 택지 범위 경계 |
| `public/data/final_core_boundaries_v14.geojson` | 업무지구 범위 경계 |
| `public/data/map_full_planning_landuse_pangyo_v24.geojson` | 판교 택지 토지이용 지도 |
| `public/data/map_full_planning_landuse_wirye_v24.geojson` | 위례 택지 토지이용 지도 |
| `public/data/buildings_summary_v35.json` | 건축물 요약 지표 |
| `public/data/building_register_boundary_office_far_summary.json` | 건축물대장 기반 용적률 지표 |
| `public/data/planning_boundary_population_workers_area_v2.json` | 택지·업무지구 인구·종사자 요약 |
| `public/data/dashboard_bus_access_pangyo_bokjeong_0_60min_station_population_workers_500m.json` | 버스 접근성 누적 지표 |
| `public/data/subway_station_population_workers_750m_grid_v2.csv` | 지하철역 750m 도보권 격자 인구·종사자 |
| `public/data/pangyo_bokjeong_mode_accessibility_curve_v30.json` | 0~60분 교통 접근성 곡선 |

## 실행 방법

```bash
npm install
npm run dev
npm run build
npm run preview
```

## 저장소 포함·제외 기준

포함:

- GitHub Pages 배포에 필요한 `src/`, `public/data/`, `docs/`, `scripts/`
- 전처리 결과 중 대시보드가 직접 참조하는 JSON, GeoJSON, CSV, PNG
- 전처리 재현을 위한 Python 스크립트

제외:

- 원본 SHP, SHX, DBF, PRJ, CPG
- 대용량 원본 CSV
- API 원본 응답 전문
- 지오코딩 좌표 캐시 또는 좌표 저장 파일
- 임시 로그, 캡처 이미지, 중간 실험 산출물

## 한계와 해석 유의사항

- 통계, 경계, 건축물, 교통 자료의 기준연도와 기준월이 완전히 동일하지 않습니다.
- SGIS 집계구와 격자 통계는 면적비례 배분 또는 반경 기반 결합을 사용하므로 행정구역 공표값과 정확히 일치하지 않을 수 있습니다.
- 건축물대장, VWorld GIS 건물정보, 연속지적도는 PNU·주소·경계 매칭 과정에서 결측이나 불일치가 발생할 수 있습니다.
- 접근성 지표는 네트워크 전처리 결과와 도달권 반경 가정에 의존합니다.
- 본 대시보드는 판교와 위례의 상대 비교와 공간적 해석을 목적으로 하며, 법정 경계 확정이나 행정 통계 공표값을 대체하지 않습니다.
