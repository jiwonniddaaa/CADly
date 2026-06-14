import React from 'react';
import { PlusCircle, History, Edit3, Settings, HelpCircle } from 'lucide-react';

const MainLayout = ({ children, onNewProject }) => {
  return (
    <div className="flex w-screen h-screen bg-white overflow-hidden text-slate-800 font-sans">
      
      {/* ── 좌측 글로벌 고정 사이드바 ── */}
      <aside className="w-64 h-full bg-white border-r border-slate-200 flex flex-col justify-between p-5 shrink-0">
        
        <div className="flex flex-col gap-6">
          {/* 로고 영역: font-serif를 적용하여 기획안과 동일한 서체 느낌 구현 */}
          <div className="flex flex-col px-2 mb-2">
            <h1 className="text-3xl font-serif font-bold text-[#002d5a]">CADly</h1>
            <p className="text-[10px] tracking-widest text-slate-400 font-mono mt-1">AI ARCHITECTURAL AGENT</p>
          </div>

          <button
            onClick={onNewProject}
            className="w-full bg-[#002d5a] hover:bg-[#001f3f] text-white py-3 px-4 rounded-lg font-medium flex items-center justify-center gap-2 transition-all shadow-md active:scale-[0.98]"
          >
            <PlusCircle size={18} />
            <span className="text-sm tracking-wide">New Project</span>
          </button>

          <nav className="flex flex-col gap-1 mt-2">
            <button className="w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-slate-500 hover:bg-slate-50 hover:text-[#002d5a] transition-colors text-sm">
              <History size={18} />
              <span>Recent Works</span>
            </button>
            
            <button className="w-full flex items-center gap-3 px-3 py-2.5 rounded-md bg-[#e2ecf8] text-[#002d5a] font-semibold transition-colors text-sm">
              <Edit3 size={18} />
              <span>Works</span>
            </button>

            <button className="w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-slate-500 hover:bg-slate-50 hover:text-[#002d5a] transition-colors text-sm">
              <Settings size={18} />
              {/* Settings -> Setting 으로 수정 */}
              <span>Setting</span>
            </button>
          </nav>
        </div>

        <div className="border-t border-slate-100 pt-4">
          <button className="w-full flex items-center gap-3 px-3 py-2 text-slate-500 hover:text-[#002d5a] transition-colors text-sm">
            <HelpCircle size={18} />
            <span>Help Center</span>
          </button>
        </div>

      </aside>

      {/* ── 우측 메인 콘텐츠 영역 ── */}
      <main className="flex-1 h-full relative overflow-hidden flex flex-col bg-white">
        {children}
      </main>

    </div>
  );
};

export default MainLayout;