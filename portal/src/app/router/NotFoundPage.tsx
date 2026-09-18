import { useTranslation } from "react-i18next";

import { EmptyState, LinkButton, AlertCircleIcon } from "@/shared/ui";
import { useTierBase } from "@/shared/lib";

/**
 * «Страница не найдена» — for a mistyped URL or a link that has outlived its
 * page.
 *
 * Mounted twice: inside `PublicShell` for the storefront and inside `AppShell`
 * for the cabinet, so it always arrives wearing the site's own chrome. It used
 * to be the storefront's ONLY top-level route, outside every shell, which left
 * a visitor on a page with no header, no navigation, no `<main>` and a single
 * link back to `/` — nothing to read and nowhere to go but home (IMEX-20).
 *
 * `titleAs="h1"` because here the empty state IS the page. Everywhere else this
 * component appears it sits under a heading that already exists.
 */
export function NotFoundPage() {
  const base = useTierBase();
  const { t } = useTranslation();
  return (
    <div className="mx-auto max-w-[1440px] px-4 py-16 lg:px-6">
      <EmptyState
        icon={<AlertCircleIcon size={28} />}
        titleAs="h1"
        title={t("errors.notFound")}
        description={t("errors.notFoundBody")}
        action={
          /* Two ways out, because "home" is the answer to only one of the two
             reasons anyone lands here. Someone who mistyped wants the front
             page; someone following a dead listing link wants the catalogue,
             where the thing they were after may still be. */
          <div className="flex flex-wrap items-center justify-center gap-2">
            <LinkButton to={base || "/"}>{t("nav.home")}</LinkButton>
            <LinkButton to="/market" variant="secondary">
              {t("public.nav.catalog")}
            </LinkButton>
          </div>
        }
      />
    </div>
  );
}
