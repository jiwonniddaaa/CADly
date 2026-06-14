import httpx
import logging
from .config import NaverConfig

logger = logging.getLogger(__name__)

class NaverMapClient:
    def __init__(self, config: NaverConfig):
        self.config = config

    async def fetch_location_by_address(self, address: str):
        """[Case A] 주소 입력 -> 좌표 및 지번 추출"""
        params = {"query": address}
        geo_data = await self._request(self.config.base_url, params, is_reverse=False)
        
        if not geo_data:
            return None

        # 좌표로 Case B를 호출하여 PNU 코드 보완
        refined_data = await self.fetch_location_by_coords(geo_data['lat'], geo_data['lng'])
        
        if refined_data and refined_data.get('status') == 'OK':
            geo_data['pnu_code'] = refined_data.get('pnu_code')
            geo_data['legal_address'] = refined_data.get('address')
            geo_data['bun'] = refined_data.get('bun')
            geo_data['ji'] = refined_data.get('ji')
            
        return geo_data

    async def fetch_location_by_coords(self, lat: float, lng: float):
        """[Case B] 좌표 -> 주소 및 법정동 정보 추출 (Reverse Geocoding)"""
        params = {
            "coords": f"{lng},{lat}",
            "orders": "legalcode,admcode,addr,roadaddr",
            "output": "json",
            "request": "coordsToaddr",
            "sourcecrs": "epsg:4326"
        }
        return await self._request(self.config.reverse_base_url, params, is_reverse=True)

    async def _request(self, url: str, params: dict, is_reverse: bool):
        """네이버 API 공통 요청 처리 로직"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=self.config.get_headers(), params=params)
                if response.status_code != 200:
                    return None

                data = response.json()
                # 이 부분이 핵심: is_reverse 값에 따라 다른 파서를 호출합니다.
                return self._parse_reverse_geo(data) if is_reverse else self._parse_geo(data)
                
            except Exception as e:
                logger.error(f"요청 중 예외 발생: {e}")
                return None

    def _parse_geo(self, data):
        """Geocoding 응답 파싱"""
        if not data or data.get('status') != 'OK' or not data.get('addresses'):
            return None
            
        addr = data['addresses'][0]
    
        elements = {el['types'][0]: el['longName'] for el in addr.get('addressElements', [])}
        land_number = elements.get('LAND_NUMBER', "")
        
        main_no, sub_no = "0", "0"
        if land_number:
            if "-" in land_number:
                parts = land_number.split("-")
                main_no = parts[0]
                sub_no = parts[1]
            else:
                main_no = land_number

        return {
            "status": "OK",
            "address": addr.get('roadAddress') or addr.get('jibunAddress'),
            "lat": float(addr['y']),
            "lng": float(addr['x']),
            "bun": main_no.zfill(4),
            "ji": sub_no.zfill(4)
        }

    def _parse_reverse_geo(self, data):
        """Reverse Geocoding 응답 파싱: 좌표 -> 법정동 코드"""
        results = data.get('results')
        if not results:
            return {"status": "NOT_FOUND", "address": "주소 없음", "pnu_code": None}

        # 1. 법정동 명칭과 코드를 위한 'legalcode' 레이어
        legal_info = next((res for res in results if res['name'] == 'legalcode'), results[0])
        pnu_base = legal_info.get('code', {}).get('id')

        # 2. 상세 번지수(343-1)를 가져오기 위한 'addr' 레이어 추출
        addr_info = next((res for res in results if res['name'] == 'addr'), None)
        main_no, sub_no = "0", "0"
        detail_address = ""
        
        if addr_info:
            region = addr_info['region']
            land = addr_info.get('land', {})
            main_no = land.get('number1', "0")
            sub_no = land.get('number2', "0")
            
            # 주소 구성 요소 (시/도 + 구 + 동)
            addr_parts = [
                region['area1']['name'],
                region['area2']['name'],
                region['area3']['name']
            ]
            
            addr_parts = [region['area1']['name'], region['area2']['name'], region['area3']['name']]
            base_addr = " ".join([p for p in addr_parts if p]).strip()
            land_num = f"{main_no}-{sub_no}" if sub_no and sub_no != '0' else main_no
            detail_address = f"{base_addr} {land_num}"

        return {
            "status": "OK",
            "address": detail_address,  # 🆕 이제 "삼선동5가 343-1"이 나옵니다!
            "pnu_code": pnu_base,
            "bun": main_no.zfill(4),
            "ji": main_no.zfill(4) if sub_no else "0000"
        }