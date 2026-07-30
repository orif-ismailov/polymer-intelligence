import { useState } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { usePublicCompanyProfile } from "@/entities/market";
import {
  ProfileAboutTab,
  ProfileActionBar,
  ProfileDocumentsTab,
  ProfileHeader,
  ProfileProductsTab,
  ProfileReviewsTab,
} from "@/features/company-profile";
import {
  Alert,
  LinkButton,
  LoadingView,
  Tabs,
  type TabItem,
} from "@/shared/ui";

const TAB_IDS = ["about", "products", "reviews", "documents"] as const;
type TabId = (typeof TAB_IDS)[number];

/**
 * Public seller company profile — `docs/new-design/company_profile.jpeg`.
 *
 * Opened from a product-detail seller card when `seller_company_id` is set.
 * `?fromOffer=` carries the offer the buyer came from so «Написать» can return
 * to that offer's inquiry form.
 */
export function SellerProfilePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { companyId: rawId } = useParams<{ companyId: string }>();
  const companyId = rawId ? Number(rawId) : null;
  const [search] = useSearchParams();
  const fromOffer = search.get("fromOffer");
  const fromOfferId = fromOffer && /^\d+$/.test(fromOffer) ? Number(fromOffer) : null;

  const profileQuery = usePublicCompanyProfile(
    companyId != null && Number.isFinite(companyId) ? companyId : null,
  );
  const [tab, setTab] = useState<TabId>(TAB_IDS[0]);
  const [shareNote, setShareNote] = useState<string | null>(null);

  if (profileQuery.isLoading) return <LoadingView label={t("common.loading")} />;
  if (profileQuery.isError || !profileQuery.data) {
    return (
      <div className="space-y-4">
        <Alert tone="danger">{t("companyProfile.notFound")}</Alert>
        <LinkButton to="/market" variant="secondary">
          {t("market.backToMarket")}
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
    if (fromOfferId != null) {
      void navigate(`/market/${fromOfferId}#inquiry`);
      return;
    }
    setTab("products");
  }

  function goRfq(): void {
    setTab("products");
  }

  return (
    <div className="space-y-5 pb-36 md:pb-0" data-testid="seller-profile">
      <ProfileHeader profile={profile} onShare={() => void share()} />

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
        />
      ) : null}
      {tab === "reviews" ? <ProfileReviewsTab /> : null}
      {tab === "documents" ? <ProfileDocumentsTab /> : null}

      {fromOfferId == null && tab === "products" ? (
        <p className="text-center text-xs text-text-subtle">
          {t("companyProfile.pickOfferHint")}
        </p>
      ) : null}

      <ProfileActionBar
        onMessage={goMessage}
        onRfq={goRfq}
        messageDisabled={fromOfferId == null && profile.offer_count === 0}
      />
    </div>
  );
}
