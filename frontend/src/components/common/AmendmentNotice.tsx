import React from 'react';
import { History } from 'lucide-react';
import { useI18n } from '../../i18n/I18nContext';
import { AmendmentNote } from '../../types/api';

export const AmendmentNotice: React.FC<{ notes: AmendmentNote[] }> = ({ notes }) => {
  const { t } = useI18n();
  if (notes.length === 0) return null;
  return (
    <ul data-testid="amendment-notice" className="mt-3 space-y-1">
      {notes.map((note) => (
        <li key={note.path} className="flex items-start gap-2 text-xs leading-5 text-amber-400">
          <History className="mt-0.5 h-3.5 w-3.5 flex-none" />
          <span>
            {t('amend.note', {
              label: note.label,
              doc: note.doc_code,
              d: note.effective_date,
              title: note.title,
            })}
          </span>
        </li>
      ))}
    </ul>
  );
};
