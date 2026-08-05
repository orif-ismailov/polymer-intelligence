import { useTranslation } from "react-i18next";

import { offerImageUrl } from "@/entities/market";
import { Badge, Card, CardBody } from "@/shared/ui";

import { documentLabel } from "../model/labels";
import type { ProductDetailFile } from "../model/types";

interface OfferDocumentsProps {
  offerId: number;
  /** Everything that is not a photo — TDS, SDS, COA, certificates, the passport. */
  documents: ProductDetailFile[];
}

/**
 * The «Документы» panel.
 *
 * The files themselves are already public — `offerImageUrl` points at the
 * webapp media endpoint, which has no auth dependency — so the storefront can
 * list and serve them exactly as the cabinet does.
 */
export function OfferDocuments({ offerId, documents }: OfferDocumentsProps) {
  const { t } = useTranslation();

  return (
    <Card>
      <CardBody>
        {documents.length > 0 ? (
          <ul className="space-y-2">
            {documents.map((file) => (
              <li key={file.id}>
                <a
                  href={offerImageUrl(offerId, file.id)}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center justify-between rounded-md border border-border px-3 py-2.5 text-sm hover:border-brand-line"
                >
                  <span className="min-w-0 truncate text-text">{documentLabel(file, t)}</span>
                  {/* `offerDocumentKind`, not `documentKind` — the latter is the
                      company-verification set (bank letter, director ID …), so
                      tds/sds/coa/lab_passport used to render as raw enum strings. */}
                  <Badge tone="neutral">
                    {t(`offerDocumentKind.${file.kind}`, { defaultValue: file.kind })}
                  </Badge>
                </a>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-text-muted">{t("market.noDocuments")}</p>
        )}
      </CardBody>
    </Card>
  );
}
