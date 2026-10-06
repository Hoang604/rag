import React from 'react';
import {
  CheckSquare,
  Columns,
  FolderTree,
  GitBranch,
  MessagesSquare,
  Search,
} from 'lucide-react';

export type TabId =
  | 'studio'
  | 'dualview'
  | 'history'
  | 'checklist'
  | 'search'
  | 'answer';

interface NavigationTabsProps {
  activeTab: TabId;
  onTabChange: (tab: TabId) => void;
  chunksCount: number;
  historyCount: number;
  issuesCount: number;
}

export const NavigationTabs: React.FC<NavigationTabsProps> = ({
  activeTab,
  onTabChange,
  chunksCount,
  historyCount,
  issuesCount,
}) => {
  const tabs = [
    {
      id: 'studio' as TabId,
      label: 'Legal Studio (3-Pane)',
      icon: FolderTree,
      badge: chunksCount > 0 ? `${chunksCount} mục` : undefined,
    },
    {
      id: 'dualview' as TabId,
      label: 'Đối Chiếu Toàn Văn',
      icon: Columns,
    },
    {
      id: 'history' as TabId,
      label: 'Nhật Ký Tác Vụ',
      icon: GitBranch,
      badge: historyCount > 0 ? `${historyCount}` : undefined,
    },
    {
      id: 'checklist' as TabId,
      label: 'Thẩm Định Toàn Vẹn',
      icon: CheckSquare,
      badge: issuesCount > 0 ? `${issuesCount} lỗi` : 'Đạt ✔',
      badgeColor:
        issuesCount > 0
          ? 'bg-rose-950 text-rose-300 border border-rose-800'
          : 'bg-emerald-950 text-emerald-300 border border-emerald-800',
    },
    {
      id: 'search' as TabId,
      label: 'Thử Nghiệm Truy Xuất',
      icon: Search,
    },
    {
      id: 'answer' as TabId,
      label: 'Hỏi Đáp (LLM)',
      icon: MessagesSquare,
    },
  ];

  return (
    <div className="flex border-b border-slate-800 bg-slate-900/60 px-5 backdrop-blur-sm overflow-x-auto">
      <nav className="flex space-x-1 sm:space-x-2">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;

          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => onTabChange(tab.id)}
              className={`group flex items-center gap-2 border-b-2 px-3.5 py-3 text-xs font-semibold transition whitespace-nowrap ${
                isActive
                  ? 'border-brand-500 text-brand-300'
                  : 'border-transparent text-slate-400 hover:border-slate-700 hover:text-slate-200'
              }`}
            >
              <Icon
                className={`h-4 w-4 transition ${
                  isActive
                    ? 'text-brand-400'
                    : 'text-slate-400 group-hover:text-slate-200'
                }`}
              />
              <span>{tab.label}</span>

              {tab.badge && (
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] font-mono font-bold ${
                    tab.badgeColor ||
                    (isActive
                      ? 'bg-brand-950 text-brand-300 border border-brand-800'
                      : 'bg-slate-800 text-slate-400 border border-slate-700')
                  }`}
                >
                  {tab.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>
    </div>
  );
};
