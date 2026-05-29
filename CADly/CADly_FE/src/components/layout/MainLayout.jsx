import React from 'react';
import { LayoutDashboard, History, PenTool, FolderDown, Users, Settings, HelpCircle } from 'lucide-react';

const MainLayout = ({ children }) => {
  return (
    <div className="flex h-screen bg-surface font-body text-[#191c1e] antialiased">
      {/* SideNavBar (Fixed 320px width as per DESIGN.md) */}
      <aside className="w-[320px] bg-white border-r border-outline flex flex-col justify-between">
        <div>
          <div className="p-6">
            <h1 className="font-display font-bold text-2xl text-primary tracking-tight">CADly</h1>
            <p className="font-mono text-xs text-secondary mt-1">AI Architectural Agent</p>
          </div>
          
          <nav className="mt-4 flex flex-col gap-2 px-4">
            <NavItem icon={<LayoutDashboard size={20}/>} label="New Project" />
            <NavItem icon={<History size={20}/>} label="Recent Work" />
            {/*<NavItem icon={<PenTool size={20}/>} label="Drafting History" />
            <NavItem icon={<FolderDown size={20}/>} label="CAD Assets"/>
            <NavItem icon={<Users size={20}/>} label="Team Library" />*/}
          </nav>
        </div>

        <div className="p-6">
          {/*<button className="w-full bg-primary text-white rounded-soft py-3 font-display font-semibold hover:bg-[#00355f] transition-colors mb-6">
            Upgrade to Pro
          </button>*/}
          <nav className="flex flex-col gap-3 text-sm">
            <a href="#" className="flex items-center gap-3 text-secondary hover:text-primary"><Settings size={18}/> Settings</a>
            <a href="#" className="flex items-center gap-3 text-secondary hover:text-primary"><HelpCircle size={18}/> Support</a>
          </nav>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col h-full overflow-hidden">
        {children}
      </main>
    </div>
  );
};

const NavItem = ({ icon, label, active }) => (
  <a href="#" className={`flex items-center gap-3 px-4 py-3 rounded-soft transition-colors ${active ? 'bg-blue-50 text-primary font-semibold' : 'text-secondary hover:bg-surface'}`}>
    {icon}
    <span>{label}</span>
  </a>
);

export default MainLayout;