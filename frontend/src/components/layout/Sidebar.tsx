import React from 'react';
import {
  Activity,
  Terminal,
  Network,
  Database,
  GraduationCap,
  ShieldCheck,
  Layers,
} from 'lucide-react';

export type NavTab =
  | 'mission-control'
  | 'execution-console'
  | 'orchestration'
  | 'memory'
  | 'governance'
  | 'security';

interface SidebarProps {
  currentTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
}

interface NavItem {
  id: NavTab;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: string;
  badgeColor?: string;
  description: string;
}

const NAV_ITEMS: NavItem[] = [
  {
    id: 'mission-control',
    label: 'Mission Control',
    icon: Activity,
    description: 'Health, Telemetry & Dispatch',
  },
  {
    id: 'execution-console',
    label: 'Execution Console',
    icon: Terminal,
    description: 'Task Logs & Event Stream',
  },
  {
    id: 'orchestration',
    label: 'Multi-Agent',
    icon: Network,
    description: 'DAG Planner & Workers',
  },
  {
    id: 'memory',
    label: 'Memory Explorer',
    icon: Database,
    description: 'Episodic & Procedural DB',
  },
  {
    id: 'governance',
    label: 'Learning & Evolution',
    icon: GraduationCap,
    badge: 'Phase 12',
    badgeColor: 'bg-cyan-950 text-cyan-400 border border-cyan-700/60',
    description: 'Procedures, Gates & Rollback',
  },
  {
    id: 'security',
    label: 'Security & Audit',
    icon: ShieldCheck,
    description: 'RBAC Policy & Merkle Log',
  },
];

export const Sidebar: React.FC<SidebarProps> = ({ currentTab, onSelectTab }) => {
  return (
    <aside className="w-64 shrink-0 border-r border-gray-800 bg-[#090d16] p-4 flex flex-col justify-between">
      <div className="space-y-6">
        <div className="px-2">
          <p className="text-[10px] font-bold uppercase tracking-wider text-gray-500">
            Control Center
          </p>
        </div>

        <nav className="space-y-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = currentTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onSelectTab(item.id)}
                className={`w-full text-left flex items-start space-x-3 rounded-xl px-3 py-2.5 transition-all ${
                  isActive
                    ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 shadow-[0_0_15px_rgba(6,182,212,0.1)]'
                    : 'text-gray-400 hover:bg-gray-800/60 hover:text-gray-200 border border-transparent'
                }`}
              >
                <Icon
                  className={`mt-0.5 h-5 w-5 shrink-0 ${
                    isActive ? 'text-cyan-400' : 'text-gray-500'
                  }`}
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span
                      className={`text-sm font-medium leading-none ${
                        isActive ? 'text-white' : 'text-gray-300'
                      }`}
                    >
                      {item.label}
                    </span>
                    {item.badge && (
                      <span
                        className={`text-[9px] font-semibold px-1.5 py-0.2 rounded-full leading-tight uppercase ${item.badgeColor}`}
                      >
                        {item.badge}
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-[11px] text-gray-500 truncate leading-none">
                    {item.description}
                  </p>
                </div>
              </button>
            );
          })}
        </nav>
      </div>

      {/* Production Infrastructure Stamp */}
      <div className="rounded-xl border border-gray-800/80 bg-gray-950/60 p-3.5 space-y-2">
        <div className="flex items-center space-x-2 text-[11px] text-gray-400 font-medium">
          <Layers className="w-3.5 h-3.5 text-cyan-400" />
          <span>AEGIS Runtime Engine</span>
        </div>
        <div className="space-y-1 text-[11px] font-mono text-gray-400">
          <div className="flex justify-between">
            <span>Target:</span>
            <span className="text-cyan-400">Render Cloud</span>
          </div>
          <div className="flex justify-between">
            <span>Auth:</span>
            <span className="text-gray-300">Bearer JWT</span>
          </div>
          <div className="flex justify-between">
            <span>Mode:</span>
            <span className="text-emerald-400">Production Strict</span>
          </div>
        </div>
      </div>
    </aside>
  );
};
