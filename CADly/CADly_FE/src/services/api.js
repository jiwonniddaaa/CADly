import axios from 'axios';

const apiClient = axios.create({
  baseURL: 'http://localhost:8000/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

export const cadlyApi = {
  // 채팅 메시지 전송 (기존)
  sendMessage: async (message, projectId) => {
    const response = await apiClient.post('/chat/', {
      message,
      session_id: projectId
    });
    return response.data;
  },

  // 3D 파일 생성 요청 추가 (반드시 responseType: 'blob' 지정!)
  generate3DModel: async (projectId, format) => {
    const response = await apiClient.post('/generate/3d', {
      project_id: projectId,
      format: format
    }, {
      responseType: 'blob' // 텍스트가 아닌 실제 파일 스트림으로 받음
    });
    return response.data;
  }
};