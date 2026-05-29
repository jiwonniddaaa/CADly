import React, { useState } from 'react';
import { Send, Paperclip } from 'lucide-react';
import { cadlyApi } from '../services/api';

const UnifiedChatView = ({ onNavigateToGeneration }) => {
  const [activeAgent, setActiveAgent] = useState('site'); // 'site' | 'reference'
  const [inputMessage, setInputMessage] = useState('');
  
  // 에이전트별 독립된 메시지 관리를 위한 상태
  const [siteMessages, setSiteMessages] = useState([]);
  const [refMessages, setRefMessages] = useState([]);

  const currentMessages = activeAgent === 'site' ? siteMessages : refMessages;

  const handleSendMessage = async () => {
    if (!inputMessage.trim()) return;
    
    const newMsg = { sender: 'user', text: inputMessage };
    
    if (activeAgent === 'site') {
      setSiteMessages(prev => [...prev, newMsg]);
    } else {
      setRefMessages(prev => [...prev, newMsg]);
    }
    
    setInputMessage('');

    try {
      const response = await cadlyApi.sendMessage(activeAgent, newMsg.text, 'proj_123');
      // 백엔드에서 추출해 준 image_urls 배열도 상태에 함께 저장합니다.
      const agentMsg = { 
        sender: 'agent', 
        text: response.message,
        imageUrls: response.image_urls || [] // 🚨 추가된 부분
      };
      
      if (activeAgent === 'site') {
        setSiteMessages(prev => [...prev, agentMsg]);
      } else {
        setRefMessages(prev => [...prev, agentMsg]);
      }
    } catch (error) {
      console.error("Failed to send message", error);
    }
  };

  return (
    <div className="flex flex-col h-full bg-surface">
      {/* TopAppBar */}
      <header className="h-[72px] border-b border-outline flex items-center px-8 bg-white justify-between">
        <div className="flex gap-6 font-display font-semibold text-secondary">
          <button 
            onClick={() => setActiveAgent('site')} 
            className={`px-4 py-2 rounded-md transition-all ${
                        activeAgent === 'site'
                          ? 'bg-primary text-white'
                          : 'text-secondary hover:bg-gray-100 hover:text-primary'
                      }`}
          >
            Site Agent
          </button>
          <button 
            onClick={() => setActiveAgent('reference')} 
            className={`px-4 py-2 rounded-md transition-all ${
                        activeAgent === 'reference'
                          ? 'bg-primary text-white'
                          : 'text-secondary hover:bg-gray-100 hover:text-primary'
                      }`}
          >
            Reference Agent
          </button>
          <span className="text-outline">|</span>
          <button 
            onClick={onNavigateToGeneration} 
            className="hover:text-primary transition-colors text-secondary"
          >
            Generation
          </button>
        </div>
      </header>

      {/* Main Content Grid */}
      <div className="flex-1 flex overflow-hidden">
        {/* Chat Area */}
        <div className="flex-1 flex flex-col p-8 overflow-y-auto">
          
          {/* 🚨 에이전트 선택에 따라 컨텐츠 조건부 렌더링 */}
          {activeAgent === 'site' ? (
            <div>
              <span className="font-mono text-xs text-primary font-bold tracking-widest uppercase">Site Investigation</span>
              <h2 className="font-display text-3xl font-bold mt-2">대지 분석 (Site Investigation)</h2>
              <div className="mt-4 flex justify-end">
                <div className="p-4 bg-primary text-white rounded-soft max-w-max text-sm">
                서울 성북구 안암동 5가 73-2번지 대지 조사해줘.
                </div>
              </div>
              <div className="mt-4 p-6 bg-white border border-outline rounded-container shadow-blueprint space-y-2">
                <h4 className="font-bold text-lg"># 대지 분석 결과 요약</h4>
                <p className="text-sm text-secondary">• 용도지역: 제1종 근린생활시설 / 제3종 일반주거지역</p>
                <p className="text-sm text-secondary">• 대지면적: 28.04 m²</p>
                <p className="text-sm text-secondary">• 건폐율(BCR): 53.55% / 용적률(FAR): 214.21%</p>
              </div>
            </div>
          ) : (
            <div>
              <span className="font-mono text-xs text-primary font-bold tracking-widest uppercase">Planning</span>
              <h2 className="font-display text-3xl font-bold mt-2">건축 기획 (Architectural Planning)</h2>
              <div className="mt-4 flex justify-end">
                <div className="mt-4 p-4 bg-primary text-white rounded-soft max-w-max text-sm">
                도심 속 오두막 느낌으로 건축 기획하고 싶어.
                </div>
              </div>
              <div className="mt-4 p-6 bg-white border border-outline rounded-container shadow-blueprint space-y-2">
                <h4 className="font-bold text-lg"># Urban Cabin Rustic City Dwelling 컨셉 브리핑</h4>
                <p className="text-sm text-secondary leading-relaxed">
                  수집된 이미지들은 도시 환경 내에서 자연 소재(목재, 석재)와 현대적 미니멀리즘을 결합하는 방식을 보여주며, 좁은 공간을 수직 활용하는 전략을 제시합니다.
                </p>
              </div>
            </div>
          )}

          {/* Dynamic Message History */}
          <div className="flex-1 space-y-4 mt-6">
            {currentMessages.map((msg, idx) => (
              <div key={idx} className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[80%] p-4 border border-outline rounded-container ${msg.sender === 'user' ? 'bg-primary text-white' : 'bg-white shadow-blueprint'}`}>
                  {/* 텍스트 렌더링 (줄바꿈이 적용되도록 CSS 추가) */}
                  <div className="whitespace-pre-wrap">{msg.text}</div>
                  {/* 🚨 이미지 렌더링: imageUrls 배열이 존재하면 Grid로 뿌려줍니다 */}
                  {msg.imageUrls && msg.imageUrls.length > 0 && (
                    <div className="mt-4 grid grid-cols-2 gap-4">
                      {msg.imageUrls.map((url, i) => (
                        <img 
                          key={i} 
                          src={url} 
                          alt={`Reference ${i + 1}`} 
                          className="w-full h-48 object-cover rounded-md border border-outline"
                          loading="lazy"
                        />
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Input Area */}
          <div className="mt-auto bg-white border border-outline rounded-soft p-2 flex items-center focus-within:border-primary focus-within:ring-2 focus-within:ring-blue-100 transition-all">
            <button className="p-2 text-secondary hover:text-primary"><Paperclip size={20}/></button>
            <input 
              type="text" 
              className="flex-1 outline-none px-4 font-body"
              placeholder={`Ask for ".DXF" or ".SVG" to trigger CAD Schematic Generation`}
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
            />
            <button onClick={handleSendMessage} className="bg-primary text-white p-3 rounded-soft hover:bg-[#00355f] transition-colors">
              <Send size={18}/>
            </button>
          </div>
        </div>

        {/* Planning Workflow 사이드바 - 제외 */} 
        {/*<aside className="w-[360px] bg-white border-l border-outline p-6 overflow-y-auto">
          <h3 className="font-display font-bold text-lg mb-6">Planning Workflow</h3>
          <div className="space-y-4">
            <WorkflowNode status={activeAgent === 'site' ? "VALIDATED" : "VALIDATED"} title="Site Investigation" details={["Anam-dong 5-ga 73-2", "Land Metrics Analyzed"]} />
            <WorkflowNode status={activeAgent === 'reference' ? "PROCESSING" : "PENDING"} title="Reference Curation" details={["Curating high res architectural references based on context."]} />
            <WorkflowNode status="PENDING" title="CAD Schematic Generation" details={["Final output will include DXF, SVG, and high fidelity plan views."]} />
          </div>

          <button 
            onClick={onNavigateToGeneration}
            className="w-full mt-8 bg-primary text-white py-4 rounded-soft font-display font-semibold flex justify-between px-6 hover:bg-[#00355f] transition-colors"
          >
            Export for CAD
            <span>&gt;</span>
          </button>
        </aside>*/}
      </div>
    </div>
  );
};

const WorkflowNode = ({ status, title, details }) => {
  const isValidated = status === 'VALIDATED';
  const isProcessing = status === 'PROCESSING';
  return (
    <div className={`p-5 border border-outline rounded-container ${isValidated || isProcessing ? 'bg-white' : 'bg-surface opacity-60'}`}>
      <span className={`font-mono text-xs px-2 py-1 rounded-sm font-bold ${isValidated ? 'bg-validated text-green-800' : isProcessing ? 'bg-processing text-orange-800' : 'bg-surface-dim text-secondary'}`}>
        {status}
      </span>
      <h4 className="font-display font-semibold mt-3 mb-2">{title}</h4>
      <ul className="text-sm font-body text-secondary space-y-1 list-disc pl-4">
        {details.map((desc, i) => <li key={i}>{desc}</li>)}
      </ul>
    </div>
  );
};

export default UnifiedChatView;