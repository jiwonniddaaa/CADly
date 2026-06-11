import axios from 'axios';

const apiClient = axios.create({
  baseURL: 'http://localhost:8000/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

export const cadlyApi = {
  // 채팅 메시지 전송 (이미지 파일 첨부 지원)
  sendMessage: async (message, projectId, imageFile = null) => {
    const formData = new FormData();
    const normalizedMessage = (message || '').trim();

    formData.append('session_id', projectId);
    // FastAPI Form(...)는 빈 문자열을 누락으로 처리하므로, 텍스트가 있을 때만 전송
    if (normalizedMessage) {
      formData.append('message', normalizedMessage);
    }

    if (imageFile) {
      formData.append('file', imageFile);
    }

    const response = await apiClient.post('/chat/', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    });
    return response.data;
  },

  // 세션(planning_state) 초기화 — New Project 시 호출
  clearSession: async (projectId) => {
    const response = await apiClient.delete(`/chat/session/${projectId}`);
    return response.data;
  },

  // 3D 파일 생성 요청 (바이너리 수신)
  generate3DModel: async (projectId, format) => {
    const response = await apiClient.post('/generate/3d', {
      project_id: projectId,
      format: format
    }, {
      responseType: 'blob'
    });
    return response.data;
  }
};