import { useEffect, useState } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { useCreateInquiry } from "@/entities/inquiry";
import {
  offerImageUrl,
  offerPhotos,
  useMarketOffer,
  useToggleFavorite,
} from "@/entities/market";
import {
  OfferActionBar,
  OfferDescriptionBlocks,
  OfferHero,
} from "@/features/product-detail";
import { coerceLang } from "@/shared/i18n";
import { countryName } from "@/shared/lib";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  ChevronLeftIcon,
  FormField,
  HeartIcon,
  IconButton,
  Input,
  LinkButton,
  LoadingView,
  ShareIcon,
  SpecItem,
  SpecList,
  Tabs,
  Textarea,
  type TabItem,
} from "@/shared/ui";

const INQUIRY_STATUS_TONE = {
  pending: "warning",
  approved: "success",
  rejected: "danger",
} as const;

const TAB_IDS = ["description", "specs", "documents", "compatibility", "reviews"] as const;

/**
 * True when a filled-in field cannot survive the wire.
 *
 * `quantity`/`target_price` land in `Decimal … gt=0` (`OfferRequestCreate`), so
 * "500 тонн" or "0" comes back a 422 the buyer can only read as a generic
 * failure. Empty is fine — it is sent as null. Same rule as the offer wizard's
 * positive-number check (`features/offer-wizard/model/validation.ts`).
 */
function notPositiveNumber(value: string): boolean {
  const trimmed = value.trim();
  if (trimmed === "") return false;
  const parsed = Number(trimmed);
  return !Number.isFinite(parsed) || parsed <= 0;
}

/**
 * Product detail — `docs/new-design/product_detail.jpeg`.
 *
 * One long sheet: hero (gallery + RFQ + favourite), gold-underline tabs, then
 * the description blocks (facts / availability / samples / lab / seller /
 * compatibility / documents). Specs and documents also have dedicated tabs;
 * compatibility and reviews are present as chrome so the rail matches the
 * mockup even while those surfaces are still empty.
 */
