import React, { useState } from 'react';
import { ArrowLeft, Menu, FileText, Loader2, ArrowUpRight } from 'lucide-react';
import { cadlyApi } from '../services/api';

const CADGenerationView = ({ onNavigateToChat, cadSvgContent, designOutput, projectId }) => {
  // 1. 우측 제어 사이드바 토글 상태
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  
  // 2. 3D 모델링 플로우 상태: 'initial' -> 'format_selection' -> 'generated'
  const [modelingStep, setModelingStep] = useState('initial');
  const [isGenerating, setIsGenerating] = useState(false);
  const [generatedFile, setGeneratedFile] = useState(null);
  const [cadExportTarget, setCadExportTarget] = useState(null);
  const [cadExportMessage, setCadExportMessage] = useState('');

  const triggerBlobDownload = (blob, filename) => {
    const downloadUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(downloadUrl);
  };

  const downloadDxfFallback = async () => {
    const blobData = await cadlyApi.downloadDxf(projectId, designOutput?.dxfPath);
    const filename = designOutput?.dxfPath
      ? designOutput.dxfPath.split('/').pop()
      : 'floorplan.dxf';
    triggerBlobDownload(blobData, filename);
    setCadExportMessage('CAD 앱 열기에 실패해 DXF 파일을 다운로드했습니다.');
  };

  const handleCadExport = async (targetCad) => {
    if (!designOutput?.dxfPath) {
      alert('DXF 파일이 없습니다. 도면 생성을 먼저 완료해 주세요.');
      return;
    }

    setCadExportTarget(targetCad);
    setCadExportMessage('');
    try {
      const result = await cadlyApi.importToCad(projectId, targetCad, designOutput.dxfPath);
      if (result.ok) {
        setCadExportMessage(result.message || 'CAD 앱에서 DXF를 열었습니다.');
        return;
      }

      await downloadDxfFallback();
    } catch (error) {
      console.error('CAD export failed:', error);
      try {
        await downloadDxfFallback();
      } catch (downloadError) {
        console.error('DXF download fallback failed:', downloadError);
        alert('CAD 연동 및 DXF 다운로드에 모두 실패했습니다.');
      }
    } finally {
      setCadExportTarget(null);
    }
  };

  // 3D 파일 생성용 FastAPI 연동 함수
  const handleGenerate3D = async (format) => {
    setIsGenerating(true);
    try {
      const blobData = await cadlyApi.generate3DModel(projectId, format);
      setGeneratedFile({
        blob: blobData,
        name: `preview_in_3d${format}`,
        format: format,
        size: (blobData.size / 1024 / 1024).toFixed(1) + ' MB'
      });
      setModelingStep('generated');
    } catch (error) {
      console.error("3D 모델 생성 실패:", error);
      alert("파일 생성에 실패했습니다.");
    } finally {
      setIsGenerating(false);
    }
  };

  // 3D 파일 로컬 다운로드 (추후 포맷별 후처리·메타데이터 확장 지점)
  const handleDownload3D = () => {
    if (!generatedFile) return;

    const downloadUrl = URL.createObjectURL(generatedFile.blob);
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.download = generatedFile.name;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(downloadUrl);
  };

  return (
    <div className="flex h-full w-full bg-white font-sans relative overflow-hidden">
      
      {/* ================= 메인 캔버스 워크스페이스 영역 ================= */}
      <div className="flex-1 flex flex-col relative h-full transition-all duration-300">
        
        {/* ✨ 상단 헤더: UnifiedChatView와 동일한 높이와 패딩(px-8 py-4) 적용 */}
        <header className="flex items-center justify-between px-8 py-4 border-b border-gray-100 bg-white shrink-0 z-10 w-full">
          
          {/* 좌측 CHAT 이동 버튼 */}
          <button 
            onClick={onNavigateToChat}
            className="flex items-center gap-1.5 font-mono text-xs font-bold text-[#002d5a] hover:opacity-70 transition-opacity bg-transparent outline-none"
          >
            <ArrowLeft size={14} strokeWidth={2.5} />
            CHAT
          </button>
          
          {/* 우측 햄버거 메뉴 버튼 */}
          <button 
            onClick={() => setIsSidebarOpen(!isSidebarOpen)} 
            className="text-[#002d5a] hover:opacity-70 transition-opacity bg-transparent outline-none"
          >
            <Menu size={18} strokeWidth={2.5} />
          </button>
          
        </header>

        {/* 메인 도면 영역 (헤더 아래 캔버스 파트는 어두운 네이비색 유지) */}
        <div className="flex-1 relative flex items-center justify-center overflow-hidden bg-[#0b132b]">
          
          {/* 좌측 상단 상태 뱃지 (상단 화이트 헤더 영역 확보에 맞춰 top-6 안전 배치) */}
          <div className="absolute top-6 left-6 z-20 border border-[#4a5568] text-[#81e6d9] px-4 py-1.5 text-[11px] font-mono tracking-widest rounded bg-[#0b132b]/80 flex items-center gap-2">
            ACTIVE VIEW: 2D FLOORPLAN_B1 <span className="w-1.5 h-1.5 rounded-full bg-[#fbd38d]"></span>
          </div>

          {/* 모눈종이 격자선 배경 */}
          <div className="absolute inset-0 bg-[linear-gradient(to_right,#1e293b_1px,transparent_1px),linear-gradient(to_bottom,#1e293b_1px,transparent_1px)] bg-[size:4rem_4rem] opacity-20"></div>
          
          {cadSvgContent ? (
            <div dangerouslySetInnerHTML={{ __html: cadSvgContent }} className="relative z-10 w-full h-full p-8 flex items-center justify-center" />
          ) : (
             <div className="relative z-10 w-[600px] h-[400px] border border-dashed border-[#4a5568] flex items-center justify-center text-[#a0aec0]">
               [도면 미리보기 영역]
             </div>
          )}

          {/* 우측 하단 Open Export Panel 플로팅 버튼 */}
          {!isSidebarOpen && (
            <div className="absolute bottom-6 right-6 z-20">
              <button 
                onClick={() => setIsSidebarOpen(true)}
                className="bg-[#002d5a] hover:bg-[#001f3f] text-white px-5 py-3 rounded-lg flex items-center gap-2 text-xs font-bold tracking-wider shadow-lg border border-[#1c2541] transition-all duration-200 transform hover:scale-105"
              >
                <ArrowUpRight size={15} />
                Open Export Panel
              </button>
            </div>
          )}
          
        </div>
      </div>

      {/* ================= 우측 하얀색 제어 사이드바 영역 ================= */}
      {isSidebarOpen && (
        <div className="w-[380px] bg-white text-slate-800 h-full border-l border-slate-200 overflow-y-auto shadow-2xl z-30 shrink-0 animate-in fade-in slide-in-from-right duration-200 relative">
          <button onClick={() => setIsSidebarOpen(false)} className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 text-xs">✕</button>

          <div className="p-8 flex flex-col gap-10 mt-4">
            <section>
              <h3 className="text-lg font-bold text-[#002d5a] mb-4">Files</h3>
              {designOutput?.dxfPath || designOutput?.svgPath ? (
                <div className="space-y-2">
                  {designOutput.dxfPath && (
                    <div className="border border-slate-200 bg-slate-50 rounded-lg p-4 flex items-start gap-4">
                      <FileText className="text-slate-400 shrink-0" size={24} />
                      <div className="min-w-0">
                        <p className="text-[13px] font-bold text-[#002d5a]">DXF</p>
                        <p className="text-[10px] text-slate-500 mt-0.5 break-all font-mono">{designOutput.dxfPath}</p>
                      </div>
                    </div>
                  )}
                  {designOutput.svgPath && (
                    <div className="border border-slate-200 bg-slate-50 rounded-lg p-4 flex items-start gap-4">
                      <FileText className="text-slate-400 shrink-0" size={24} />
                      <div className="min-w-0">
                        <p className="text-[13px] font-bold text-[#002d5a]">SVG</p>
                        <p className="text-[10px] text-slate-500 mt-0.5 break-all font-mono">{designOutput.svgPath}</p>
                      </div>
                    </div>
                  )}
                  {designOutput.status && (
                    <p className="text-[10px] text-slate-500 font-mono">status: {designOutput.status}</p>
                  )}
                </div>
              ) : (
                <div className="border border-dashed border-slate-200 bg-slate-50 rounded-lg p-4 text-[12px] text-slate-500">
                  생성된 도면 파일 경로가 아직 없습니다.
                </div>
              )}
            </section>

            <section>
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-bold text-[#002d5a]">Plan Specs</h3>
                <span className="bg-teal-50 text-teal-700 px-2 py-1 text-[10px] font-bold rounded border border-teal-100">VALIDATED</span>
              </div>
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div className="bg-slate-50 p-4 rounded-lg border border-slate-100">
                  <p className="text-[10px] text-slate-500 font-bold mb-1 tracking-wider">TOTAL AREA</p>
                  <p className="text-xl font-bold text-[#002d5a]">1,240 <span className="text-[12px]">m²</span></p>
                </div>
                <div className="bg-slate-50 p-4 rounded-lg border border-slate-100">
                  <p className="text-[10px] text-slate-500 font-bold mb-1 tracking-wider">EFFICIENCY</p>
                  <p className="text-xl font-bold text-[#002d5a]">94.2%</p>
                </div>
              </div>
            </section>

            <section>
              <h3 className="text-lg font-bold text-[#002d5a] mb-4">CAD Export</h3>
              <div className="flex gap-2">
                <button
                  onClick={() => handleCadExport('autocad')}
                  disabled={!designOutput?.dxfPath || !!cadExportTarget}
                  className="flex-1 bg-[#002d5a] text-white py-3 rounded text-xs font-bold tracking-wider hover:bg-[#001f3f] transition-colors shadow-sm disabled:opacity-50 disabled:cursor-not-allowed flex justify-center items-center gap-2"
                >
                  {cadExportTarget === 'autocad' ? <Loader2 className="animate-spin" size={14} /> : null}
                  AUTOCAD
                </button>
                <button
                  onClick={() => handleCadExport('rhino')}
                  disabled={!designOutput?.dxfPath || !!cadExportTarget}
                  className="flex-1 bg-[#002d5a] text-white py-3 rounded text-xs font-bold tracking-wider hover:bg-[#001f3f] transition-colors shadow-sm disabled:opacity-50 disabled:cursor-not-allowed flex justify-center items-center gap-2"
                >
                  {cadExportTarget === 'rhino' ? <Loader2 className="animate-spin" size={14} /> : null}
                  RHINO
                </button>
              </div>
              {cadExportMessage && (
                <p className="mt-3 text-[11px] text-slate-600 leading-relaxed">{cadExportMessage}</p>
              )}
            </section>

            <section>
              <h3 className="text-lg font-bold text-[#002d5a] mb-2">3D Modeling</h3>
              <p className="text-xs text-slate-500 mb-4">Create a Rhino-based 3D model from the generated floor plan.</p>
              
              <button 
                onClick={() => setModelingStep('format_selection')}
                disabled={modelingStep !== 'initial'}
                className="w-full py-3 rounded text-xs font-bold tracking-wider mb-3 transition-colors bg-white border border-slate-300 text-[#002d5a] hover:bg-slate-50 shadow-sm disabled:bg-slate-50 disabled:border-slate-200 disabled:text-slate-400 disabled:cursor-not-allowed disabled:shadow-inner"
              >
                Generate 3D Model
              </button>

              {modelingStep === 'format_selection' && (
                <div className="flex gap-2 animate-in fade-in slide-in-from-top-2 duration-150">
                  <button onClick={() => handleGenerate3D('.3dm')} disabled={isGenerating} className="flex-1 bg-[#002d5a] text-white py-2 rounded text-[10px] font-bold hover:bg-[#001f3f] disabled:opacity-50 flex justify-center shadow-sm">
                    {isGenerating ? <Loader2 className="animate-spin" size={14} /> : '.3DM'}
                  </button>
                  <button onClick={() => handleGenerate3D('.glb')} disabled={isGenerating} className="flex-1 bg-[#002d5a] text-white py-2 rounded text-[10px] font-bold hover:bg-[#001f3f] disabled:opacity-50 flex justify-center shadow-sm">
                    {isGenerating ? <Loader2 className="animate-spin" size={14} /> : '.glb'}
                  </button>
                  <button onClick={() => handleGenerate3D('.dwg')} disabled={isGenerating} className="flex-1 bg-[#002d5a] text-white py-2 rounded text-[10px] font-bold hover:bg-[#001f3f] disabled:opacity-50 flex justify-center shadow-sm">
                    {isGenerating ? <Loader2 className="animate-spin" size={14} /> : '.dwg'}
                  </button>
                </div>
              )}

              {modelingStep === 'generated' && generatedFile && (
                <div className="flex flex-col gap-2 animate-in fade-in duration-200">
                  <div 
                    onClick={handleDownload3D}
                    className="mt-2 border border-slate-200 bg-white shadow-sm rounded-lg p-4 flex items-center gap-4 cursor-pointer hover:border-[#002d5a] hover:bg-slate-50 transition-all"
                  >
                    <FileText className="text-slate-400 shrink-0" size={24} />
                    <div className="overflow-hidden">
                      <p className="text-[13px] font-bold text-[#002d5a] truncate">{generatedFile.name}</p>
                      <p className="text-[10px] text-slate-500 mt-0.5 tracking-wider">CAD INTERCHANGE | {generatedFile.size}</p>
                    </div>
                  </div>
                </div>
              )}
            </section>
          </div>
        </div>
      )}
    </div>
  );
};

export default CADGenerationView;