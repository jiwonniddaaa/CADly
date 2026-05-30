# site_agent/config.py
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

class NaverConfig:
    def __init__(self):
        self.client_id = os.getenv("NAVER_CLIENT_ID")
        self.client_secret = os.getenv("NAVER_CLIENT_SECRET")
        self.base_url = "https://maps.apigw.ntruss.com/map-geocode/v2/geocode"
        self.reverse_base_url = "https://maps.apigw.ntruss.com/map-reversegeocode/v2/gc"

    def get_headers(self):
        return {
            "X-NCP-APIGW-API-KEY-ID": self.client_id,
            "X-NCP-APIGW-API-KEY": self.client_secret
        }
        
class PublicDataConfig:
    def __init__(self):
        self.bld_base_url = "http://apis.data.go.kr/1613000/BldRgstHubService"
        self.bld_service_key = os.getenv("PUBLIC_DATA_SERVICE_KEY")
        
        self.land_base_url = "http://apis.data.go.kr/1613000/arLandUseInfoService"
        self.land_service_key = os.getenv("LAND_USE_SERVICE_KEY")
        
        self.endpoints = {
            "basic_info": "/getBrBasisOulnInfo", 
            "title_info": "/getBrTitleInfo",      
            "floor_info": "/getBrFlrOulnInfo",    
            "jijigu_info": "/getBrJijiguInfo",   
            "land_limit": "/getLurisGeoService" 
        }


class LLMConfig:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = "gpt-4o"

    def validate(self):
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY가 .env 파일에 없습니다. 프로젝트 최상위에 .env 설정을 확인하세요.")