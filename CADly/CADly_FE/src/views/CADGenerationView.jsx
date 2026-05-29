import React, { useState } from 'react';
import {
  Download, FileText, Image as ImageIcon, FileCode,
  ArrowLeft, RotateCcw, Loader2
} from 'lucide-react';
import { cadlyApi } from '../services/api'; // api 연동

const CADGenerationView = ({ onNavigateBack }) => {
  const [generationStatus, setGenerationStatus] = useState('idle'); // 'idle' | 'generating' | 'completed'
  const [generatedData, setGeneratedData] = useState(null); // 백엔드에서 받은 도면 데이터 저장

  // [기능 1] 백엔드에 도면 생성 요청
  const handleGenerate = async () => {
    // 이미 완료된 상태라면 다운로드 함수 실행 후 리턴
    if (generationStatus === 'completed') {
      downloadAssets();
      return;
    }

    try {
      setGenerationStatus('generating');
      
      // 실제 백엔드 API 호출 (project_id 및 specs 전달)
      const response = await cadlyApi.generateCad('proj_123', { specs: 'Urban Cabin' });
      
      if (response.success) {
        setGeneratedData(response); // svg_content, dxf_content 등 상태에 저장
        setGenerationStatus('completed');
      } else {
        throw new Error('Generation failed on server');
      }
    } catch (error) {
      console.error(error);
      alert('CAD generation failed. Please try again.');
      setGenerationStatus('idle');
    }
  };

  // [기능 2] 다운로드 버튼 클릭 시 파일 저장 처리
  const downloadAssets = () => {
    if (!generatedData) return;

    // 1. SVG 파일 다운로드
    const svgBlob = new Blob([generatedData.svg_content], { type: 'image/svg+xml' });
    const svgUrl = URL.createObjectURL(svgBlob);
    triggerDownload(svgUrl, `${generatedData.filename}.svg`);

    // 2. DXF 파일 다운로드 (Base64 디코딩)
    // 팁: 여러 파일을 동시에 다운로드하면 브라우저가 차단할 수 있으므로 약간의 딜레이를 줍니다.
    setTimeout(() => {
      const dxfBlob = base64ToBlob(generatedData.dxf_content, 'application/dxf');
      const dxfUrl = URL.createObjectURL(dxfBlob);
      triggerDownload(dxfUrl, `${generatedData.filename}.dxf`);
    }, 500);
  };

  // 다운로드 트리거 헬퍼 함수
  const triggerDownload = (url, filename) => {
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url); // 메모리 누수 방지
  };

  // Base64 -> Blob 변환 헬퍼 함수
  const base64ToBlob = (base64, mimeType) => {
    const byteCharacters = atob(base64);
    const byteNumbers = new Array(byteCharacters.length);
    for (let i = 0; i < byteCharacters.length; i++) {
      byteNumbers[i] = byteCharacters.charCodeAt(i);
    }
    const byteArray = new Uint8Array(byteNumbers);
    return new Blob([byteArray], { type: mimeType });
  };

  return (
    <div className="flex h-full flex-col bg-[#0a192f]">
      {/* Top Navigation Bar */}
      <header className="h-[72px] border-b border-blue-900/40 flex items-center px-8 bg-white justify-between w-full">
        <div className="flex gap-6 font-display font-semibold text-secondary">
          <button onClick={onNavigateBack} className="hover:text-primary transition-colors text-secondary flex items-center gap-1">
            <ArrowLeft size={16}/> Site / Reference Agent
          </button>
          <span className="text-outline">|</span>
          <button className="text-primary font-bold">Generation</button>
        </div>
      </header>

      {/* Main Body Grid */}
      <div className="flex-1 flex overflow-hidden">
        {/* CAD Viewer Canvas */}
        <div className="flex-1 flex flex-col relative bg-[#071120]">
          <div className="absolute inset-0 opacity-10" style={{ backgroundImage: 'linear-gradient(#3b82f6 1px, transparent 1px), linear-gradient(90deg, #3b82f6 1px, transparent 1px)', backgroundSize: '32px 32px' }} />
          
          <div className="absolute top-6 left-6 flex bg-white rounded-soft shadow-blueprint border border-outline p-1 z-10">
            <button className="p-2 hover:bg-surface rounded-soft text-secondary"><i className="fas fa-mouse-pointer"></i></button>
            <button className="p-2 hover:bg-surface rounded-soft text-secondary"><i className="fas fa-hand-paper"></i></button>
          </div>

          <div className="flex-1 flex items-center justify-center p-12 z-0">
            <div className="w-full max-w-4xl flex justify-center">

              {generationStatus === 'idle' && (
                <div className="border border-blue-500/30 p-8 bg-[#0a192f] shadow-2xl rounded-container w-full max-w-2xl text-center text-blue-400 font-mono text-sm border-dashed">
                  <div className="py-20 border border-blue-500/20">
                    READY TO GENERATE
                    <p className="text-xs text-blue-500/60 mt-2">CLICK GENERATE TO CREATE CAD OUTPUT</p>
                  </div>
                </div>
              )}

              {generationStatus === 'generating' && (
                <div className="border border-blue-500/30 p-8 bg-[#0a192f] shadow-2xl rounded-container w-full max-w-2xl text-center text-blue-400 font-mono text-sm border-dashed">
                  <div className="py-20 border border-blue-500/20 flex flex-col items-center">
                    <Loader2 size={40} className="animate-spin mb-6 text-blue-400" />
                    GENERATING CAD OUTPUT...
                    <p className="text-xs text-blue-500/60 mt-2">PROCESSING FLOOR PLAN AND STRUCTURE DATA</p>
                  </div>
                </div>
              )}

              {/* 🚨 생성 완료: 캔버스에 SVG를 렌더링합니다! */}
              {generationStatus === 'completed' && generatedData && (
                <div className="border border-blue-500/30 bg-[#0a192f] shadow-2xl w-full flex justify-center items-center p-4">
                  {/* dangerouslySetInnerHTML을 사용해 텍스트 형태의 SVG를 실제 그래픽으로 변환 */}
                  <div 
                    className="w-full h-full flex justify-center items-center [&>svg]:w-full [&>svg]:h-auto"
                    dangerouslySetInnerHTML={{ __html: generatedData.svg_content }} 
                  />
                </div>                    
              )}

            </div>
          </div>
        </div>

        {/* Right Asset Sidebar */}
        <aside className="w-[400px] bg-white border-l border-outline flex flex-col justify-between h-full">
          <div className="p-6 overflow-y-auto space-y-8 flex-1">
            
            {generationStatus === 'completed' && generatedData && (
            <div>
              <h3 className="font-display text-sm text-secondary uppercase mb-4">Generated Assets</h3>
              <div className="space-y-3">
                <div className="flex items-center gap-4 p-4 border border-outline rounded-soft bg-white">
                  <FileCode size={20} className="text-secondary"/> 
                  <span className="text-sm font-medium">{generatedData.filename}.dxf</span>
                </div>
                <div className="flex items-center gap-4 p-4 border border-outline rounded-soft bg-white">
                  <ImageIcon size={20} className="text-secondary"/> 
                  <span className="text-sm font-medium">{generatedData.filename}.svg</span>
                </div>
              </div>
            </div>
            )}

            <div className="bg-surface p-5 rounded-container border border-outline border-dashed">
              <h3 className="font-mono text-xs text-secondary mb-4">GENERATION SPECS</h3>
              <div className="grid grid-cols-2 gap-4">
                <div><p className="font-mono text-[10px] text-secondary">TOTAL AREA</p><p className="font-display font-bold text-primary text-base">28.04 m²</p></div>
                <div><p className="font-mono text-[10px] text-secondary">STRUCTURE</p><p className="text-sm font-semibold">Steel Frame</p></div>
                <div className="col-span-2"><p className="font-mono text-[10px] text-secondary">WALL TYPE</p><p className="text-sm font-semibold">Insulated Wood Finish</p></div>
              </div>
            </div>

            <button 
              onClick={onNavigateBack}
              className="w-full py-3 border border-outline rounded-soft font-display font-medium text-sm text-secondary flex items-center justify-center gap-2 hover:bg-surface transition-colors"
            >
              <RotateCcw size={16}/>
              View Revision History
            </button>
          </div>

          <div className="p-6 border-t border-outline bg-white">
            <button
              onClick={handleGenerate}
              disabled={generationStatus === 'generating'}
              className="w-full bg-primary text-white py-4 rounded-soft font-display font-semibold flex justify-center items-center gap-2 hover:bg-[#00355f] transition-colors disabled:opacity-70"
            >
              {generationStatus === 'idle' && <>Generate CAD-like Output</>}
              {generationStatus === 'generating' && <><Loader2 size={18} className="animate-spin"/> Generating...</>}
              {generationStatus === 'completed' && <><Download size={20}/> Download All CAD Assets</>}
            </button>
          </div>
        </aside>
      </div>
    </div>
  );
};

export default CADGenerationView;