import React, { useState } from 'react';
import { AppHeader, TabId } from './components/layout/AppHeader';
import { LlmAnswerPanel } from './components/answer/LlmAnswerPanel';
import { DryRunSearchSimulator } from './components/search/DryRunSearchSimulator';
import { I18nProvider } from './i18n/I18nContext';

const AppContent: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabId>('answer');

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-slate-950 text-slate-100">
      <AppHeader activeTab={activeTab} onTabChange={setActiveTab} />
      <main className="min-h-0 flex-1">
        {activeTab === 'answer' ? <LlmAnswerPanel /> : <DryRunSearchSimulator />}
      </main>
    </div>
  );
};

export const App: React.FC = () => (
  <I18nProvider>
    <AppContent />
  </I18nProvider>
);

export default App;
