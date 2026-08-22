import React from 'react';
import { RefreshCw, Radio, CheckCircle2, ShieldCheck, Database } from 'lucide-react';

export default function Header({ currentTab, projects, selectedProject, setSelectedProject, wsConnected, onRefresh, loading }) {
  const titles = {
    overview: 'System Overview & Telemetry',
    queues: 'Queue Management & Concurrency Limits',
    jobs: 'Job Ingestion & Live Lifecycle',
    dlq: 'Dead Letter Queue (DLQ) & Redrive',
    schedules: 'Recurring Cron Dispatcher',
    workers: 'Distributed Worker Nodes Fleet',
  };

  return (
    <header className="h-16 px-8 border-b border-slate-800/80 bg-[#080E1A]/80 backdrop-blur-md flex items-center justify-between sticky top-0 z-20">
      <div className="flex items-center gap-3">
        <span className="text-xs font-semibold text-sky-400 uppercase tracking-widest">Codity</span>
        <span className="text-slate-600">/</span>
        <h1 className="text-sm font-semibold text-slate-100">{titles[currentTab] || 'Dashboard'}</h1>
      </div>

      <div className="flex items-center gap-4">
        {/* Project Selector */}
        {projects && projects.length > 0 && (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-900/80 border border-slate-800 text-xs text-slate-300">
            <Database className="w-3.5 h-3.5 text-sky-400" />
            <select
              value={selectedProject?.id || ''}
              onChange={(e) => {
                const p = projects.find((proj) => proj.id === e.target.value);
                if (p) setSelectedProject(p);
              }}
              className="bg-transparent text-slate-200 outline-none cursor-pointer text-xs"
            >
              {projects.map((p) => (
                <option key={p.id} value={p.id} className="bg-slate-900 text-slate-200">
                  {p.name}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Live Stream Beacon */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-900/90 border border-slate-800 text-xs">
          <span className="relative flex h-2 w-2">
            {wsConnected && (
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            )}
            <span
              className={`relative inline-flex rounded-full h-2 w-2 ${
                wsConnected ? 'bg-emerald-500' : 'bg-amber-500'
              }`}
            ></span>
          </span>
          <span className={`text-[11px] font-medium ${wsConnected ? 'text-emerald-400' : 'text-amber-400'}`}>
            {wsConnected ? 'WebSocket Live Stream' : 'Polling Sync'}
          </span>
        </div>

        {/* Manual Refresh */}
        <button
          onClick={onRefresh}
          disabled={loading}
          className="p-2 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-slate-300 hover:text-white transition-all active:scale-95 disabled:opacity-50"
          title="Refresh Data"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-sky-400' : ''}`} />
        </button>
      </div>
    </header>
  );
}
