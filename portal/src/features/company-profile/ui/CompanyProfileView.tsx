import { useState, type ReactNode } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useCompanies } from "@/entities/company";
import { usePublicCompanyProfile } from "@/entities/market";
import {
  Alert,
  LinkButton,
  LoadingView,
  StickyActionBar,
  Tabs,
  type TabItem,
} from "@/shared/ui";

import { ProfileAboutTab } from "./ProfileAboutTab";
import { ProfileActionBar } from "./ProfileActionBar";
import { ProfileDocumentsTab } from "./ProfileDocumentsTab";
import { ProfileHeader } from "./ProfileHeader";
import { ProfileProductsTab } from "./ProfileProductsTab";
import { ProfileReviewsTab } from "./ProfileReviewsTab";

const TAB_IDS = ["about", "products", "reviews", "documents"] as const;
type TabId = (typeof TAB_IDS)[number];

export interface CompanyProfileViewProps {
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
  /**
   * `manufacturer` swaps the buyer footer's actions and labels for the
   * factory flow (`docs/new-design/manufacturer_flow.jpeg`): Message opens a
   * chat thread directly instead of scrolling to an offer's inquiry form, and
   * product links carry `?fromManufacturer=1` so the offer page can route RFQ
   * to the factory-RFQ wizard.
   */
  mode?: "seller" | "manufacturer";
}

/**
 * Shared public company profile sheet — `docs/new-design/company_profile.jpeg`.
 *
 * Used by both `/sellers/:id` and `/companies/:id` so the two routes stay
 * visually identical without duplicating the tab chrome.
 */
export function CompanyProfileView({
  companyId,
  fromOfferId = null,
  backTo,
  ownerActions,
  mode = "seller",
}: CompanyProfileViewProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const profileQuery = usePublicCompanyProfile(companyId);
  const companiesQuery = useCompanies();
  const [tab, setTab] = useState<TabId>(TAB_IDS[0]);
  const [shareNote, setShareNote] = useState<string | null>(null);

  const isOwner =
    companiesQuery.data?.some((c) => c.id === companyId) === true;

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

  const tabs: TabItem[] = TAB_IDS.map((id) => ({
    id,
    label: t(`companyProfile.tabs.${id}`),
    count: id === "products" && profile.offer_count > 0 ? profile.offer_count : undefined,
  }));

  async function share(): Promise<void> {
    const url = window.location.href;
    try {
      if (navigator.share) {
        await navigator.share({
          title: profile.short_name ?? profile.legal_name ?? t("companyProfile.title"),
          url,
        });
        return;
      }
      await navigator.clipboard.writeText(url);
      setShareNote(t("market.detail.linkCopied"));
      window.setTimeout(() => setShareNote(null), 2500);
    } catch {
      /* cancelled */
    }
  }

  function goMessage(): void {
    if (mode === "manufacturer") {
      void navigate(`/manufacturers/${profile.id}/chat`);
      return;
    }
    if (fromOfferId != null) {
      void navigate(`/market/${fromOfferId}#inquiry`);
      return;
    }
    setTab("products");
  }

  function goRfq(): void {
    setTab("products");
  }

  const showBuyerBar = !isOwner;
  const resolvedOwnerActions =
    ownerActions ??
    (isOwner ? (
      <StickyActionBar>
        <div className="flex w-full gap-2" data-testid="company-owner-actions">
          <LinkButton
            variant="outline"
            size="lg"
            className="min-w-0 flex-1"
            to={`/companies/${profile.id}/manage`}
          >
            {t("company.manage")}
          </LinkButton>
          <LinkButton size="lg" className="min-w-0 flex-[1.4]" to="/offers/new">
            {t("company.createOffer")}
          </LinkButton>
        </div>
      </StickyActionBar>
    ) : null);
  const showOwnerBar = resolvedOwnerActions != null;

  return (
    <div
      className={`space-y-5 ${showBuyerBar || showOwnerBar ? "pb-36 md:pb-0" : ""}`}
      data-testid="company-profile"
    >
      <ProfileHeader profile={profile} onShare={() => void share()} backTo={backTo} />

      {shareNote ? <Alert tone="success">{shareNote}</Alert> : null}

      <Tabs
        items={tabs}
        value={tab}
        onChange={(id) => setTab(id as TabId)}
        variant="underlineGold"
        label={profile.short_name ?? profile.legal_name ?? t("companyProfile.title")}
      />

      {tab === "about" ? <ProfileAboutTab profile={profile} /> : null}
      {tab === "products" ? (
        <ProfileProductsTab
          offers={profile.offers}
          offerCount={profile.offer_count}
          onSeeAll={() => {
            void navigate(`/market?seller=${profile.id}`);
          }}
          linkQuery={mode === "manufacturer" ? "?fromManufacturer=1" : undefined}
        />
      ) : null}
      {tab === "reviews" ? <ProfileReviewsTab /> : null}
      {tab === "documents" ? <ProfileDocumentsTab /> : null}

      {showBuyerBar && fromOfferId == null && tab === "products" ? (
        <p className="text-center text-xs text-text-subtle">
          {t("companyProfile.pickOfferHint")}
        </p>
      ) : null}

      {showBuyerBar ? (
        <ProfileActionBar
          onMessage={goMessage}
          onRfq={goRfq}
          messageDisabled={
            mode === "manufacturer" ? false : fromOfferId == null && profile.offer_count === 0
          }
          mode={mode}
        />
      ) : null}

      {showOwnerBar ? resolvedOwnerActions : null}
    </div>
  );
}
