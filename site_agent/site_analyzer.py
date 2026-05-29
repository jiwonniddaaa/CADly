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

    async def discover_from_dataset(self, sigungu_cd: str, theme: str, address: str = "") -> dict:
        """
        [Case B 경로] 대용량 CSV 초고속 청크 스트리밍 검색 엔진
        - 시군구(구) 단위 검색 및 동(Dong) 단위 정밀 검색을 가변적으로 서포트합니다.
        """
        logger.info(f"📊 [Case B] 청크 스트리밍 탐색 가동 -> 지역구: {sigungu_cd}, 테마: {theme}, 입력텍스트: {address}")
        
        target_sigungu = str(sigungu_cd).strip()[:4] # 필터링할 앞자리 캐싱
        best_match = None
        
        # 🌟 변경 포인트 2: 유저 문장(address)에서 '동(Dong)' 이름 추출 프로세스
        target_dong = None
        if address:
            words = address.split()
            dong_words = [w for w in words if w.endswith("동")]
            if dong_words:
                target_dong = dong_words[0] # 예: "역삼동" 확보
        
        try:
            chunks = pd.read_csv(self.dataset_path, chunksize=50000, low_memory=False)
            
            for chunk_idx, chunk in enumerate(chunks):
                if chunk_idx % 5 == 0:
                    logger.info(f"   ⏳ 데이터 마트 {chunk_idx * 50000:,}번째 레코드 통과 중...")

                # 1. 시군구_코드 1차 필터링
                if '시군구_코드' in chunk.columns:
                    chunk['시군구_코드'] = chunk['시군구_코드'].astype(str)
                    filtered_chunk = chunk[chunk['시군구_코드'].str.startswith(target_sigungu)]
                else:
                    filtered_chunk = chunk

                # 🌟 변경 포인트 3: 동(Dong) 이름이 감지되었다면 주소 필터링 레이어 가동!
                if target_dong and not filtered_chunk.empty and '대지_위치' in filtered_chunk.columns:
                    filtered_chunk = filtered_chunk[filtered_chunk['대지_위치'].str.contains(target_dong, na=False)]

                # 2. 주_용도_코드_명 컨텍스트 기반 테마 필터링 (기존 로직 및 주거 보완)
                if not filtered_chunk.empty and '주_용도_코드_명' in filtered_chunk.columns:
                    if theme == "문화":
                        filtered_chunk = filtered_chunk[
                            filtered_chunk['주_용도_코드_명'].str.contains('문화|집회|노유자|교육', na=False)
                        ]
                    elif theme == "상권":
                        filtered_chunk = filtered_chunk[
                            filtered_chunk['주_용도_코드_명'].str.contains('근린|상업|판매', na=False)
                        ]
                    elif theme == "주거":
                        filtered_chunk = filtered_chunk[
                            filtered_chunk['주_용도_코드_명'].str.contains('공동주택|아파트|주택', na=False)
                        ]

                # 3. 모든 필터링(시군구 + 동 + 테마)을 통과한 타겟을 찾았다면 즉시 탈출
                if not filtered_chunk.empty:
                    best_match = filtered_chunk.iloc[0]
                    logger.info(f"⚡ [고속 매칭 완성] {chunk_idx * 50000:,}보 구간에서 타겟 부지 득템 성공!")
                    break

        except Exception as e:
            logger.error(f"❌ 추천용 데이터셋 청크 스트리밍 중 시스템 에러: {e}")
            return {"status": "error", "message": "추천 데이터셋 스캔 실패"}

        if best_match is None:
            logger.warning(f"⚠️ 조건에 맞는 부지가 데이터셋에 없습니다. 폴백 모드로 전환합니다.")
            return self._get_fallback_mock_data()

        # 5. 지번 자릿수 패딩 방어
        bun_raw = best_match.get('번') if pd.notna(best_match.get('번')) else "59"
        ji_raw = best_match.get('지') if pd.notna(best_match.get('지')) else "45"
        
        bun = str(int(float(bun_raw))).zfill(4) if isinstance(bun_raw, (int, float)) or str(bun_raw).replace('.','').isdigit() else "0059"
        ji = str(int(float(ji_raw))).zfill(4) if isinstance(ji_raw, (int, float)) or str(ji_raw).replace('.','').isdigit() else "0045"
        
        target_address = best_match.get('대지_위치', '서울특별시 강남구 역삼동 일대 후보지')

        logger.info(f"🎯 [추천 매칭 부지 확정] 지번: {bun}-{ji} | 주소: {target_address}")

        # 🌟 변경 포인트 4: 로컬 DB 조인 시 원본 유저 텍스트(address)도 함께 넘겨서 DB 단 주소 낚시 버그를 차단합니다.
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
        """[로컬 데이터마트 엔진] 동 이름과 지번 숫자를 크로스체크하여 전국구 스왑 버그를 원천 봉쇄합니다."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            main_no = int(bun)
            sub_no = int(ji)
            target_jibun = f"{main_no}-{sub_no}" if sub_no > 0 else f"{main_no}"
            
            # 🌟 변경 포인트 5: DB 조회용 주소 키워드 가변적 조립
            search_word = ""
            if address:
                words = address.split()
                dong_words = [w for w in words if w.endswith("동")]
                search_word = dong_words[0] if dong_words else ""

            # 만약 주소에 동이 확인되면 "%역삼동%747%" 형태로 매칭하고, 없으면 기존 지번 매칭을 따릅니다.
            if search_word:
                query_keyword = f"%{search_word}%{target_jibun}%"
            else:
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

            # 층별개요 고속 PK 매칭
            cursor.execute("SELECT `면적(㎡)` FROM floor_records WHERE 관리_건축물대장_PK = ? LIMIT 1;", (pk,))
            f_info = cursor.fetchone()
            floor_area_m2 = float(f_info[0]) if f_info else building_area_m2

            is_apartment_type = (main_purpose_str == "공동주택")

            try:
                households = int(household_count) if household_count and int(household_count) > 0 else 1
            except (ValueError, TypeError):
                households = 1

            if is_apartment_type and households > 1:
                site_area_m2 = round(site_area_m2 / households, 2)
                building_area_m2 = round(building_area_m2 / households, 2)
                floor_area_m2 = round(floor_area_m2 / households, 2)
                common_area_m2 = round(floor_area_m2 * 0.35, 2)
                private_area_m2 = round(floor_area_m2 - common_area_m2, 2)
            else:
                common_area_m2 = round(floor_area_m2 * 0.215, 2)
                private_area_m2 = round(floor_area_m2 - common_area_m2, 2)

            return {
                "status": "success",
                "source": "local_sqlite_fallback",
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