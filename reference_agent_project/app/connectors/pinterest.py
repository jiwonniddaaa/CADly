import requests
from app.core.config import settings

def search_pinterest(query: str, num: int = 5) -> list:
    """
    Google Custom Search API를 사용하여 Pinterest 이미지를 검색합니다.
    """
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": settings.GOOGLE_API_KEY,
        "cx": settings.PINTEREST_CX,
        "q": query,
        "searchType": "image",
        "num": num
    }
    
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        items = data.get("items", [])
        
        results = []
        for item in items:
            results.append({
                "source": "pinterest",
                "link": item.get("link"),
                "title": item.get("title"),
                "contextLink": item.get("image", {}).get("contextLink")
            })
        return results
    else:
        print(f"Pinterest Search Error: {response.status_code} - {response.text}")
        return []