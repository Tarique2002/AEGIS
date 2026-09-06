import React from 'react';
import { Navbar } from './Navbar';
import { Sidebar, type NavTab } from './Sidebar';
import { ConnectModal } from '../common/ConnectModal';

interface ShellProps {
  currentTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  children: React.ReactNode;
}

export const Shell: React.FC<ShellProps> = ({
  currentTab,
  onSelectTab,
  children,
}) => {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#0b0f19] text-gray-100">
      {/* Global Connection / Auth Modal */}
      <ConnectModal />

      {/* Sidebar Navigation */}
      <Sidebar currentTab={currentTab} onSelectTab={onSelectTab} />

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        <Navbar />
        <main className="flex-1 overflow-y-auto p-6 md:p-8">
          <div className="max-w-7xl mx-auto">{children}</div>
        </main>
      </div>
    </div>
  );
};
