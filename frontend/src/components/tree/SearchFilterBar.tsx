import React from 'react';
import { Filter, Search, X } from 'lucide-react';

interface SearchFilterBarProps {
  searchTerm: string;
  onSearchChange: (value: string) => void;
  pathFilter: string;
  onPathFilterChange: (value: string) => void;
  selectedNodeType: string;
  onNodeTypeSelect: (type: string) => void;
}

export const SearchFilterBar: React.FC<SearchFilterBarProps> = ({
  searchTerm,
  onSearchChange,
  pathFilter,
  onPathFilterChange,
  selectedNodeType,
  onNodeTypeSelect,
}) => {
  const nodeTypes = [
    { key: '', label: 'Tất cả' },
    { key: 'CHAPTER', label: 'Chương' },
    { key: 'ARTICLE', label: 'Điều' },
    { key: 'CLAUSE', label: 'Khoản' },
    { key: 'POINT', label: 'Điểm' },
  ];

  return (
    <div className="flex flex-wrap items-center gap-2.5 rounded-lg border border-slate-800 bg-slate-900/90 p-2.5 shadow">
      {/* Search Input */}
      <div className="relative flex-1 min-w-[200px]">
        <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-400" />
        <input
          type="text"
          value={searchTerm}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Tìm kiếm nội dung nguyên văn / từ khóa..."
          className="w-full rounded-md border border-slate-700 bg-slate-800 py-1.5 pl-8 pr-8 text-xs text-slate-100 placeholder-slate-400 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
        {searchTerm && (
          <button
            onClick={() => onSearchChange('')}
            className="absolute right-2.5 top-2 text-slate-400 hover:text-white"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* Path Filter Input */}
      <div className="relative min-w-[160px]">
        <Filter className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-400" />
        <input
          type="text"
          value={pathFilter}
          onChange={(e) => onPathFilterChange(e.target.value)}
          placeholder="LTree path (*.a_5.*)"
          className="w-full rounded-md border border-slate-700 bg-slate-800 py-1.5 pl-8 pr-8 text-xs font-mono text-slate-100 placeholder-slate-400 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
        {pathFilter && (
          <button
            onClick={() => onPathFilterChange('')}
            className="absolute right-2.5 top-2 text-slate-400 hover:text-white"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* Node Type Chips */}
      <div className="flex items-center gap-1">
        {nodeTypes.map((t) => (
          <button
            key={t.key}
            onClick={() => onNodeTypeSelect(t.key)}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${
              selectedNodeType === t.key
                ? 'bg-brand-600 text-white shadow-sm'
                : 'bg-slate-800 text-slate-400 hover:bg-slate-700 hover:text-slate-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
    </div>
  );
};
