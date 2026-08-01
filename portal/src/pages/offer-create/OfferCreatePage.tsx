import { useEffect, useRef } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { useOffer } from "@/entities/offer";
import { OfferWizard, clampStep, useOfferDraft } from "@/features/offer-wizard";
import { OffersLocked } from "@/pages/offers";
import { ErrorView, LinkButton, LoadingView } from "@/shared/ui";

/**
 * Host for the add-product flow, at `/cabinet/offers/new/:step` and
 * `/cabinet/offers/:offerId/edit/:step`.
 *
 * The step lives in the URL (the registration wizard's pattern): a reload, a
 * shared link and the browser's back button all land where they say they will,
 * and the draft in the store survives the hop because it is not router state.
 */
export function OfferCreatePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const params = useParams<{ step?: string; offerId?: string }>();
  const step = clampStep(params.step);
  const isEdit = params.offerId !== undefined;
  const offerId = isEdit ? Number(params.offerId) : null;

  const { activeCompany, isLoading: companyLoading } = useActiveCompany();
  const companyId = activeCompany?.id ?? null;
  const offerQuery = useOffer(companyId, offerId);

  const hydrate = useOfferDraft((s) => s.hydrate);
  const reset = useOfferDraft((s) => s.reset);
  const draftOfferId = useOfferDraft((s) => s.offerId);

  const base = isEdit ? `/cabinet/offers/${offerId}/edit` : "/cabinet/offers/new";

  // Normalize an out-of-range / non-numeric step to a canonical URL.
  useEffect(() => {
    if (String(step) !== params.step) void navigate(`${base}/${step}`, { replace: true });
  }, [step, params.step, base, navigate]);

  /*
   * Seed the draft once per offer. Re-hydrating on every render of the query
   * (TanStack refetches on focus) would throw away everything typed since —
   * which is why the guard is the id the store already holds, not a boolean.
   */
  const seeded = useRef<number | null | undefined>(undefined);
  useEffect(() => {
    if (isEdit) {
      const offer = offerQuery.data;
      if (!offer || seeded.current === offer.id) return;
      seeded.current = offer.id;
      hydrate(offer);
      return;
    }
    // Entering the create flow with a draft left over from an edit would publish
    // an update as if it were a new listing.
    if (seeded.current === null && draftOfferId === null) return;
    seeded.current = null;
    reset();
  }, [isEdit, offerQuery.data, hydrate, reset, draftOfferId]);

  // Leaving the flow entirely drops the draft — a half-written listing is not
  // something to resurrect three screens later without saying so.
  useEffect(() => () => reset(), [reset]);

  if (companyLoading) return <LoadingView label={t("common.loading")} />;

  if (!activeCompany) {
    return (
      <ErrorView title={t("home.noActiveCompany")} message={t("home.noActiveCompanyBody")}>
        <LinkButton to="/cabinet/companies/new/1">{t("companies.create")}</LinkButton>
      </ErrorView>
    );
  }

  const companyName =
    activeCompany.legal_name ?? activeCompany.short_name ?? activeCompany.tax_id;

  // Publishing needs a verified company; say so before the seven sheets rather
  // than after them.
  if (activeCompany.status !== "verified") {
    return <OffersLocked companyId={activeCompany.id} companyName={companyName} />;
  }

  if (isEdit && offerQuery.isLoading) return <LoadingView label={t("common.loading")} />;
  if (isEdit && offerQuery.isError) {
    return (
      <ErrorView
        title={t("errors.loadFailed")}
        retryLabel={t("common.retry")}
        onRetry={() => void offerQuery.refetch()}
      />
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      <OfferWizard
        companyId={activeCompany.id}
        isEdit={isEdit}
        step={step}
        onStepChange={(next) => navigate(`${base}/${next}`)}
        onExit={() => navigate("/cabinet/offers")}
        onPublished={(offer) =>
          navigate(isEdit ? "/cabinet/offers" : `/cabinet/offers/new/done/${offer.id}`, { replace: true })
        }
        onNotVerified={() =>
          navigate(`/cabinet/companies/${activeCompany.id}/verification`, { replace: true })
        }
      />
    </div>
  );
}
