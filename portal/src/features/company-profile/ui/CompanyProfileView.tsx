import { useState, type ReactNode } from "react";

import { useTranslation } from "react-i18next";

import { Alert, Tabs, type TabItem } from "@/shared/ui";

import { COMPANY_PROFILE_TAB_IDS, type CompanyProfileTabId } from "../model/tabs";
import type { CompanyProfileCompany, CompanyProfileOffer } from "../model/types";

import { ProfileAboutTab } from "./ProfileAboutTab";
import { ProfileDocumentsTab } from "./ProfileDocumentsTab";
import { ProfileHeader } from "./ProfileHeader";
import { ProfileProductsTab } from "./ProfileProductsTab";
import { ProfileReviewsTab } from "./ProfileReviewsTab";

export interface CompanyProfileViewProps {
  company: CompanyProfileCompany;
  /** Where the header back control goes. Defaults to browser history. */
  backTo?: string;
  /** Where a product row links. */
  productHref: (offer: CompanyProfileOffer) => string;
  /** «Показать все» target when the company has more listings than shown. */
  seeAllHref?: string;
  /**
   * Tab state is LIFTED, not internal: the cabinet's footer buttons switch to
   * «Продукты» («выберите позицию» is the honest answer to an RFQ with no offer
   * picked), so the owner of those buttons has to own the tab too.
   */
  tab: CompanyProfileTabId;
  onTabChange: (id: CompanyProfileTabId) => void;
  /**
   * The sticky footer, when there is one. A slot because every version of it is
   * an answer to a question only a session can ask — "is this mine", "may I
   * contact them" — and the storefront, whose HTML is shared-cached, must not
   * ask any of them. It passes nothing and puts a single CTA in `headerActions`.
   */
  actionBar?: ReactNode;
  /** Rendered under the header — the storefront's «Связаться» link lives here. */
  headerActions?: ReactNode;
  /** Rendered between the panels and the footer (the pick-an-offer hint). */
  footerNote?: ReactNode;
  /**
   * Mounted at the top of the «Отзывы» panel — the review form, once there is
   * a session to write one with. A slot for the same reason `actionBar` is one:
   * the storefront's HTML is shared-cached, so anything that varies by visitor
   * has to arrive after hydration rather than from this component.
   */
  reviewAction?: ReactNode;
  /**
   * Render every tab panel, hiding the inactive ones with the `hidden`
   * attribute, instead of mounting only the active one.
   *
   * The storefront needs it: this sheet has to reach a crawler as HTML, and the
   * company's facts live in the About panel. The cabinet leaves it off — nothing
   * indexes `/cabinet`, and mounting one panel is cheaper.
   */
  renderAllPanels?: boolean;
}

/**
 * The company profile sheet — `docs/new-design/company_profile.jpeg`.
 *
 * Presentational on purpose. It is rendered by the cabinet's
 * `/cabinet/sellers/:id` and `/cabinet/companies/:id` and by the public
 * `/{directory}/:id`, which read from two different endpoints
 * (`/portal/market/companies/{id}` behind auth,
 * `/public/directories/{slug}/{id}` in front of it). Both payloads satisfy
 * `CompanyProfileCompany` structurally, so the fetch belongs to the caller and
 * this component never needs to know which tier it is in.
 *
 * `CabinetCompanyProfile` is the wrapper that does the authenticated fetch.
 */
export function CompanyProfileView({
  company,
  backTo,
  productHref,
  seeAllHref,
  tab,
  onTabChange,
  actionBar,
  headerActions,
  footerNote,
  reviewAction,
  renderAllPanels = false,
}: CompanyProfileViewProps) {
  const { t } = useTranslation();
  const [shareNote, setShareNote] = useState<string | null>(null);

  const name = company.short_name ?? company.legal_name ?? t("companyProfile.title");

  const tabs: TabItem[] = COMPANY_PROFILE_TAB_IDS.map((id) => ({
    id,
    label: t(`companyProfile.tabs.${id}`),
    count: id === "products" && company.offer_count > 0 ? company.offer_count : undefined,
  }));

  async function share(): Promise<void> {
    const url = window.location.href;
    try {
      if (navigator.share) {
        await navigator.share({ title: name, url });
        return;
      }
      await navigator.clipboard.writeText(url);
      setShareNote(t("market.detail.linkCopied"));
      window.setTimeout(() => setShareNote(null), 2500);
    } catch {
      /* cancelled */
    }
  }

  function panel(id: CompanyProfileTabId, content: ReactNode): ReactNode {
    if (!renderAllPanels) return tab === id ? content : null;
    // The `hidden` ATTRIBUTE on a bare wrapper — a Tailwind `display` utility on
    // the same element would override it.
    return <div hidden={tab !== id}>{content}</div>;
  }

  return (
    <div
      className={`space-y-5 ${actionBar ? "pb-36 md:pb-0" : ""}`}
      data-testid="company-profile"
    >
      <ProfileHeader profile={company} onShare={() => void share()} backTo={backTo} />

      {shareNote ? <Alert tone="success">{shareNote}</Alert> : null}

      {headerActions}

      <Tabs
        items={tabs}
        value={tab}
        onChange={(id) => onTabChange(id as CompanyProfileTabId)}
        variant="underlineGold"
        label={name}
      />

      {panel("about", <ProfileAboutTab profile={company} />)}
      {panel(
        "products",
        <ProfileProductsTab
          offers={company.offers}
          offerCount={company.offer_count}
          productHref={productHref}
          seeAllHref={seeAllHref}
        />,
      )}
      {panel(
        "reviews",
        <ProfileReviewsTab
          rating={company.rating}
          reviewCount={company.review_count}
          reviews={company.reviews}
          action={reviewAction}
        />,
      )}
      {panel("documents", <ProfileDocumentsTab />)}

      {footerNote}
      {actionBar}
    </div>
  );
}
