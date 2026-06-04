import React, { useState } from 'react';
import MainLayout from './components/layout/MainLayout';
import UnifiedChatView from './views/UnifiedChatView';
import CADGenerationView from './views/CADGenerationView';

function App() {
  const [currentView, setCurrentView] = useState('chat');
  const [cadSvgContent, setCadSvgContent] = useState(null);
  const [projectId, setProjectId] = useState('proj_123');

  const handleNewProject = () => {
    const newProjectId = `proj_${Date.now()}`;
    setProjectId(newProjectId);
    setCadSvgContent(null);
    setCurrentView('chat');
    console.log(`New Project Started: ${newProjectId}`);
  };

  return (
    // 반드시 onNewProject={handleNewProject} 프롭을 넣어주어야 작동
    <MainLayout onNewProject={handleNewProject}>
      {currentView === 'chat' ? (
        <UnifiedChatView 
          currentView={currentView}
          onNavigateToGeneration={() => setCurrentView('generation')}
          setCadSvgContent={setCadSvgContent} 
          projectId={projectId}
        />
      ) : (
        <CADGenerationView 
          currentView={currentView}
          onNavigateToChat={() => setCurrentView('chat')}
          cadSvgContent={cadSvgContent} 
          projectId={projectId}
        />
      )}
    </MainLayout>
  );
}

export default App;