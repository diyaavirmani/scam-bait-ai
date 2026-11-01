import React from 'react';
import { LayoutDashboard, MessagesSquare, PhoneCall, ShieldAlert, Network, FolderArchive, Cpu } from 'lucide-react';

export const NAV = [
  { path: '/', label: 'Overview', icon: LayoutDashboard },
  { path: '/chats', label: 'Live Chats', icon: MessagesSquare },
  { path: '/calls', label: 'Calls', icon: PhoneCall },
  { path: '/intel', label: 'Intelligence', icon: ShieldAlert },
  { path: '/networks', label: 'Scammer Networks', icon: Network },
  { path: '/cases', label: 'Cases and Export', icon: FolderArchive },
  { path: '/system', label: 'System Status', icon: Cpu },
];

interface LayoutProps {
  children: React.ReactNode;
  path: string;
  navigate: (path: string) => void;
  connected: boolean;
}

export const Layout = ({ children, path, navigate, connected }: LayoutProps) => (
  <div className="flex h-screen bg-slate-50 overflow-hidden">
    <aside className="w-64 bg-white border-r border-slate-200 flex flex-col z-10 shadow-sm shrink-0">
      <div className="p-6 border-b border-slate-100 flex items-center gap-3">
        <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-white">
          <ShieldAlert size={18} />
        </div>
        <h1 className="font-bold text-slate-800 tracking-tight">ScamBait AI</h1>
      </div>
      <nav className="flex-1 p-4 space-y-1">
        {NAV.map((item) => (
          <button
            key={item.path}
            onClick={() => navigate(item.path)}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-colors ${
              path === item.path ? 'bg-blue-50 text-blue-700' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
            }`}
          >
            <item.icon size={18} />
            {item.label}
          </button>
        ))}
      </nav>
      <div className="p-4 border-t border-slate-100">
        <StatusPill connected={connected} />
      </div>
    </aside>
    <main className="flex-1 overflow-y-auto bg-slate-50 relative">
      <div className="max-w-7xl mx-auto p-8">{children}</div>
    </main>
  </div>
);

export const StatusPill = ({ connected }: { connected: boolean }) => (
  <div className={`px-3 py-1.5 rounded-full text-xs font-semibold border inline-flex items-center gap-2 ${connected ? 'bg-green-50 text-green-700 border-green-200' : 'bg-red-50 text-red-700 border-red-200'}`}>
    <span className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
    {connected ? 'System Online' : 'Offline'}
  </div>
);

export const PageHeader = ({ title, subtitle, connected }: { title: string; subtitle: string; connected: boolean }) => (
  <div className="flex justify-between items-center bg-white p-6 rounded-xl shadow-sm border border-slate-200 mb-6">
    <div>
      <h1 className="text-2xl font-bold text-slate-900 tracking-tight">{title}</h1>
      <p className="text-slate-500 text-sm mt-1">{subtitle}</p>
    </div>
    <StatusPill connected={connected} />
  </div>
);

export const Panel = ({ title, right, children, className = '' }: { title?: string; right?: React.ReactNode; children: React.ReactNode; className?: string }) => (
  <div className={`bg-white rounded-xl shadow-sm border border-slate-200 p-6 ${className}`}>
    {title && (
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-bold text-slate-800">{title}</h3>
        {right}
      </div>
    )}
    {children}
  </div>
);

export const Empty = ({ text = 'Waiting for the first scammer message' }: { text?: string }) => (
  <div className="flex flex-col items-center justify-center py-10 text-slate-400 gap-2">
    <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center">
      <ShieldAlert className="text-slate-300" />
    </div>
    <span className="text-sm font-medium">{text}</span>
  </div>
);
