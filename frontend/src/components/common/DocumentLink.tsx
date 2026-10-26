import React from 'react';
import { ExternalLink } from 'lucide-react';
import { useI18n } from '../../i18n/I18nContext';
import { DocumentLinkSet } from '../../hooks/useDocumentLinks';

const hostOf = (url: string): string => {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
};

const LINK = 'inline-flex items-center gap-1 underline decoration-slate-600 underline-offset-2 transition-colors duration-200 hover:text-brand-400 hover:decoration-brand-400';

const External: React.FC<{ href: string; title: string; className?: string; testId?: string; children: React.ReactNode }> = ({
  href,
  title,
  className = '',
  testId,
  children,
}) => {
  const { t } = useI18n();
  return (
    <a data-testid={testId} href={href} target="_blank" rel="noopener noreferrer" title={title} className={`${LINK} ${className}`}>
      {children}
      <ExternalLink className="h-3 w-3 flex-none" aria-hidden="true" />
      <span className="sr-only">{t('doc.newTab')}</span>
    </a>
  );
};

export const DocumentLink: React.FC<{
  docCode: string;
  links?: DocumentLinkSet;
  fragment?: string | null;
  className?: string;
  'data-testid'?: string;
}> = ({ docCode, links, fragment, className = '', 'data-testid': testId }) => {
  const { t } = useI18n();
  const main = links?.official ?? links?.provision;
  if (!main) {
    return (
      <span data-testid={testId} className={className}>
        {docCode}
      </span>
    );
  }
  const deep = links?.provision && fragment ? `${links.provision.split('#')[0]}${fragment}` : null;
  return (
    <span className={`inline-flex flex-wrap items-center gap-x-2 gap-y-0.5 ${className}`}>
      <External href={main} testId={testId} title={t(links?.official ? 'doc.openOfficial' : 'doc.open', { doc: docCode, site: hostOf(main) })}>
        {docCode}
      </External>
      <span className="text-[11px] text-slate-500">{hostOf(main)}</span>
      {deep && (
        <External href={deep} testId={testId ? `${testId}-provision` : undefined} title={t('doc.openAt', { doc: docCode, site: hostOf(deep) })} className="text-[11px]">
          {t('doc.toProvision')}
        </External>
      )}
    </span>
  );
};
