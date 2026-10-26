import React from 'react';
import { ExternalLink } from 'lucide-react';
import { useI18n } from '../../i18n/I18nContext';

export const DocumentLink: React.FC<{
  docCode: string;
  href?: string;
  className?: string;
  'data-testid'?: string;
}> = ({ docCode, href, className = '', 'data-testid': testId }) => {
  const { t } = useI18n();
  if (!href) {
    return (
      <span data-testid={testId} className={className}>
        {docCode}
      </span>
    );
  }
  return (
    <a
      data-testid={testId}
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      title={t('doc.open', { doc: docCode })}
      className={`inline-flex items-center gap-1 underline decoration-slate-600 underline-offset-2 transition-colors duration-200 hover:text-brand-400 hover:decoration-brand-400 ${className}`}
    >
      {docCode}
      <ExternalLink className="h-3 w-3 flex-none" aria-hidden="true" />
      <span className="sr-only">{t('doc.newTab')}</span>
    </a>
  );
};
