import React, { useState } from 'react';
import {
  CheckCircle,
  FilePlus,
  Layers,
  RefreshCw,
  Scale,
  ShieldAlert,
} from 'lucide-react';
import { StagingDocumentSession, StagingSessionSummary } from '../../types/staging';
import { StatusBadge } from './StatusBadge';

interface HeaderProps {
  sessions: StagingSessionSummary[];
  activeDocCode?: string;
  session: StagingDocumentSession | null;
  onSelectDoc: (docCode: string) => void;
  onRefresh: () => void;
  onOpenPromotionModal: () => void;
  onOpenCreateSessionModal: () => void;
  onQuickValidate: () => void;
  validating?: boolean;
  blockingIssuesCount?: number;
}

export const Header: React.FC<HeaderProps> = ({
  sessions,
  activeDocCode,
  session,
  onSelectDoc,
  onRefresh,
  onOpenPromotionModal,
  onOpenCreateSessionModal,
  onQuickValidate,
  validating = false,
  blockingIssuesCount = 0,
}) => {
  const [isRefreshing, setIsRefreshing] = useState(false);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await onRefresh();
    setTimeout(() => setIsRefreshing(false), 400);
  };

  return (
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 bg-slate-900/95 px-5 py-3 shadow-md">
      {/* Brand & Document Selector */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-brand-600 to-brand-800 text-white shadow-inner">
            <Scale className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold tracking-wide text-slate-100">
                THẨM ĐỊNH PHÁP LÝ GIAO THÔNG
              </span>
              <span className="rounded bg-brand-950 px-1.5 py-0.5 text-[10px] font-mono font-semibold text-brand-400 border border-brand-800/60">
                v1.0
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              Human-in-the-Loop Statutory Ingestion & Reviewer
            </p>
          </div>
        </div>

        <div className="h-6 w-px bg-slate-800 hidden sm:block" />

        {/* Document Selection Dropdown */}
        <div className="flex items-center gap-2">
          <Layers className="h-4 w-4 text-slate-400" />
          <select
            value={activeDocCode || ''}
            onChange={(e) => onSelectDoc(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-800/90 px-3 py-1.5 text-xs md:text-sm font-medium text-slate-100 shadow-sm transition hover:border-slate-600 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          >
            {sessions.length === 0 ? (
              <option value="">Chưa có văn bản trong Staging</option>
            ) : (
              sessions.map((s) => (
                <option key={s.doc_code} value={s.doc_code}>
                  {s.doc_code} — {s.title.substring(0, 38)}
                  {s.title.length > 38 ? '...' : ''} ({s.status})
                </option>
              ))
            )}
          </select>

          <button
            onClick={handleRefresh}
            title="Làm mới danh sách văn bản"
            className="rounded-lg border border-slate-700 bg-slate-800 p-2 text-slate-300 transition hover:bg-slate-700 hover:text-white"
          >
            <RefreshCw
              className={`h-4 w-4 ${isRefreshing ? 'animate-spin text-brand-400' : ''}`}
            />
          </button>
        </div>
      </div>

      {/* Center / Right Metadata & Action Buttons */}
      <div className="flex items-center gap-3">
        {session && <StatusBadge status={session.status} />}

        {/* Quick Validate Button */}
        {session && (
          <button
            onClick={onQuickValidate}
            disabled={validating}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-200 transition hover:bg-slate-700 disabled:opacity-50"
          >
            <CheckCircle
              className={`h-3.5 w-3.5 ${validating ? 'animate-spin text-brand-400' : 'text-slate-400'}`}
            />
            <span>{validating ? 'Đang thẩm định...' : 'Thẩm định'}</span>
          </button>
        )}

        {/* Promote to PostgreSQL Button */}
        {session && (
          <button
            onClick={onOpenPromotionModal}
            disabled={blockingIssuesCount > 0}
            className={`flex items-center gap-2 rounded-lg px-4 py-1.5 text-xs font-semibold shadow transition ${
              blockingIssuesCount > 0
                ? 'cursor-not-allowed border border-rose-800/80 bg-rose-950/40 text-rose-300 opacity-60'
                : 'border border-brand-500 bg-gradient-to-r from-brand-600 to-brand-700 text-white hover:from-brand-500 hover:to-brand-600 shadow-brand-900/30'
            }`}
          >
            {blockingIssuesCount > 0 ? (
              <>
                <ShieldAlert className="h-3.5 w-3.5 text-rose-400" />
                <span>Bị chặn ({blockingIssuesCount} lỗi)</span>
              </>
            ) : (
              <>
                <CheckCircle className="h-3.5 w-3.5 text-white" />
                <span>Phê duyệt & Nhập CSDL</span>
              </>
            )}
          </button>
        )}

        {/* New Session Button */}
        <button
          onClick={onOpenCreateSessionModal}
          className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/90 px-3 py-1.5 text-xs font-medium text-slate-200 transition hover:bg-slate-700 hover:text-white"
        >
          <FilePlus className="h-3.5 w-3.5 text-brand-400" />
          <span>Văn bản mới</span>
        </button>
      </div>
    </header>
  );
};
