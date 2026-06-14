import requests
from reference_agent.core.config import settings

def search_archdaily(query: str, num: int = 5) -> list:
    """
    Google Custom Search API를 사용하여 ArchDaily 이미지를 검색합니다.
    """
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": settings.GOOGLE_API_KEY,
        "cx": settings.ARCHDAILY_CX,
        "q": query, # 사용자의 자연어 질문 혹은 정제된 키워드 
        "searchType": "image", # 이미지 결과 요청 필수 파라미터 
        "num": num
    }
    
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        items = data.get("items", [])
        
        # 프론트엔드에서 활용하기 좋게 필요한 정보(link, title, contextLink)만 추출 [cite: 83, 87]
        results = []
        for item in items:
            results.append({
                "source": "archdaily",
                "link": item.get("link"), 
                "title": item.get("title"),
                "contextLink": item.get("image", {}).get("contextLink") 
            })
        return results
    else:
        print(f"ArchDaily Search Error: {response.status_code} - {response.text}")
        return []