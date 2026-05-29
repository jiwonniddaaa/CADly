import React, { useState } from 'react';
import MainLayout from './components/layout/MainLayout';
import UnifiedChatView from './views/UnifiedChatView';
import CADGenerationView from './views/CADGenerationView';

function App() {
  // 'planning' (채팅 뷰)와 'generation' (CAD 뷰) 사이의 화면 상태
  const [currentLayer, setCurrentLayer] = useState('planning');

  return (
    <MainLayout>
      {currentLayer === 'planning' ? (
        // CAD 화면으로 가기 위한 함수 전달
        <UnifiedChatView onNavigateToGeneration={() => setCurrentLayer('generation')} />
      ) : (
        // 다시 채팅 화면으로 돌아오기 위한 함수 전달 (onNavigateBack)
        <CADGenerationView onNavigateBack={() => setCurrentLayer('planning')} />
      )}
    </MainLayout>
  );
}

export default App;