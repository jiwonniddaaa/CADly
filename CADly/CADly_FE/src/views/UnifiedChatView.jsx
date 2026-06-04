import React, { useState, useEffect } from 'react';
import { Send, Paperclip, ExternalLink } from 'lucide-react';
import { cadlyApi } from '../services/api';

const UnifiedChatView = ({ onNavigateToGeneration, currentView, setCadSvgContent, projectId }) => {
  const [inputMessage, setInputMessage] = useState('');
  const [messages, setMessages] = useState([]);

  useEffect(() => {
    setMessages([
      { 
        sender: 'agent', 
        text: "안녕하세요! 대지 분석이나 건축 기획에 대해 필요한 부분을 말씀해 주세요. 조사가 완료되면 설계 생성을 진행할 수 있습니다.",
        imageUrls: [] 
      }
    ]);
  }, [projectId]);

  const handleSendMessage = async () => {
    if (!inputMessage.trim()) return;
    const newMsg = { sender: 'user', text: inputMessage };
    
    setMessages(prev => [...prev, newMsg]);
    setInputMessage('');

    try {
      // 백엔드로 메시지 전송
      const response = await cadlyApi.sendMessage(newMsg.text, projectId);

      // 도면 생성 여부와 상관없이 무조건 에이전트의 메시지를 먼저 채팅 기록에 저장
      const agentMsg = {
        sender: 'agent',
        text: response.response,
        imageUrls: response.image_urls || []
      };
      setMessages(prev => [...prev, agentMsg]);

      // AI가 도면 데이터(Raw SVG String)를 함께 반환한 경우
      if (response.cad_svg_content) {
        setCadSvgContent(response.cad_svg_content);
        // 도면이 생성되었으므로 프리뷰를 볼 수 있게 Generation 레이어로 자동 이동!
        onNavigateToGeneration(); 
      }
    } catch (error) {
      console.error("Failed to send message", error);
    }
  };

  return (
    <div className="w-full h-full flex flex-col justify-between bg-white">
      
      {/* 상단 헤더: 하단에 연한 구분선(border-b) 및 높이 최적화 */}
      <header className="w-full h-16 flex items-center justify-between px-10 bg-white border-b border-slate-100 z-10 shrink-0">
        
        {/* 좌측 타이틀 */}
        <div className="font-mono text-xs font-bold tracking-wider text-[#002d5a]">
          Site Investigation & Planning
        </div>

        {/* 우측 Generation 이동 버튼 */}
        <button 
          onClick={onNavigateToGeneration}
          className="flex items-center gap-1.5 font-mono text-xs font-bold text-[#002d5a] hover:opacity-70 transition-opacity bg-transparent outline-none"
        >
          Generation
          <ExternalLink size={14} strokeWidth={2.5} />
        </button>
        
      </header>

      {/* 대화 히스토리 영역 */}
      <div className="flex-1 overflow-y-auto p-10 flex flex-col gap-6 bg-white">
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[70%] p-5 rounded-2xl shadow-sm border ${
              msg.sender === 'user' 
                ? 'bg-[#002d5a] border-[#002d5a] text-white rounded-br-sm' 
                : 'bg-white border-slate-200 text-slate-800 rounded-bl-sm'
            }`}>
              <p className="whitespace-pre-line text-[14px] leading-relaxed">{msg.text}</p>

              {msg.imageUrls && msg.imageUrls.length > 0 && (
                <div className="grid grid-cols-2 gap-2 mt-4">
                  {msg.imageUrls.map((url, i) => (
                    <img key={i} src={url} alt={`Ref ${i+1}`} className="w-full h-32 object-cover rounded-lg border border-slate-200" />
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* 하단 입력 폼 벨트 */}
      <div className="px-10 pb-8 pt-2 bg-white">
        <div className="flex items-center gap-3 bg-slate-50 border border-slate-200 rounded-xl px-5 py-3.5 shadow-sm transition-all focus-within:border-[#002d5a] focus-within:ring-1 focus-within:ring-[#002d5a]">
          <Paperclip size={20} className="text-slate-400 hover:text-[#002d5a] cursor-pointer transition-colors" />
          <input
            type="text"
            className="flex-1 bg-transparent outline-none text-sm text-slate-800 placeholder-slate-400"
            placeholder="Ask about site restrictions or request a massing plan..."
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
          />
          <button onClick={handleSendMessage} className="p-2.5 bg-[#002d5a] text-white rounded-lg hover:bg-[#001f3f] transition-colors shadow-md">
            <Send size={18} />
          </button>
        </div>
      </div>
    </div>
  );
};

export default UnifiedChatView;