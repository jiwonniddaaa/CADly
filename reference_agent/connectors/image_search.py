import requests
from reference_agent.core.config import settings

def search_reference_images(query: str, limit: int = 10) -> list:
    """
    SerpApi를 사용하여 ArchDaily와 Pinterest 내에서만 이미지 검색을 수행합니다.
    """
    url = "https://serpapi.com/search"
    
    # 검색어 뒤에 강제로 사이트 제한 연산자 추가
    refined_query = f"{query} site:archdaily.com OR site:pinterest.com"
    
    params = {
        "engine": "google_images",
        "q": refined_query,
        "tbm": "isch",
        "api_key": settings.SERPAPI_API_KEY,
        "num": limit
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code != 200:
            print(f"SerpApi Error: {response.status_code} - {response.text}")
            return []
            
        data = response.json()
        images_results = data.get("images_results", [])
        
        parsed_results = []
        for item in images_results[:limit]:
            # 프론트엔드에서 사용하기 쉽게 URL 구조를 파싱합니다.
            parsed_results.append({
                "title": item.get("title", "Untitled Image"),
                "imageUrl": item.get("original", ""),   # 고화질 원본 이미지 URL
                "sourceUrl": item.get("link", ""),      # 출처 웹페이지 링크
                "thumbnail": item.get("thumbnail", "")  # 썸네일 이미지 URL
            })
            
        return parsed_results

    except Exception as e:
        print(f"SerpApi Connection Error: {e}")
        return []