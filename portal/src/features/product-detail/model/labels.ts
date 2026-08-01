import type { TFunction } from "i18next";

import type { ProductDetailFile } from "./types";

/**
 * Label a document by its KIND, falling back to the uploaded filename.
 *
 * That order matters: the public payload carries no `file_name`, and «TDS PDF»
 * reads better than «scan_002.pdf» even where one exists. `docChip` is the short
 * chip family and has no entry for `other`, so the chain ends at
 * `offerDocumentKind`, which covers every kind in all three locales — a raw enum
 * is unreachable.
 */
export function documentLabel(file: ProductDetailFile, t: TFunction): string {
  return t(`market.detail.docChip.${file.kind}`, {
    defaultValue:
      file.file_name ?? t(`offerDocumentKind.${file.kind}`, { defaultValue: file.kind }),
  });
}
