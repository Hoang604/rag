import React from 'react';
import { Clock } from 'lucide-react';
import { StagingDocumentSession } from '../../types/staging';
import { MutationLogList } from './MutationLogList';

interface MutationHistoryViewProps {
  session: StagingDocumentSession;
}

export const MutationHistoryView: React.FC<MutationHistoryViewProps> = ({ session }) => {
  return (
    <div className="flex h-full w-full flex-col overflow-y-auto bg-slate-950 p-6">
      <div className="mb-6 rounded-xl border border-slate-800 bg-slate-900/80 p-5 shadow">
        <div className="flex items-center gap-2 mb-2">
          <Clock className="h-4 w-4 text-brand-400" />
          <h3 className="text-sm font-bold uppercase tracking-wider text-slate-200">
            Nhật Ký Tác Vụ Bất Biến (WAL Mutation History)
          </h3>
        </div>
        <p className="text-xs text-slate-400">
          Toàn bộ lịch sử can thiệp dữ liệu được ghi nhận đơn điệu (monotonic LSN) vào Write-Ahead Log.
        </p>
      </div>
      <div className="max-w-4xl">
        <MutationLogList history={session.mutation_history} />
      </div>
    </div>
  );
};
