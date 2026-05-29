import axios from 'axios';

// FastAPI 백엔드 기본 URL 설정
const apiClient = axios.create({
  baseURL: 'http://localhost:8000/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

export const cadlyApi = {
  // 🚨 채팅 메시지 전송 (백엔드 ChatRequest 스키마 명세에 100% 일치하도록 수정)
  sendMessage: async (agentType, message, projectId) => {
    // 1. 백엔드 라우터 엔드포인트는 /chat 이며, 바디(body) 데이터에 필요한 값을 모두 실어 보냅니다.
    const response = await apiClient.post('/chat', {
      message: message,
      agent_type: agentType,     // 👈 백엔드가 필요로 하는 agent_type 주입
      session_id: projectId      // 👈 백엔드 스키마 명칭인 session_id로 매핑하여 매칭 성공!
    });
    
    // 백엔드는 { success: true, agent_type: ..., message: ..., image_urls: [...] } 를 반환합니다.
    return response.data;
  },

  // CAD 생성 트리거 (이전 가이드라인에 맞춰 responseType을 'blob'으로 지정하는 구조를 미리 대기시킵니다)
  generateCad: async (projectId, specs) => {
    const response = await apiClient.post(`/generate/${projectId}`, specs, {
      // responseType: 'blob'       // 👈 파일 바이너리(바이트 스트림) 다운로드를 위한 필수 옵션!
                                    // 이었으나 JSON을 받으므로 해당 옵션을 삭제
    });
    return response.data;
  },

  // 생성된 자산 다운로드 URL 가져오기
  getAssets: async (projectId) => {
    const response = await apiClient.get(`/projects/${projectId}/assets`);
    return response.data;
  }
};