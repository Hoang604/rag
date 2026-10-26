import { useEffect, useState } from 'react';
import { api } from '../services/api';

export interface DocumentLinkSet {
  official?: string;
  provision?: string;
}

let pending: Promise<Map<string, DocumentLinkSet>> | null = null;

const loadDocumentLinks = (): Promise<Map<string, DocumentLinkSet>> => {
  pending ??= api
    .documents()
    .then(
      (documents) =>
        new Map(
          documents.flatMap((doc) =>
            doc.official_url || doc.provision_url
              ? [[doc.doc_code, { official: doc.official_url ?? undefined, provision: doc.provision_url ?? undefined }] as const]
              : []
          )
        )
    )
    .catch(() => {
      pending = null;
      return new Map<string, DocumentLinkSet>();
    });
  return pending;
};

export const useDocumentLinks = (): Map<string, DocumentLinkSet> => {
  const [links, setLinks] = useState<Map<string, DocumentLinkSet>>(() => new Map());

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