export function MarketOfferPage() {
  const { t, i18n } = useTranslation();
  const lang = coerceLang(i18n.language);
  const navigate = useNavigate();
  const { offerId: offerIdParam } = useParams<{ offerId: string }>();
  const offerId = offerIdParam ? Number(offerIdParam) : null;
  const { activeCompany } = useActiveCompany();
  const companyId = activeCompany?.id ?? null;
  const [searchParams] = useSearchParams();
  // Arrived from the manufacturers directory — swap the trader inquiry door for
  // a direct chat + factory RFQ (`docs/new-design/manufacturer_flow.jpeg`).
  const fromManufacturer = searchParams.get("fromManufacturer") === "1";

  const offerQuery = useMarketOffer(offerId, companyId);
  const createInquiry = useCreateInquiry(companyId);
  const toggleFavorite = useToggleFavorite();

  const [quantity, setQuantity] = useState("");
  const [targetPrice, setTargetPrice] = useState("");
  const [message, setMessage] = useState("");
  const [sampleSent, setSampleSent] = useState(false);
  const [shareNote, setShareNote] = useState<string | null>(null);
  const [tab, setTab] = useState<(typeof TAB_IDS)[number]>("description");

  // «Написать» from the seller profile returns with #inquiry — land on the form.
  useEffect(() => {
    if (window.location.hash === "#inquiry" && offerQuery.data) {
      window.setTimeout(() => {
        document.getElementById("inquiry")?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 80);
    }
  }, [offerQuery.data]);

  if (offerQuery.isLoading) return <LoadingView label={t("common.loading")} />;
  if (offerQuery.isError || !offerQuery.data) {
    return (
      <div className="space-y-4">
        <Alert tone="danger">{t("market.notFound")}</Alert>
        <LinkButton to="/cabinet/market" variant="secondary">
          {t("market.backToMarket")}
        </LinkButton>
      </div>
    );
  }

  const offer = offerQuery.data;
  const photos = offerPhotos(offer.files);
  // A lab passport only — a COA is a different document. Accepting one here made
  // the block say «паспорт отсутствует» next to a Download button.
  const passport = offer.files.find((f) => f.kind === "lab_passport") ?? null;
  const documents = offer.files.filter((f) => f.kind !== "image");
  const canInquire = companyId != null && !offer.is_own;
  const canSendRfq = canInquire && offer.accepts_rfq;
  const title = offer.product_text ?? offer.grade_text ?? "—";

  // Both sides must be verified or POST /portal/contracts answers 422, and a TG-origin
  // offer has no company to sign with at all. Say which of those it is, on the page,
  // rather than letting the buyer discover it two screens later.
  const contractBlockedReason = !offer.accepts_contract
    ? t("market.detail.contractNotOffered")
    : offer.seller_company_id == null || !offer.company_verified
      ? t("market.detail.contractNeedsVerifiedSeller")
      : activeCompany?.status !== "verified"
        ? t("market.detail.contractNeedsVerifiedCompany")
        : null;

  const tabs: TabItem[] = TAB_IDS.map((id) => ({
    id,
    label: t(`market.tabs.${id}`),
    ...(id === "documents" && documents.length > 0 ? { count: documents.length } : {}),
  }));

  const quantityError = notPositiveNumber(quantity) ? t("market.quantityInvalid") : null;
  const targetPriceError = notPositiveNumber(targetPrice) ? t("market.targetPriceInvalid") : null;
  const inquiryError =
    createInquiry.error?.code === "network" || createInquiry.error?.status === 0
      ? t("common.network")
      : createInquiry.error?.status === 429
        ? t("market.inquiryRateLimited")
        : createInquiry.error?.code === "rfq_not_accepted"
          ? t("market.detail.rfqNotAccepted")
          : createInquiry.error?.status === 400 && createInquiry.error.message
            ? createInquiry.error.message
            : createInquiry.isError
              ? t("market.inquiryFailed")
              : null;

  function scrollTo(id: string): void {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function submitInquiry(): void {
    if (companyId == null || offerId == null) return;
    createInquiry.mutate(
      {
        offerId,
        payload: {
          company_id: companyId,
          quantity: quantity.trim() || null,
          // The offer's own unit and currency, or the server records its defaults
          // (MT / none) and staff read "500" against a KG listing as 500 tonnes.
          qty_unit: offer.qty_unit,
          target_price: targetPrice.trim() || null,
          currency: offer.currency,
          message: message.trim() || null,
        },
      },
      {
        onSuccess: () => {
          setQuantity("");
          setTargetPrice("");
          setMessage("");
        },
      },
    );
  }

  /** Clear a stale success/error banner as soon as the buyer starts a new inquiry. */
  function edit(setter: (value: string) => void): (value: string) => void {
    return (value) => {
      if (createInquiry.isSuccess || createInquiry.isError) createInquiry.reset();
      setter(value);
    };
  }

  async function share(): Promise<void> {
    const url = window.location.href;
    try {
      if (navigator.share) {
        await navigator.share({ title, url });
        return;
      }
      await navigator.clipboard.writeText(url);
      setShareNote(t("market.detail.linkCopied"));
      window.setTimeout(() => setShareNote(null), 2500);
    } catch {
      /* user cancelled share sheet — nothing to report */
    }
  }

  return (
    <div className="space-y-5 pb-36 md:pb-0" data-testid="product-detail">
      <header className="flex items-center gap-2">
        <IconButton label={t("market.backToMarket")} onClick={() => navigate("/cabinet/market")}>
          <ChevronLeftIcon size={20} />
        </IconButton>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-text">{title}</p>
          <p className="truncate text-xs text-text-muted">{t("market.detail.marketplace")}</p>
        </div>
        <IconButton
          label={t(offer.is_favorite ? "market.unfavorite" : "market.favorite")}
          onClick={() => toggleFavorite.mutate({ offerId: offer.id, next: !offer.is_favorite })}
        >
          <HeartIcon
            size={18}
            className={offer.is_favorite ? "fill-current text-danger" : undefined}
          />
        </IconButton>
        <IconButton label={t("market.detail.share")} onClick={() => void share()}>
          <ShareIcon size={18} />
        </IconButton>
      </header>

      {shareNote ? <Alert tone="success">{shareNote}</Alert> : null}

      <OfferHero
        offer={offer}
        photos={photos}
        canInquire={canInquire}
        onRequestRfq={() => {
          if (fromManufacturer && offer.seller_company_id != null) {
            void navigate(`/cabinet/manufacturers/${offer.seller_company_id}/rfq/${offer.id}`);
            return;
          }
          setTab("description");
          window.setTimeout(() => scrollTo("inquiry"), 50);
        }}
        onToggleFavorite={() =>
          toggleFavorite.mutate({ offerId: offer.id, next: !offer.is_favorite })
        }
      />

      <Tabs
        items={tabs}
        value={tab}
        onChange={(id) => setTab(id as typeof tab)}
        variant="underlineGold"
        label={title}
      />

      {tab === "description" ? (
        <OfferDescriptionBlocks
          offer={offer}
          documents={documents}
          passport={passport}
          companyId={companyId}
          sampleSent={sampleSent}
          onSampleSent={() => setSampleSent(true)}
          onRequestSample={() => scrollTo("samples")}
        />
      ) : null}

      {tab === "specs" ? (
        <Card>
          <CardBody>
            <SpecList>
              <SpecItem
                label={t("market.detail.manufacturer")}
                value={offer.manufacturer?.trim() || "—"}
              />
              <SpecItem label={t("market.detail.cas")} value={offer.cas_number?.trim() || "—"} />
              <SpecItem label={t("market.detail.hs")} value={offer.hs_code?.trim() || "—"} />
              <SpecItem
                label={t("market.detail.country")}
                value={offer.country ? countryName(offer.country, lang) : "—"}
              />
              <SpecItem label={t("market.warehouse")} value={offer.warehouse_city ?? "—"} />
              <SpecItem label={t("market.incoterms")} value={offer.incoterms} />
              {offer.lead_time_days != null ? (
                <SpecItem
                  label={t("market.leadTimeShort")}
                  value={t("market.leadTime", { count: offer.lead_time_days })}
                  numeric
                />
              ) : null}
            </SpecList>
            {(offer.key_properties?.length ?? 0) > 0 ? (
              <div className="mt-4">
                <p className="mb-2 text-sm font-medium text-text">
                  {t("market.detail.keyProperties")}
                </p>
                <ul className="flex flex-wrap gap-2">
                  {(offer.key_properties ?? []).map((chip) => (
                    <li key={chip}>
                      <Badge tone="neutral">{chip}</Badge>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {(offer.applications?.length ?? 0) > 0 ? (
              <div className="mt-4">
                <p className="mb-2 text-sm font-medium text-text">
                  {t("market.detail.applications")}
                </p>
                <ul className="flex flex-wrap gap-2">
                  {(offer.applications ?? []).map((chip) => (
                    <li key={chip}>
                      <Badge tone="neutral">{chip}</Badge>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </CardBody>
        </Card>
      ) : null}

      {tab === "documents" ? (
        <Card>
          <CardBody>
            {documents.length > 0 ? (
              <ul className="space-y-2">
                {documents.map((file) => (
                  <li key={file.id}>
                    <a
                      href={offerImageUrl(offer.id, file.id)}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center justify-between rounded-md border border-border px-3 py-2.5 text-sm hover:border-brand-line"
                    >
                      <span className="min-w-0 truncate text-text">{file.file_name}</span>
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
      ) : null}

      {tab === "compatibility" ? (
        <Card className="border-info/40">
          <CardBody className="space-y-2">
            <p className="text-sm font-medium text-text">{t("market.detail.compatibility")}</p>
            <p className="text-sm text-text-muted">{t("market.detail.compatibilityBody")}</p>
            <p className="text-xs text-text-subtle">{t("market.detail.comingSoon")}</p>
          </CardBody>
        </Card>
      ) : null}

      {tab === "reviews" ? (
        <Card>
          <CardBody>
            <p className="text-sm text-text-muted">{t("market.detail.reviewsEmpty")}</p>
          </CardBody>
        </Card>
      ) : null}

      {offer.my_inquiries.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>{t("market.myInquiries")}</CardTitle>
          </CardHeader>
          <CardBody className="space-y-2">
            {offer.my_inquiries.map((inq) => (
              <button
                key={inq.id}
                type="button"
                onClick={() => navigate(`/cabinet/inquiries/${inq.id}`)}
                className="flex w-full items-center justify-between rounded-md border border-border px-3 py-2 text-left text-sm hover:border-brand"
              >
                <span className="text-text-muted">{inq.message ?? `#${inq.id}`}</span>
                <Badge tone={INQUIRY_STATUS_TONE[inq.status]}>
                  {t(`inquiryStatus.${inq.status}`)}
                </Badge>
              </button>
            ))}
          </CardBody>
        </Card>
      ) : null}

      <Card id="inquiry">
        <CardHeader>
          <CardTitle>{t("market.detail.requestRfq")}</CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          {offer.is_own ? (
            <Alert tone="info">{t("market.ownOffer")}</Alert>
          ) : companyId == null ? (
            <Alert tone="warning">{t("market.selectCompanyHint")}</Alert>
          ) : !offer.accepts_rfq ? (
            // The server refuses this too (422 `rfq_not_accepted`). Greying only the
            // hero button while leaving a working form below it meant a seller's
            // opt-out held in one place on the page and not in the other.
            <Alert tone="info">{t("market.detail.rfqNotAccepted")}</Alert>
          ) : (
            <>
              {createInquiry.isSuccess ? (
                <Alert tone="success">{t("market.inquirySent")}</Alert>
              ) : null}
              {inquiryError ? <Alert tone="danger">{inquiryError}</Alert> : null}
              <FormField label={t("market.quantity")} error={quantityError}>
                {({ id, describedBy }) => (
                  <Input
                    id={id}
                    inputMode="decimal"
                    value={quantity}
                    onChange={(e) => edit(setQuantity)(e.target.value)}
                    placeholder={offer.qty_unit}
                    aria-describedby={describedBy}
                  />
                )}
              </FormField>
              <FormField label={t("market.targetPrice")} error={targetPriceError}>
                {({ id, describedBy }) => (
                  <Input
                    id={id}
                    inputMode="decimal"
                    value={targetPrice}
                    onChange={(e) => edit(setTargetPrice)(e.target.value)}
                    placeholder={offer.currency}
                    aria-describedby={describedBy}
                  />
                )}
              </FormField>
              <FormField label={t("market.message")}>
                {({ id }) => (
                  <Textarea
                    id={id}
                    rows={3}
                    value={message}
                    onChange={(e) => edit(setMessage)(e.target.value)}
                  />
                )}
              </FormField>
              <Button
                fullWidth
                disabled={
                  !canSendRfq ||
                  createInquiry.isPending ||
                  quantityError != null ||
                  targetPriceError != null ||
                  (!quantity.trim() && !message.trim())
                }
                onClick={submitInquiry}
                data-testid="inquiry-submit"
              >
                {createInquiry.isPending ? t("common.saving") : t("market.sendInquiry")}
              </Button>
            </>
          )}
        </CardBody>
      </Card>

      <OfferActionBar
        canAct={canInquire}
        acceptsRfq={offer.accepts_rfq}
        acceptsEscrow={offer.accepts_escrow}
        contractBlockedReason={contractBlockedReason}
        onMessage={() => {
          if (fromManufacturer && offer.seller_company_id != null) {
            void navigate(`/cabinet/manufacturers/${offer.seller_company_id}/chat`);
            return;
          }
          scrollTo("inquiry");
        }}
        onContract={() =>
          navigate(
            `/cabinet/contracts/new?offerId=${offer.id}&counterpartyId=${offer.seller_company_id}`,
          )
        }
      />
    </div>
  );
}
