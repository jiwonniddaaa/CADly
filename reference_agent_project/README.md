# Reference Agent

- Anthropic Claude 기반 멀티모달 레퍼런스 에이전트.
- ArchDaily에서 크롤링한 이미지와 CSV 태깅 데이터를 기반으로, 사용자 질의에 맞는 레퍼런스 이미지를 검색하여 제공

## Refactoring (20260519)
- **레퍼런스 에이전트가 각각 search node와 concept node를 가지는 구조로 수정**
- **이미지 검색 시 custom search api를 사용하여 특정 웹사이트 (archdaily, pinterest)에서 사용자의 요청에 맞게 이미지 가져옴**
- **다만 custom search api가 최근 구글에서 막고 있다고 하여 SerpApi로 바꿔야 할 필요가 있음**

## 구성
- LLM: Anthropic Claude
- Agent Framework: LangGraph
- Backend: FastAPI
- Vector DB: Qdrant
- Metadata DB: SQLite
- Embeddings: SentenceTransformers + CLIP

## 동작 방식
1. 크롤러가 이미지 수집
2. CSV 파일에 이미지 메타데이터 및 태그 저장
3. CSV를 기반으로 벡터 DB(Qdrant)에 인덱싱
4. 사용자 질의를 받아 관련 레퍼런스 이미지 검색
5. 검색된 이미지를 API로 반환 (이미지는 생성하지 않고, 기존 크롤링 데이터 기반으로)

## 주요 기능
### 3.1 CSV 기반 데이터 적재
- CSV 한 행 = 이미지 1개
- 태그, 스타일, 공간 정보 등을 함께 저장
- 텍스트 + 이미지 임베딩 생성 후 Qdrant에 저장
### 3.2 하이브리드 검색
- Dense (텍스트 의미)
- CLIP (이미지-텍스트 멀티모달)
- Sparse (키워드 매칭)
### 3.3 이미지 반환
- 검색 결과에 image_url 포함 ** (추후 구현 예정)**
- FastAPI static 서버를 통해 실제 이미지 접근 가능

## 폴더 구조
```python
app/ agents/ # Claude 기반 에이전트 
api/ # FastAPI 라우터 
core/ # 설정 
models/ # Pydantic 스키마 
services/ # 핵심 로직 
embedding.py ingestion.py csv_ingestion.py retrieval.py qdrant_store.py metadata_store.py utils/ image_url.py # image_path → image_url 변환 
scripts/ ingest_csv.py init_qdrant_collection.py data/ raw/ # 크롤링 이미지 저장 위치 
sample_references.csv
```


## 실행
```bash
docker compose up -d
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python scripts/init_qdrant_collection.py
uvicorn app.main:app --reload
```
