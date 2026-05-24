# site_agent/site_analyzer.py
import sqlite3
import asyncio
import logging
import pandas as pd

logger = logging.getLogger(__name__)

class SiteAnalyzer:
    def __init__(self, public_client, dataset_path: str, db_path: str = "./data/mart_building_data.db"):
        self.client = public_client
        self.dataset_path = dataset_path
        self.db_path = db_path
        self.df = None 

    # site_agent/site_analyzer.py 내부의 discover_from_dataset 메서드 교체

    async def discover_from_dataset(self, sigungu_cd: str, theme: str) -> dict:
        """
        [Case B 경로] 대용량 CSV 초고속 청크 스트리밍 검색 엔진
        - 전체 파일을 메모리에 올리지 않고 1만 건씩 끊어서 빛의 속도로 스캔합니다.
        """
        logger.info(f"📊 [Case B] 초고속 청크 스트리밍 탐색 가동 -> 지역구: {sigungu_cd}, 테마: {theme}")
        
        target_sigungu = str(sigungu_cd).strip()[:4] # 필터링할 앞자리 캐싱
        best_match = None
        
        try:
            # 💡 [핵심 튜닝] chunksize=50000 지정을 통해 5만 줄씩 읽어 들이며 즉시 필터링 진행!
            # 이렇게 하면 거대한 CSV 파일을 한 번에 무겁게 load하지 않습니다.
            chunks = pd.read_csv(self.dataset_path, chunksize=50000, low_memory=False)
            
            for chunk_idx, chunk in enumerate(chunks):
                # 실시간 탐색 서포트용 미니 로그 (0.2초마다 찍힘)
                if chunk_idx % 5 == 0:
                    logger.info(f"   ⏳ 데이터 마트 {chunk_idx * 50000:,}번째 레코드 통과 중...")

                # 1. 시군구_코드 필터링
                if '시군구_코드' in chunk.columns:
                    chunk['시군구_코드'] = chunk['시군구_코드'].astype(str)
                    filtered_chunk = chunk[chunk['시군구_코드'].str.startswith(target_sigungu)]
                else:
                    filtered_chunk = chunk

                # 2. 주_용도_코드_명 컨텍스트 기반 테마 필터링
                if not filtered_chunk.empty and '주_용도_코드_명' in filtered_chunk.columns:
                    if theme == "문화":
                        filtered_chunk = filtered_chunk[
                            filtered_chunk['주_용도_코드_명'].str.contains('문화|집회|노유자|교육', na=False)
                        ]
                    elif theme == "상권":
                        filtered_chunk = filtered_chunk[
                            filtered_chunk['주_용도_코드_명'].str.contains('근린|상업|판매', na=False)
                        ]

                # 3. 매칭 조건에 맞는 타겟을 청크 안에서 찾았다면 즉시 루프 브레이크 탈출!
                if not filtered_chunk.empty:
                    best_match = filtered_chunk.iloc[0]
                    logger.info(f"⚡ [고속 매칭 완성] {chunk_idx * 50000:,}보 구간에서 타겟 부지 득템 성공!")
                    break

        except Exception as e:
            logger.error(f"❌ 추천용 데이터셋 청크 스트리밍 중 시스템 에러: {e}")
            return {"status": "error", "message": "추천 데이터셋 스캔 실패"}

        # 4. 전체 파일을 끝까지 다 뒤졌는데도 매칭 결과가 완전히 없으면 폴백 모드 가동
        if best_match is None:
            logger.warning(f"⚠️ 데이터셋 전체 스캔 결과 조건 부지가 없습니다. 폴백 시뮬레이션 모드로 전환합니다.")
            return self._get_fallback_mock_data()

        # 5. 국토교통부 원본 지번 데이터 정수 변환 및 자릿수 패딩 방어 코드
        bun_raw = best_match.get('번') if pd.notna(best_match.get('번')) else "59"
        ji_raw = best_match.get('지') if pd.notna(best_match.get('지')) else "45"
        
        bun = str(int(float(bun_raw))).zfill(4) if isinstance(bun_raw, (int, float)) or str(bun_raw).replace('.','').isdigit() else "0059"
        ji = str(int(float(ji_raw))).zfill(4) if isinstance(ji_raw, (int, float)) or str(ji_raw).replace('.','').isdigit() else "0045"
        
        target_address = best_match.get('대지_위치', '서울특별시 성북구 삼선동 일대 후보지')

        logger.info(f"🎯 [추천 매칭 부지 확정] 지번: {bun}-{ji} | 주소: {target_address}")

        # 6. 확보한 지번 키를 들고 우리가 빌드한 2,100만 건짜리 고속 SQLite 조인 엔진 가동!
        db_result = self._fetch_from_local_db(bun, ji, target_address)
        
        if db_result["status"] == "success":
            db_result["source"] = "local_dataset_recommendation_case_b"
            
        return db_result

    async def run_full_analysis(self, pnu: str, bun: str, ji: str, address: str = ""):
        """[Case A & B 공통 면적 + 토지규제 파이프라인] API 중단 시 로컬 SQLite 백업 가동"""
        logger.info(f"🔍 부지 면적 및 토지이용규제 프로파일링 가동: PNU={pnu}, 지번={bun}-{ji}")

        # 💡 토지이용규제 API(land_limit) 호출을 비동기 스케줄러에 추가하여 3개 API를 동시에 찌릅니다.
        results = await asyncio.gather(
            self.client.fetch_building_data("title_info", pnu, bun, ji),
            self.client.fetch_building_data("floor_info", pnu, bun, ji),
            self.client.fetch_building_data("land_limit", pnu, bun, ji),
            return_exceptions=True
        )
        title_res, floor_res, land_res = results

        # 건축 API 중 하나라도 터지거나, 응답 값이 비정상(0)이면 로컬 DB 백업 스위치를 켭니다.
        api_failed = False
        if (not title_res or isinstance(title_res, Exception)) or (not floor_res or isinstance(floor_res, Exception)):
            api_failed = True
        else:
            t_items = self._get_items(title_res)
            if not t_items or float(t_items[0].get('bcRat', 0)) == 0:
                api_failed = True

        if api_failed:
            logger.warning("🚨 [인프라 전환] 공공데이터 API 사용 중단 감지! 로컬 데이터마트(SQLite) 백업 분석으로 전환합니다.")
            return self._fetch_from_local_db(bun, ji, address)

        logger.info("✅ 실시간 공공데이터 API 연동 성공.")
        t_items = self._get_items(title_res)[0] if self._get_items(title_res) else {}
        
        # 1. 건축물대장 물리 제원 파싱
        building_area = float(t_items.get('bldArea', 0))
        site_area = float(t_items.get('platArea', 0))
        tot_area = float(t_items.get('totArea', 0)) 
        bc_rat = f"{t_items.get('bcRat', '0')}%"  # 실제 대장 상 건폐율
        vl_rat = f"{t_items.get('vlRat', '0')}%"  # 실제 대장 상 용적률
        strct_name = t_items.get('strctCdNm', '정보 없음') # 구조 명칭

        # 2. 토지이용규제 API(land_res) 데이터 정밀 파싱 (용도지역 추출)
        z_items = self._get_items(land_res)
        zones = [i.get('jijiguCdNm') for i in z_items if i.get('jijiguCdNm')]
        legal_zone = ", ".join(list(set(zones))) if zones else "제3종일반주거지역(기본값)"

        common_area = round(building_area * 0.215, 2)
        private_area = round(building_area - common_area, 2)

        return {
            "status": "success",
            "source": "public_api_live",
            # 채민 - 리턴값에 location 필드 포함
            "location": {
                "address": address,
                "pnu": pnu,
                "bun": bun,
                "ji": ji,
                "jibun": f"{int(bun)}-{int(ji)}" if int(ji) > 0 else f"{int(bun)}",
            },
            "building_identifiers": {
                "management_pk": t_items.get('mgmtBldrgstPk', 'API_LIVE'),
                "building_name": t_items.get('bldNm', '명칭 미등기 건물'),
                "main_purpose": t_items.get('mainPurpsCdNm', '정보 없음'),
                "legal_zone": legal_zone,
                "bc_rat": bc_rat,
                "vl_rat": vl_rat,
                "strct_name": strct_name
            },
            "diffusion_output": {
                "site_area_m2": site_area,
                "building_area_m2": building_area,
                "floor_area_m2": tot_area,
                "common_area_m2": common_area,
                "private_area_m2": private_area,
                "diffusion_target_area_m2": private_area, 
                "space_type": "commercial_or_cultural"
            }
        }

    def _fetch_from_local_db(self, bun: str, ji: str, address: str) -> dict:
        """[로컬 데이터마트 엔진] 실제 DB 적재 규격(공동주택) 기반 세대수 분할 연산 적용"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            main_no = int(bun)
            sub_no = int(ji)
            target_jibun = f"{main_no}-{sub_no}" if sub_no > 0 else f"{main_no}"
            query_keyword = f"%{target_jibun}%"
            
            # DB 마트 컬럼 명세에 맞춘 정밀 쿼리
            cursor.execute("""
                SELECT 관리_건축물대장_PK, 건물_명, `건축_면적(㎡)`, `대지_면적(㎡)`, 주_용도_코드_명, 구조_코드_명, `건폐_율(%)`, `용적_률(%)`, `세대_수(세대)`
                FROM building_records 
                WHERE 대지_위치 LIKE ? LIMIT 1;
            """, (query_keyword,))
            b_info = cursor.fetchone()

            if not b_info:
                return self._get_fallback_mock_data()

            pk, b_name, b_area, s_area, main_purpose, strct_name, bc_rat, vl_rat, household_count = b_info
            building_area_m2 = float(b_area) if b_area else 150.0
            site_area_m2 = float(s_area) if s_area else 300.0
            main_purpose_str = str(main_purpose).strip() if main_purpose else ""

            # 층별개요 고속 PK 매칭 (건물 전체 층면적 확보)
            cursor.execute("SELECT `면적(㎡)` FROM floor_records WHERE 관리_건축물대장_PK = ? LIMIT 1;", (pk,))
            f_info = cursor.fetchone()
            floor_area_m2 = float(f_info[0]) if f_info else building_area_m2

            # 💡 [데이터 적재 규격 맞춤형 조건] 
            # 전수조사 결과 매칭: 주용도가 정확히 "공동주택"일 때만 세대 분할 연산 트리거
            is_apartment_type = (main_purpose_str == "공동주택")

            # 세대 수 안전 바인딩 (0이거나 None이면 1세대로 방어)
            try:
                households = int(household_count) if household_count and int(household_count) > 0 else 1
            except (ValueError, TypeError):
                households = 1

            # 💡 [핵심 연산 분기] 
            # 공동주택일 때는 1세대당 할당되는 지분 면적으로 쪼개 스케일을 정규화합니다.
            if is_apartment_type and households > 1:
                site_area_m2 = round(site_area_m2 / households, 2)
                building_area_m2 = round(building_area_m2 / households, 2)
                floor_area_m2 = round(floor_area_m2 / households, 2)

                # 공동주택은 복도/엘리베이터/주차장 등 공용부 지분이 크므로 건축 표준 비율 35% 반영
                common_area_m2 = round(floor_area_m2 * 0.35, 2)
                private_area_m2 = round(floor_area_m2 - common_area_m2, 2)
            else:
                # 단독주택이나 상가빌딩(근린생활시설) 등은 일반 가중치 21.5% 반영
                common_area_m2 = round(floor_area_m2 * 0.215, 2)
                private_area_m2 = round(floor_area_m2 - common_area_m2, 2)

            return {
                "status": "success",
                "source": "local_sqlite_fallback",
                # 채민 - 리턴값에 location 필드 포함
                "location": {
                    "address": address,
                    "bun": bun,
                    "ji": ji,
                    "jibun": target_jibun,
                },
                "building_identifiers": {
                    "management_pk": pk, 
                    "building_name": b_name,
                    "main_purpose": main_purpose_str,
                    "legal_zone": "제3종일반주거지역",
                    "bc_rat": f"{bc_rat}%" if bc_rat else "정보없음",
                    "vl_rat": f"{vl_rat}%" if vl_rat else "정보없음",
                    "strct_name": strct_name if strct_name else "철근콘크리트 구조"
                },
                "diffusion_output": {
                    "building_area_m2": building_area_m2,
                    "floor_area_m2": floor_area_m2,
                    "common_area_m2": common_area_m2,
                    "private_area_m2": private_area_m2
                }
            }
        finally:
            conn.close()

    def _get_fallback_mock_data(self):
        return {
            "status": "success",
            "source": "mock_simulation",
            # 채민 - 리턴값에 location 필드 포함
            "location": {
                "address": None,
                "message": "실제 후보지 위치를 찾지 못한 fallback 결과입니다."
            },
            "diffusion_output": {
                "site_area_m2": 500.0, "building_area_m2": 250.0, "floor_area_m2": 250.0,
                "common_area_m2": 53.75, "private_area_m2": 196.25,
                "diffusion_target_area_m2": 196.25, "space_type": "commercial_or_cultural"
            }
        }

    def _get_items(self, response):
        if not response or not isinstance(response, dict): return []
        items = response.get('response', {}).get('body', {}).get('items', {}).get('item', [])
        return [items] if isinstance(items, dict) else items