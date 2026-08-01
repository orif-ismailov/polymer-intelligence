import { useState, type ReactNode } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useCompanies } from "@/entities/company";
import { usePublicCompanyProfile } from "@/entities/market";
import { Alert, LinkButton, LoadingView, StickyActionBar } from "@/shared/ui";

import { COMPANY_PROFILE_TAB_IDS, type CompanyProfileTabId } from "../model/tabs";

import { CompanyProfileView } from "./CompanyProfileView";
import { ProfileActionBar } from "./ProfileActionBar";

export interface CabinetCompanyProfileProps {
  companyId: number;
  /** Offer the buyer came from — «Написать» returns to that inquiry form. */
  fromOfferId?: number | null;
  /** Where the header back control goes. Defaults to browser history. */
  backTo?: string;
  /**
   * Extra footer when the viewer owns this company (manage / verification).
   * Buyer Message/RFQ bar is hidden in that case.
   */
  ownerActions?: ReactNode;
}

/**
 * The cabinet's company profile — `/cabinet/sellers/:id` and
 * `/cabinet/companies/:id`.
 *
 * Reads the authenticated catalog profile, answers "do I own this", and picks
 * the sticky footer those two decide between. `CompanyProfileView` renders the
 * sheet and is shared with the public `/{directory}/:id`, which does the same
 * job from the anonymous payload.
 *
 * There is no `manufacturer` mode here any more: the factory profile IS the
 * public `/manufacturers/:id`, which mounts the chat + factory-RFQ footer itself
 * once a session exists.
 */
export function CabinetCompanyProfile({
  companyId,
  fromOfferId = null,
  backTo,
  ownerActions,
}: CabinetCompanyProfileProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const profileQuery = usePublicCompanyProfile(companyId);
  const companiesQuery = useCompanies();
  const [tab, setTab] = useState<CompanyProfileTabId>(COMPANY_PROFILE_TAB_IDS[0]);

  const isOwner = companiesQuery.data?.some((c) => c.id === companyId) === true;

  if (profileQuery.isLoading) return <LoadingView label={t("common.loading")} />;
  if (profileQuery.isError || !profileQuery.data) {
    return (
      <div className="space-y-4">
        <Alert tone="danger">{t("companyProfile.notFound")}</Alert>
        <LinkButton to={backTo ?? "/market"} variant="secondary">
          {backTo ? t("common.back") : t("market.backToMarket")}
        </LinkButton>
      </div>
    );
  }

  const profile = profileQuery.data;

  /*
   * A seller reached from a listing returns to that listing's inquiry form; a
   * seller reached cold has no thread to open, so the sheet shows their products
   * and asks the buyer to pick one — an inquiry belongs to an offer.
   */
  function goMessage(): void {
    if (fromOfferId != null) {
      void navigate(`/market/${fromOfferId}#inquiry`);
      return;
    }
    setTab("products");
  }

  const resolvedOwnerActions =
    ownerActions ??
    (isOwner ? (
      <StickyActionBar>
        <div className="flex w-full gap-2" data-testid="company-owner-actions">
          <LinkButton
            variant="outline"
            size="lg"
            className="min-w-0 flex-1"
            to={`/cabinet/companies/${profile.id}/manage`}
          >
            {t("company.manage")}
          </LinkButton>
          <LinkButton size="lg" className="min-w-0 flex-[1.4]" to="/cabinet/offers/new">
            {t("company.createOffer")}
          </LinkButton>
        </div>
      </StickyActionBar>
    ) : null);

  const showBuyerBar = !isOwner;
  const actionBar =
    resolvedOwnerActions ??
    (showBuyerBar ? (
      <ProfileActionBar
        onMessage={goMessage}
        onRfq={() => setTab("products")}
        messageDisabled={fromOfferId == null && profile.offer_count === 0}
      />
    ) : null);

  return (
    <CompanyProfileView
      company={profile}
      backTo={backTo}
      tab={tab}
      onTabChange={setTab}
      productHref={(offer) => `/market/${offer.id}`}
      seeAllHref={`/market?seller_company_id=${profile.id}`}
      actionBar={actionBar}
      footerNote={
        showBuyerBar && fromOfferId == null && tab === "products" ? (
          <p className="text-center text-xs text-text-subtle">
            {t("companyProfile.pickOfferHint")}
          </p>
        ) : null
      }
    />
  );
}
