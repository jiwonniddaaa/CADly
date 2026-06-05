import React, { useState, useEffect } from 'react';
import MainLayout from './components/layout/MainLayout';
import UnifiedChatView from './views/UnifiedChatView';
import CADGenerationView from './views/CADGenerationView';
import { cadlyApi } from './services/api';

function App() {
  const [currentView, setCurrentView] = useState('chat');
  const [cadSvgContent, setCadSvgContent] = useState(null);
  const [designOutput, setDesignOutput] = useState({ svgPath: null, dxfPath: null, status: null });
  const [projectId, setProjectId] = useState('proj_123');
  
  // ✨ 핵심 해결: 채팅 메시지 상태를 App으로 끌어올림 (화면을 왔다 갔다 해도 유지됨)
  const [messages, setMessages] = useState([]);

  // 프로젝트(세션)가 변경될 때만 초기 안내 메시지 세팅
  useEffect(() => {
    setMessages([
      {
        sender: 'agent',
        text: "안녕하세요! 대지 분석이나 건축 기획에 대해 필요한 부분을 말씀해 주세요. 조사가 완료되면 설계 생성을 진행할 수 있습니다.",
        imageUrls: []
      }
    ]);
  }, [projectId]);

  // 'New Project' 버튼 클릭 시에만 모든 것을 리셋
  const handleNewProject = async () => {
    const previousProjectId = projectId;
    const newProjectId = `proj_${Date.now()}`;
    setProjectId(newProjectId);
    setCadSvgContent(null);
    setDesignOutput({ svgPath: null, dxfPath: null, status: null });
    setCurrentView('chat');
    try {
      await cadlyApi.clearSession(previousProjectId);
    } catch (error) {
      console.warn('Failed to clear previous session state', error);
    }
  };

  return (
    <MainLayout onNewProject={handleNewProject}>
      {currentView === 'chat' ? (
        <UnifiedChatView
          currentView={currentView}
          onNavigateToGeneration={() => setCurrentView('generation')}
          setCadSvgContent={setCadSvgContent}
          setDesignOutput={setDesignOutput}
          projectId={projectId}
          messages={messages}       // App에서 관리하는 메시지 전달
          setMessages={setMessages} // App에서 관리하는 상태 변경 함수 전달
        />
      ) : (
        <CADGenerationView
          currentView={currentView}
          onNavigateToChat={() => setCurrentView('chat')}
          cadSvgContent={cadSvgContent}
          designOutput={designOutput}
          projectId={projectId}
        />
      )}
    </MainLayout>
  );
}

export default App;