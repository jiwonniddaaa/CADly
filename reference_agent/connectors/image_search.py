import requests
from reference_agent.core.config import settings

# Vision 등에서 나온 긴 영어 검색어 추출 후 짧게 줄여 SerpAPI에서 0건 검색 방지
_DEFAULT_MAX_WORDS = 10 
_RETRY_WORD_LIMITS = (10, 7, 5)


def shorten_search_query(query: str, max_words: int = _DEFAULT_MAX_WORDS) -> str:
    words = query.split()
    if len(words) <= max_words:
        return query.strip()
    return " ".join(words[:max_words]).strip()


def _refine_query(query: str) -> str:
    return f"{query} (site:archdaily.com OR site:pinterest.com)"


def _fetch_images(refined_query: str, limit: int) -> list:
    url = "https://serpapi.com/search"
    params = {
        "engine": "google_images",
        "q": refined_query,
        "tbm": "isch",
        "api_key": settings.SERPAPI_API_KEY,
        "num": limit,
    }

    response = requests.get(url, params=params, timeout=10)

    if response.status_code != 200:
        print(f"SerpApi Error: {response.status_code} - {response.text}")
        return []

    images_results = response.json().get("images_results", [])

    parsed_results = []
    for item in images_results[:limit]:
        parsed_results.append({
            "title": item.get("title", "Untitled Image"),
            "imageUrl": item.get("original", ""),
            "sourceUrl": item.get("link", ""),
            "thumbnail": item.get("thumbnail", ""),
        })

    return parsed_results


def search_reference_images(query: str, limit: int = 10) -> list:
    """
    SerpApi를 사용하여 ArchDaily와 Pinterest 내에서만 이미지 검색을 수행합니다.
    결과가 없으면 검색어를 단계적으로 줄여 재시도합니다.
    """
    query = (query or "").strip()
    if not query:
        return []

    word_count = len(query.split())
    limits_to_try: list[int] = []
    # 10단어를 초과하는 경우에는 원본 검색어를 스킵하고, 10, 7, 5단어 순으로 검색어 줄여서 검색
    if word_count <= _DEFAULT_MAX_WORDS:
        limits_to_try.append(word_count)
    for max_words in _RETRY_WORD_LIMITS:
        if max_words < word_count:
            limits_to_try.append(max_words)

    seen: set[str] = set()
    try:
        for max_words in limits_to_try:
            candidate = shorten_search_query(query, max_words=max_words)
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)

            results = _fetch_images(_refine_query(candidate), limit=limit)
            if results:
                return results
    except Exception as e:
        print(f"SerpApi Connection Error: {e}")
        return []

    return []