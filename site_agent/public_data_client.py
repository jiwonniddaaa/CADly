# public_client.py
import httpx
import logging
from .config import PublicDataConfig

logger = logging.getLogger(__name__)

class PublicDataClient:
    def __init__(self, config: PublicDataConfig):
        self.config = config

    async def fetch_building_data(self, operation_key: str, pnu_code: str, bun: str = "0000", ji: str = "0000"):
        """
        [건축HUB API 호출 엔진]
        공공데이터 API 서버가 마비되거나 중단되었을 경우 Exception을 잡아 상위로 전집합니다.
        """
        if operation_key == "land_limit":
            base_url = self.config.land_base_url
            service_key = self.config.land_service_key
        else:
            base_url = self.config.bld_base_url
            service_key = self.config.bld_service_key
        
        if operation_key not in self.config.endpoints:
            raise ValueError(f"정의되지 않은 오퍼레이션 키입니다: {operation_key}")
        
        url = f"{base_url}{self.config.endpoints[operation_key]}"
        
        params = {
            "serviceKey": service_key,
            "sigunguCd": pnu_code[:5] if pnu_code else "11110", 
            "bjdongCd": pnu_code[5:10] if pnu_code else "10100",
            "platGbCd": "0",       
            "bun": str(bun).zfill(4),
            "ji": str(ji).zfill(4),
            "numOfRows": "10",
            "pageNo": "1",
            "_type": "json" 
        }

        # 타임아웃을 5초로 줄여 API 중단 시 로컬 DB로 빠르게 전환되도록 인프라 튜닝
        async with httpx.AsyncClient(verify=False) as client:
            try:
                response = await client.get(url, params=params, timeout=5.0)
                if response.status_code == 200:
                    return response.json()
                return None
            except Exception as e:
                logger.warning(f"⚠️ 공공데이터 API 서버 호출 중단/지연 발생 ({operation_key}): 로컬 DB 덤프 스위칭을 트리거합니다.")
                return None