// CADly/CADly_FE/src/views/UnifiedChatView.jsx
import React, { useState, useRef } from 'react';
import { Send, Paperclip } from 'lucide-react';
import { cadlyApi } from '../services/api';

const UnifiedChatView = ({ onNavigateToGeneration, currentView, setCadSvgContent, setDesignOutput, projectId, messages, setMessages }) => {
  const [inputMessage, setInputMessage] = useState('');
  const [attachedImage, setAttachedImage] = useState(null);
  const [isSending, setIsSending] = useState(false);
  const fileInputRef = useRef(null);

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      const imageUrl = URL.createObjectURL(file);
      setAttachedImage({ file, url: imageUrl });
    }
    e.target.value = '';
  };

  const handleSendMessage = async () => {
    if (isSending) return;
    if (!inputMessage.trim() && !attachedImage) return;

    const newMsg = { 
      sender: 'user', 
      text: inputMessage,
      userImageUrl: attachedImage ? attachedImage.url : null
    };

    setMessages(prev => [...prev, newMsg]);

    const textToSend = inputMessage;
    const imageToSend = attachedImage?.file;

    setInputMessage('');
    setAttachedImage(null);
    setIsSending(true);

    try {
      const response = await cadlyApi.sendMessage(textToSend, projectId, imageToSend);

      const agentMsg = {
        sender: 'agent',
        text: response.response,
        imageUrls: response.image_urls || [],
        route: response.route || '',
        agentType: response.agent_type || 'agent',
        routeLabel: response.route_label || '에이전트',
        activeOrchestrator: response.active_orchestrator || 'planning',
        debug: response.debug || null,
      };
      setMessages(prev => [...prev, agentMsg]);

      if (response.svg_path || response.dxf_path || response.design_status) {
        setDesignOutput({
          svgPath: response.svg_path || null,
          dxfPath: response.dxf_path || null,
          status: response.design_status || null,
        });
      }

      if (response.cad_svg_content) {
        setCadSvgContent(response.cad_svg_content);
        onNavigateToGeneration();
      }
    } catch (error) {
      console.error("Failed to send message", error);
    } finally {
      setIsSending(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.nativeEvent.isComposing) return;
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <div className="flex flex-col h-full bg-white">
      {/* 상단 플랫 헤더 바 */}
      <div className="flex items-center justify-between px-8 py-4 border-b border-gray-100 bg-white shrink-0">
        <div className="flex items-center gap-6">
          <button className={`font-sans text-xs font-bold bg-transparent outline-none transition-all ${currentView === 'chat' ? 'text-[#002d5a]' : 'text-slate-400 hover:text-slate-600'}`}>
            Site Investigation & Planning
          </button>
        </div>
        <button onClick={onNavigateToGeneration} className={`flex items-center gap-2 font-sans text-xs font-bold bg-transparent outline-none transition-all ${currentView === 'generation' ? 'text-[#002d5a]' : 'text-slate-400 hover:text-slate-600'}`}>
          Generation <span className="text-[10px]">↗</span>
        </button>
      </div>

      {/* 대화 히스토리 영역 */}
      <div className="flex-1 overflow-y-auto p-8 space-y-6">
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[75%] p-4 rounded-xl border ${msg.sender === 'user' ? 'bg-[#002d5a] border-[#001f3f] text-white' : 'bg-gray-50 border-gray-200 text-slate-800'}`}>
              {msg.sender === 'agent' && msg.routeLabel && (
                <div className="flex flex-wrap items-center gap-2 mb-2">
                  <span className="inline-flex items-center rounded-full bg-[#002d5a]/10 px-2 py-0.5 text-[10px] font-semibold text-[#002d5a]">
                    {msg.routeLabel}
                  </span>
                  {msg.activeOrchestrator === 'design' && (
                    <span className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-800">
                      설계 단계
                    </span>
                  )}
                  {msg.debug && (
                    <span className="text-[10px] font-mono text-slate-400">
                      {msg.debug.route || msg.route}
                    </span>
                  )}
                </div>
              )}

              {msg.userImageUrl && (
                <img src={msg.userImageUrl} alt="User Upload" className="w-full h-40 object-cover rounded-lg mb-3 border border-blue-400/30" />
              )}
              
              {msg.text && (
                <div className="whitespace-pre-wrap text-sm leading-relaxed">{msg.text}</div>
              )}

              {msg.imageUrls && msg.imageUrls.length > 0 && (
                <div className="mt-4 grid grid-cols-2 gap-2">
                  {msg.imageUrls.map((url, i) => (
                    <img key={i} src={url} alt={`Reference ${i+1}`} className="w-full h-32 object-cover rounded-lg border border-gray-300" />
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* 하단 입력 폼 벨트 */}
      <div className="p-6 bg-white border-t border-gray-100 shrink-0">
        {attachedImage && (
          <div className="mb-3 relative inline-block">
            <img src={attachedImage.url} alt="Attached Preview" className="h-20 w-20 object-cover rounded-lg border border-gray-200 shadow-sm" />
            <button onClick={() => setAttachedImage(null)} className="absolute -top-2 -right-2 bg-slate-700 text-white rounded-full w-5 h-5 flex items-center justify-center text-[10px] hover:bg-slate-900 transition-colors shadow-md">✕</button>
          </div>
        )}
        <div className="flex items-center bg-gray-50 border border-gray-200 rounded-xl px-4 py-3 gap-3 focus-within:border-blue-300 focus-within:ring-2 focus-within:ring-blue-100 transition-all">
          <input type="file" accept="image/*" className="hidden" ref={fileInputRef} onChange={handleFileChange} />
          <button onClick={() => fileInputRef.current.click()} className="outline-none transition-colors">
            <Paperclip className={`w-5 h-5 ${attachedImage ? 'text-[#002d5a]' : 'text-slate-400 hover:text-slate-600'}`} />
          </button>
          <input
            type="text"
            className="flex-1 bg-transparent outline-none text-sm text-slate-700 placeholder-slate-400"
            placeholder={attachedImage ? "메시지 없이 이미지만내도 됩니다 (Enter 또는 전송)" : "Ask about site restrictions or request a massing plan..."}
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <button 
            type="button"
            onClick={handleSendMessage}
            disabled={isSending}
            className="p-2 bg-[#002d5a] text-white rounded-lg hover:bg-[#001f3f] transition-colors outline-none shadow-sm flex-shrink-0 disabled:opacity-50"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
};

export default UnifiedChatView;