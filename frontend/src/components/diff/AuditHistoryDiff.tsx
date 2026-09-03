import React, { useEffect, useMemo, useState } from 'react';
import {
  FileText,
  Filter,
  GitBranch,
  GitCommit,
  Layers,
  Sparkles,
} from 'lucide-react';
import { api } from '../../services/api';
import { SessionDiffResponse } from '../../types/diff';
import { StagingDocumentSession } from '../../types/staging';
import { InlineDiffViewer } from './InlineDiffViewer';
import { MutationLogList } from './MutationLogList';

interface AuditHistoryDiffProps {
  session: StagingDocumentSession;
}

export const AuditHistoryDiff: React.FC<AuditHistoryDiffProps> = ({ session }) => {
  const [diffData, setDiffData] = useState<SessionDiffResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeStage, setActiveStage] = useState<number>(4);
  const [filterType, setFilterType] = useState<string>('ALL');

  useEffect(() => {
    async function loadDiff() {
      setLoading(true);
      try {
        const res = await api.getSessionDiff(session.doc_code);
        setDiffData(res);
      } catch (err) {
        console.error('Failed to load session diff:', err);
      } finally {
        setLoading(false);
      }
    }
    void loadDiff();
  }, [session.doc_code]);

  const stages = [
    {
      num: 1,
      name: 'Stage 1: AST Parser',
      desc: 'Cấu trúc AST nguyên bản ban đầu',
      icon: Layers,
    },
    {
      num: 2,
      name: 'Stage 2: CPHC Context',
      desc: 'Tổng hợp chuỗi ngữ cảnh cha-con',
      icon: Sparkles,
    },
    {
      num: 3,
      name: 'Stage 3: AI Agent Patches',
      desc: 'Chỉnh sửa & cạnh quan hệ do AI gán',
      icon: GitCommit,
    },
    {
      num: 4,
      name: 'Stage 4: Current Staged State',
      desc: 'Toàn bộ thay đổi thực tế so với bản gốc',
      icon: GitBranch,
    },
  ];

  // Dynamically compute and filter diff entries according to active stage & filter
  const displayedEntries = useMemo(() => {
    if (!diffData) return [];

    let entries = diffData.diff_entries;

    // Filter by stage
    if (activeStage === 1) {
      // Stage 1: Pure AST baseline (no diffs applied yet)
      entries = [];
    } else if (activeStage === 2) {
      // Stage 2: Only contextualized text additions
      entries = entries.filter((e) => e.field_name === 'contextualized_text');
    } else if (activeStage === 3) {
      // Stage 3: Agent patches (metadata and edges)
      entries = entries.filter(
        (e) => e.field_name === 'metadata' || e.change_type === 'ADDED'
      );
    }

    // Filter by change type
    if (filterType !== 'ALL') {
      entries = entries.filter((e) => e.change_type === filterType);
    }

    return entries;
  }, [diffData, activeStage, filterType]);

  return (
    <div className="flex h-full w-full flex-col overflow-y-auto bg-slate-950 p-6">
      {/* 4-Stage Stepper Header */}
      <div className="mb-6 rounded-xl border border-slate-800 bg-slate-900/80 p-5 shadow">
        <h3 className="mb-3 text-sm font-bold uppercase tracking-wider text-slate-200">
          Quy Trình 4 Giai Đoạn Biến Đổi &amp; Kiểm Toán (Audit Trail)
        </h3>
        <p className="mb-4 text-xs text-slate-400">
          Chọn từng giai đoạn để so sánh biến đổi dữ liệu từ lúc bóc tách AST sơ khai đến phiên bản hiện tại
        </p>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {stages.map((stg) => {
            const Icon = stg.icon;
            const isSelected = activeStage === stg.num;
            return (
              <button
                key={stg.num}
                type="button"
                onClick={() => setActiveStage(stg.num)}
                className={`flex flex-col items-start rounded-xl border p-4 text-left transition-all duration-150 ${
                  isSelected
                    ? 'border-brand-500 bg-brand-950/50 shadow-lg ring-2 ring-brand-500/30'
                    : 'border-slate-800 bg-slate-900/50 hover:border-slate-700 hover:bg-slate-900'
                }`}
              >
                <div className="flex items-center gap-2">
                  <Icon
                    className={`h-4 w-4 ${isSelected ? 'text-brand-400' : 'text-slate-400'}`}
                  />
                  <span
                    className={`text-xs font-bold ${
                      isSelected ? 'text-brand-300' : 'text-slate-200'
                    }`}
                  >
                    {stg.name}
                  </span>
                </div>
                <p className="mt-1.5 text-[11px] text-slate-400 leading-relaxed">{stg.desc}</p>
              </button>
            );
          })}
        </div>
      </div>

      {/* Summary Statistics */}
      {diffData && (
        <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <span className="text-[11px] text-slate-400 font-medium">Tổng Biến Đổi</span>
            <div className="mt-1 text-2xl font-bold text-slate-100 font-mono">
              {diffData.total_changes}
            </div>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <span className="text-[11px] text-emerald-400 font-medium">Thêm Mới (Added)</span>
            <div className="mt-1 text-2xl font-bold text-emerald-300 font-mono">
              {diffData.added_chunks.length}
            </div>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <span className="text-[11px] text-amber-400 font-medium">Đã Hiệu Chỉnh (Modified)</span>
            <div className="mt-1 text-2xl font-bold text-amber-300 font-mono">
              {diffData.modified_chunks.length}
            </div>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <span className="text-[11px] text-rose-400 font-medium">Đã Loại Bỏ (Deleted)</span>
            <div className="mt-1 text-2xl font-bold text-rose-300 font-mono">
              {diffData.deleted_chunks.length}
            </div>
          </div>
        </div>
      )}

      {/* Main Diff Content & Mutation Ledger */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3 flex-1">
        {/* Left 2 Cols: Visual Diffs */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between pb-2 border-b border-slate-800">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-200">
              Chi Tiết Sai Khác ({displayedEntries.length} mục hiển thị)
            </h4>

            {/* Filter by Change Type */}
            <div className="flex items-center gap-2">
              <Filter className="h-3.5 w-3.5 text-slate-400" />
              <select
                value={filterType}
                onChange={(e) => setFilterType(e.target.value)}
                className="rounded-md border border-slate-700 bg-slate-900 px-2.5 py-1 text-xs text-slate-200 focus:border-brand-500 focus:outline-none"
              >
                <option value="ALL">Tất cả thay đổi</option>
                <option value="MODIFIED">Chỉ mục đã sửa (MODIFIED)</option>
                <option value="ADDED">Chỉ mục thêm mới (ADDED)</option>
                <option value="DELETED">Chỉ mục đã xóa (DELETED)</option>
              </select>
            </div>
          </div>

          {loading ? (
            <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-8 text-center text-xs text-slate-400">
              Đang tính toán sai khác phiên bản...
            </div>
          ) : activeStage === 1 ? (
            <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-8 text-center text-xs text-slate-400">
              <FileText className="mx-auto h-8 w-8 text-slate-500 mb-2" />
              <p className="font-semibold text-slate-300">Stage 1: Bản bóc tách AST ban đầu</p>
              <p className="mt-1 text-[11px]">Đây là mốc thời gian gốc (baseline), chưa phát sinh sai khác nào.</p>
            </div>
          ) : displayedEntries.length === 0 ? (
            <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-8 text-center text-xs text-slate-400">
              Không có sai khác nào trong giai đoạn hoặc bộ lọc này.
            </div>
          ) : (
            <div className="space-y-3">
              {displayedEntries.map((diff, idx) => (
                <div
                  key={idx}
                  className="rounded-xl border border-slate-800 bg-slate-900/80 p-4 shadow-sm"
                >
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <span className="font-mono text-xs font-semibold text-slate-200">
                      {diff.path}
                    </span>
                    <span
                      className={`rounded px-2.5 py-0.5 text-[10px] font-bold border ${
                        diff.change_type === 'ADDED'
                          ? 'bg-emerald-950 text-emerald-300 border-emerald-800'
                          : diff.change_type === 'DELETED'
                          ? 'bg-rose-950 text-rose-300 border-rose-800'
                          : 'bg-amber-950 text-amber-300 border-amber-800'
                      }`}
                    >
                      {diff.change_type} {diff.field_name ? `(${diff.field_name})` : ''}
                    </span>
                  </div>

                  <p className="mb-2.5 text-xs text-slate-400">{diff.description}</p>

                  {diff.old_value !== undefined && diff.new_value !== undefined && (
                    <InlineDiffViewer
                      oldText={String(diff.old_value || '')}
                      newText={String(diff.new_value || '')}
                    />
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right Col: Mutation History Ledger */}
        <div className="space-y-3">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-200 pb-2 border-b border-slate-800">
            Nhật Ký Tác Vụ Bất Biến (Mutation Ledger)
          </h4>
          <MutationLogList history={session.mutation_history} />
        </div>
      </div>
    </div>
  );
};
