import { useState } from 'react';
import { AuthProvider } from './context/AuthContext';
import { Shell } from './components/layout/Shell';
import type { NavTab } from './components/layout/Sidebar';
import { MissionControl } from './pages/MissionControl';
import { ExecutionConsole } from './pages/ExecutionConsole';
import { OrchestrationViewer } from './pages/OrchestrationViewer';
import { MemoryExplorer } from './pages/MemoryExplorer';
import { LearningGovernance } from './pages/LearningGovernance';
import { SecurityAudit } from './pages/SecurityAudit';

export function AppContent() {
  const [currentTab, setCurrentTab] = useState<NavTab>('mission-control');
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);

  const handleNavigateToTask = (taskId: string) => {
    setSelectedTaskId(taskId);
    setCurrentTab('execution-console');
  };

  return (
    <Shell currentTab={currentTab} onSelectTab={setCurrentTab}>
      {currentTab === 'mission-control' && (
        <MissionControl onNavigateToTask={handleNavigateToTask} />
      )}
      {currentTab === 'execution-console' && (
        <ExecutionConsole initialTaskId={selectedTaskId} />
      )}
      {currentTab === 'orchestration' && <OrchestrationViewer />}
      {currentTab === 'memory' && <MemoryExplorer />}
      {currentTab === 'governance' && <LearningGovernance />}
      {currentTab === 'security' && <SecurityAudit />}
    </Shell>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}
