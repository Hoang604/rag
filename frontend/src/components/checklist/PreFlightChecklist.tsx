import React from 'react';
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Database,
  RefreshCw,
  ShieldCheck,
  XCircle,
} from 'lucide-react';
import { PreFlightValidationResponse } from '../../types/preflight';
import { StagingDocumentSession } from '../../types/staging';

interface PreFlightChecklistProps {
  session: StagingDocumentSession;
  validationResult: PreFlightValidationResponse | null;
  validating: boolean;
  onReValidate: () => void;
  onOpenPromotionModal: () => void;
}

export const PreFlightChecklist: React.FC<PreFlightChecklistProps> = ({
  session,
  validationResult,
  validating,
  onReValidate,
  onOpenPromotionModal,
}) => {
  const rules = [
    {
      id: 'ORPHAN_CHUNKS',
      name: '1. Kiểm tra tính liên tục cây phân cấp (Orphan Chunks)',
      desc: 'Đảm bảo mọi điều khoản con đều có tiền tố điều khoản cha hợp lệ.',
    },
    {
      id: 'LTREE_SYNTAX',
      name: '2. Kiểm tra định dạng đường dẫn LTree (LTree Syntax)',
      desc: 'Đảm bảo tên các phân đoạn path chỉ chứa chữ cái, chữ số và dấu gạch dưới.',
    },
    {
      id: 'ROOT_CODE_ALIGNMENT',
      name: '3. Kiểm tra tiền tố mã văn bản gốc (Root Code Alignment)',
      desc: 'Đảm bảo tất cả các chunk thuộc văn bản có root segment khớp với mã văn bản.',
    },
    {
      id: 'DUPLICATE_PATH_COLLISION',
      name: '4. Kiểm tra trùng lặp đường dẫn (Duplicate Path Collision)',
      desc: 'Không cho phép hai điều khoản khác nhau có cùng đường dẫn phân cấp.',
    },
    {
      id: 'STATUTORY_DATES',
      name: '5. Kiểm tra logic niên hạn hiệu lực (Statutory Dates)',
      desc: 'Ngày có hiệu lực phải hợp lệ; ngày hết hiệu lực (nếu có) phải sau ngày có hiệu lực.',
    },
    {
      id: 'CONTENT_GROUNDING',
      name: '6. Kiểm tra nội dung nguyên văn (Content Grounding)',
      desc: 'Văn bản nguyên văn verbatim_text và contextualized_text không được để trống.',
    },
    {
      id: 'GRAPH_EDGE_INTEGRITY',
      name: '7. Kiểm tra tính toàn vẹn quan hệ pháp lý (Graph Edge Integrity)',
      desc: 'Đảm bảo source_path và target_path của các cạnh quan hệ tồn tại trong dữ liệu.',
    },
  ];

  const ruleStatusMap = validationResult?.summary?.rule_status || {};
  const issues = validationResult?.issues || [];
  const blockingIssues = issues.filter((i) => i.blocking);
  const isPassed = validationResult?.passed ?? false;

  return (
    <div className="flex h-full w-full flex-col overflow-y-auto bg-slate-950 p-6">
      {/* Header Status Card */}
      <div
        className={`mb-6 flex flex-wrap items-center justify-between gap-4 rounded-xl border p-5 shadow transition ${
          isPassed
            ? 'border-emerald-800/80 bg-emerald-950/40'
            : 'border-rose-800/80 bg-rose-950/40'
        }`}
      >
        <div className="flex items-center gap-3.5">
          <div
            className={`rounded-full p-2.5 ${
              isPassed
                ? 'bg-emerald-900 text-emerald-300 border border-emerald-700'
                : 'bg-rose-900 text-rose-300 border border-rose-700'
            }`}
          >
            {isPassed ? (
              <ShieldCheck className="h-7 w-7" />
            ) : (
              <AlertCircle className="h-7 w-7" />
            )}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs font-bold text-slate-300">
                {session.doc_code}
              </span>
              <span className="text-slate-500">•</span>
              <span className="text-xs text-slate-400 truncate max-w-md">
                {session.title}
              </span>
            </div>
            <h3 className="text-base font-bold text-slate-100 mt-1">
              {isPassed
                ? 'Đạt Toàn Bộ 7 Tiêu Chuẩn Thẩm Định Tính Toàn Vẹn!'
                : `Phát Hiện ${blockingIssues.length} Lỗi Chặn Phê Duyệt`}
            </h3>
            <p className="text-xs text-slate-300 mt-0.5">
              {isPassed
                ? 'Văn bản đáp ứng đầy đủ tính toàn vẹn ngữ pháp, quan hệ pháp lý và niên hạn.'
                : 'Vui lòng chỉnh sửa các lỗi chặn bên dưới trước khi phê duyệt vào CSDL PostgreSQL.'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={onReValidate}
            disabled={validating}
            className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900 px-4 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-800 transition"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${validating ? 'animate-spin text-brand-400' : ''}`}
            />
            <span>Thẩm Định Lại</span>
          </button>

          <button
            onClick={onOpenPromotionModal}
            disabled={!isPassed}
            className={`flex items-center gap-2 rounded-lg px-5 py-2 text-xs font-semibold shadow transition ${
              isPassed
                ? 'bg-brand-600 text-white hover:bg-brand-500 shadow-brand-900/40'
                : 'bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700'
            }`}
          >
            <Database className="h-4 w-4" />
            <span>Tiến Hành Phê Duyệt</span>
          </button>
        </div>
      </div>

      {/* 7 Automated Checklist Rows */}
      <div className="mb-6 space-y-3">
        <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 mb-2">
          Danh Sách 7 Hạng Mục Thẩm Định Tự Động
        </h4>

        {rules.map((r) => {
          const status = ruleStatusMap[r.id];
          const passed = status?.passed ?? isPassed;
          const issueCount = status?.issues_count ?? 0;

          return (
            <div
              key={r.id}
              className={`flex items-center justify-between gap-4 rounded-lg border p-4 transition ${
                passed
                  ? 'border-slate-800 bg-slate-900/60'
                  : 'border-rose-800/60 bg-rose-950/20'
              }`}
            >
              <div className="flex items-center gap-3">
                {passed ? (
                  <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0" />
                ) : (
                  <XCircle className="h-5 w-5 text-rose-400 shrink-0 animate-pulse" />
                )}
                <div>
                  <span className="font-semibold text-xs text-slate-200">
                    {r.name}
                  </span>
                  <p className="text-[11px] text-slate-400 mt-0.5">{r.desc}</p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {passed ? (
                  <span className="rounded bg-emerald-950 px-2.5 py-1 text-xs font-bold text-emerald-300 border border-emerald-800">
                    ĐẠT ✔
                  </span>
                ) : (
                  <span className="rounded bg-rose-950 px-2.5 py-1 text-xs font-bold text-rose-300 border border-rose-800">
                    CHẶN ({issueCount} lỗi) ✖
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Issues Detail List */}
      {issues.length > 0 && (
        <div className="space-y-3">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300">
            Chi Tiết Các Lỗi Phát Hiện Cần Xử Lý ({issues.length})
          </h4>
          <div className="space-y-2">
            {issues.map((issue, idx) => (
              <div
                key={idx}
                className="flex items-start gap-3 rounded-lg border border-rose-900/60 bg-rose-950/30 p-3.5 text-xs text-rose-200"
              >
                <AlertTriangle className="h-4 w-4 text-rose-400 shrink-0 mt-0.5" />
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-rose-300">{issue.rule}</span>
                    {issue.path && (
                      <span className="rounded bg-slate-950 px-2 py-0.5 font-mono text-[10px] text-slate-300 border border-slate-800">
                        {issue.path}
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-slate-300">{issue.message}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
