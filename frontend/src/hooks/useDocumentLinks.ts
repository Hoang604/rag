import { useEffect, useState } from 'react';
import { api } from '../services/api';

let pending: Promise<Map<string, string>> | null = null;

const loadDocumentLinks = (): Promise<Map<string, string>> => {
  pending ??= api
    .documents()
    .then((documents) => new Map(documents.flatMap((doc) => (doc.source_url ? [[doc.doc_code, doc.source_url] as const] : []))))
    .catch(() => {
      pending = null;
      return new Map<string, string>();
    });
  return pending;
};

export const useDocumentLinks = (): Map<string, string> => {
  const [links, setLinks] = useState<Map<string, string>>(() => new Map());

  useEffect(() => {
    let active = true;
    void loadDocumentLinks().then((loaded) => {
      if (active) setLinks(loaded);
    });
    return () => {
      active = false;
    };
  }, []);

  return links;
};
