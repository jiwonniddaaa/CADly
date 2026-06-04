# site_agent/site_agent.py
import json
from openai import AsyncOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_anthropic import ChatAnthropic
# 현재 내 패키지 폴더 안의 config 모듈에서 가져오도록 명시
from site_agent.config import LLMConfig 

class SiteAgent:
    def __init__(self, analyzer):
        self.analyzer = analyzer
        config = LLMConfig()
        config.validate()
        self.llm = ChatAnthropic(
            model=config.model,
            api_key=config.api_key,
            temperature=0.0  # 파싱 및 정형 데이터 추출의 정확도를 위해 0으로 설정
        )
        self.model = config.model

    async def get_search_params(self, user_input: str):
        """사용자 요구사항의 자연어 컨텍스트를 파싱하여 정형화된 JSON 파라미터로 변환 (Case A & B 통합)"""
        system_prompt = """
        너는 건축 부지 탐색 에이전트야. 사용자의 입력 문장을 분석하여 반드시 아래 Key를 가진 JSON 객체로만 리턴해.
        - intent: 사용자가 특정 주소/건물명을 직접 콕 집어 말하면 'query' (Case A), "~일대에 추천해줘", "~한 땅 찾아줘" 처럼 지역 추천이나 조건을 말하면 'search' (Case B)
        - sigungu_cd: 5자리 행정구역 시군구 코드 (예: 종로구 -> 11110, 성북구 -> 11290, 강남구 -> 11680)
        - theme: 사용자가 요구하는 부지의 성격이나 주변 환경에 따라 '상권', '자연', '문화' 중 가장 적절한 것 하나를 매칭, 없거나 애매하면 null
        - pnu: 알 수 있는 경우만 10자리 법정동코드 문자열, 없으면 null
        - bun: 지번의 본번 4자리 (예: 59-45의 경우 '0059'), 없으면 null
        - ji: 지번의 부번 4자리 (예: 59-45의 경우 '0045'), 없으면 null
        """
        response = await self.llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_input)
        ])
        
        return response.content
    
    # 채민 - response 생성 로직 추가 (프롬프트 수정 필요)
    async def make_message (
        self,
        user_input: str,
        raw_result: dict,
    ):
        prompt = f"""
        사용자 요청:
        {user_input}

        분석 결과:
        {json.dumps(raw_result, ensure_ascii=False, indent=2)}

        규칙:
        - 반드시 분석 결과에 있는 위치 정보를 가장 먼저 말한다.
        - 위치 정보가 없으면 "현재 분석 결과에는 주소/좌표 정보가 포함되어 있지 않습니다."라고 먼저 말한다.
        - 위치 정보 없이 적합하다고 단정하지 않는다.
        - 제공된 분석 결과에 없는 주소, 지명, 좌표는 절대 추측하지 않는다.
        - 주용도, 용도지역, 면적 정보는 그 다음에 간결하게 설명한다.
        - 3~5문장으로 답한다.
        """

        response = await self.llm.ainvoke([
            SystemMessage(content="너는 건축 부지 추천 AI다. 존댓말로 자연스럽게 한국어로 응답해줘."),
            HumanMessage(content=prompt)
        ])

        return response.content

    
    async def run(self, user_input: str) -> dict:
        """[오케스트레이터 인터페이스] 요구된 4대 면적 데이터만 엄격하게 한정하여 리턴"""
        params_raw = await self.get_search_params(user_input)
        text = params_raw.strip()
        if text.startswith("```"):
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                text = text[start:end + 1]
                
        p = json.loads(text)
        
        if p.get('intent') == "search":
            # [Case B] 자연어 조건 검색 파이프라인 가동
            sigungu_cd = p.get('sigungu_cd')
            theme = p.get('theme')
            if not sigungu_cd: # 기본값 "11290" 채우지 말고 사용자에게 되물어보기
                return {"status": "error", "message": "정확한 지역(시군구)을 파악하지 못했습니다. 구 명칭을 명확히 말씀해주세요."}
            raw_result = await self.analyzer.discover_from_dataset(sigungu_cd, theme, user_input)
        else:
            # [Case A] 특정 주소 다이렉트 쿼리 프로파일링 가동
            # 🌟 [Case A] 특정 주소 다이렉트 쿼리 프로파일링 가동 (수정 완료)
            pnu = p.get('pnu')
            bun = p.get('bun')
            ji = p.get('ji')
            
            # 1. 번지수(bun) 정보가 아예 없다면 가짜 데이터를 주입하지 말고 방어합니다.
            if not bun:
                return {
                    "status": "error", 
                    "message": "분석을 위해 정확한 지번이나 주소 정보가 필요합니다. '역삼동 747'과 같이 구체적인 주소나 번지수를 포함하여 다시 질문해 주세요."
                }
            
            # 부번(ji)은 없을 수도 있으므로 없는 경우 안전하게 "0000" 처리
            ji = ji if ji else "0000"
            pnu = pnu if pnu else "1111010100"
            raw_result = await self.analyzer.run_full_analysis(pnu, bun, ji, user_input)
            
        if not raw_result or raw_result.get("status") != "success":
            return {"status": "error", "message": "데이터 분석 및 추천 프로세스 실패"}

        # 백엔드 마트(SQLite / CSV 청크) 분석 원본 팩 추출
        diff_out = raw_result["diffusion_output"]
        
        # 💡 [정형 스펙 최적화 완성] 불필요한 메타데이터 전면 배제 및 4대 면적 격리 패킹
        refined_output = {
            "building_area_m2": diff_out.get("building_area_m2", 0.0), # 바닥(건축)면적
            "floor_area_m2": diff_out.get("floor_area_m2", 0.0),       # 층(연)면적
            "common_area_m2": diff_out.get("common_area_m2", 0.0),     # 공용면적
            "private_area_m2": diff_out.get("private_area_m2", 0.0)    # 전용면적
        }

        # 채민 - response 생성
        message = await self.make_message(
            user_input=user_input,
            raw_result=raw_result,
        )

        # 채민 - 최종 리턴값에 메시지와 면적 데이터, 원본 분석 결과 모두 포함
        return {
            "status": "success",
            "message": message,
            "diffusion_output": refined_output,
            "raw_site_output": raw_result
        }