import { useState } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { useCreateInquiry } from "@/entities/inquiry";
import { LabBadges } from "@/entities/lab";
import {
  BusinessRoleBadges,
  OfferReadinessBadges,
  offerImageUrl,
  offerPhotos,
  useMarketOffer,
} from "@/entities/market";
import { SampleRequestForm } from "@/features/sample-request";
import { cn } from "@/shared/lib";
import {
  Alert,
  Badge,
  BoxIcon,
  Button,
  buttonClasses,
  Card,
  CardBody,
  CardDescription,
  CardHeader,
  CardTitle,
  ClockIcon,
  DownloadIcon,
  FileRow,
  FormField,
  Input,
  LinkButton,
  LoadingView,
  PageHeader,
  ShieldIcon,
  SpecItem,
  SpecList,
  SpecTile,
  StickyActionBar,
  Tabs,
  Textarea,
  type TabItem,
} from "@/shared/ui";

const INQUIRY_STATUS_TONE = {
  pending: "warning",
  approved: "success",
  rejected: "danger",
} as const;

/** The sheet's five tabs minus the two whose data is out of scope (compatibility, reviews). */
const TAB_IDS = ["description", "specs", "documents"] as const;

export function MarketOfferPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { offerId: offerIdParam } = useParams<{ offerId: string }>();
  const offerId = offerIdParam ? Number(offerIdParam) : null;
  const { activeCompany } = useActiveCompany();
  const companyId = activeCompany?.id ?? null;

  const offerQuery = useMarketOffer(offerId, companyId);
  const createInquiry = useCreateInquiry(companyId);

  const [quantity, setQuantity] = useState("");
  const [targetPrice, setTargetPrice] = useState("");
  const [message, setMessage] = useState("");
  const [activePhoto, setActivePhoto] = useState(0);
  const [sampleSent, setSampleSent] = useState(false);
  const [tab, setTab] = useState<(typeof TAB_IDS)[number]>("description");

  if (offerQuery.isLoading) return <LoadingView label={t("common.loading")} />;
  if (offerQuery.isError || !offerQuery.data) {
    return (
      <div className="space-y-4">
        <Alert tone="danger">{t("market.notFound")}</Alert>
        <LinkButton to="/market" variant="secondary">
          {t("market.backToMarket")}
        </LinkButton>
      </div>
    );
  }

  const offer = offerQuery.data;
  const product = offer.product_text ?? offer.grade_text ?? "—";
  const photos = offerPhotos(offer.files);
  const active = photos[activePhoto] ?? photos[0] ?? null;
  const passport = offer.files.find((f) => f.kind === "lab_passport") ?? null;
  const documents = offer.files.filter((f) => f.kind !== "image");
  const grade = offer.product_text && offer.grade_text ? offer.grade_text : null;
  const canInquire = companyId != null && !offer.is_own;

  const tabs: TabItem[] = TAB_IDS.map((id) => ({
    id,
    label: t(`market.tabs.${id}`),
    ...(id === "documents" && documents.length > 0 ? { count: documents.length } : {}),
  }));

  function submit() {
    if (companyId == null || offerId == null) return;
    createInquiry.mutate(
      {
        offerId,
        payload: {
          company_id: companyId,
          quantity: quantity.trim() || null,
          target_price: targetPrice.trim() || null,
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

  return (
    // `pb-36` clears the StickyActionBar on phones — a fixed bar does not extend
    // this box, so without it the last card hides behind the CTA.
    <div className="space-y-5 pb-36 md:pb-0">
      <PageHeader
        backTo="/market"
        backLabel={t("market.backToMarket")}
        title={product}
        subtitle={grade}
        badge={
          <>
            <Badge variant={offer.availability === "in_stock" ? "in-stock" : "on-order"}>
              {t(`availability.${offer.availability}`)}
            </Badge>
            <LabBadges hasLabPassport={offer.has_lab_passport} labVerified={offer.lab_verified} />
          </>
        }
      />

      <div className="grid gap-5 lg:grid-cols-3">
        {/* `min-w-0`: the tab strip scrolls, but a grid item's automatic
            minimum size is its content, so without this the column widens. */}
        <div className="min-w-0 space-y-5 lg:col-span-2">
          <Card>
            <CardBody className="space-y-4">
              {/* The price is the hero figure on the mockup product page. */}
              <div>
                {offer.price == null ? (
                  <p className="text-2xl font-semibold text-text-muted">
                    {t("market.onRequest")}
                  </p>
                ) : (
                  <p className="num text-2xl font-semibold leading-tight text-brand">
                    {offer.price}{" "}
                    <span className="text-base font-medium text-text-muted">
                      {offer.currency}
                      {offer.qty_unit ? `/${offer.qty_unit}` : ""}
                    </span>
                  </p>
                )}
              </div>
              {active ? (
                <div className="space-y-2">
                  {/* Main frame + thumbnail strip (mockup sheet 4). */}
                  <div className="overflow-hidden rounded-md border border-border bg-surface-inset">
                    <img
                      src={offerImageUrl(offer.id, active.id)}
                      alt={active.file_name}
                      className="max-h-96 w-full object-contain"
                    />
                  </div>
                  {photos.length > 1 ? (
                    <div className="flex flex-wrap gap-2">
                      {photos.map((f, index) => (
                        <button
                          key={f.id}
                          type="button"
                          onClick={() => setActivePhoto(index)}
                          aria-label={f.file_name}
                          aria-current={index === activePhoto}
                          className={cn(
                            "h-20 w-20 overflow-hidden rounded-md border transition-colors",
                            index === activePhoto
                              ? "border-brand"
                              : "border-border hover:border-brand-line",
                          )}
                        >
                          <img
                            src={offerImageUrl(offer.id, f.id)}
                            alt=""
                            loading="lazy"
                            className="h-full w-full object-cover"
                          />
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}
              {/* The sheet's fact strip: the four numbers a buyer scans first. */}
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <SpecTile
                  icon={<BoxIcon />}
                  label={t("market.qty")}
                  value={
                    offer.qty_available != null
                      ? `${offer.qty_available} ${offer.qty_unit}`
                      : "—"
                  }
                  numeric
                />
                <SpecTile icon={<ShieldIcon />} label={t("market.incoterms")} value={offer.incoterms} />
                <SpecTile
                  icon={<BoxIcon />}
                  label={t("market.minOrder")}
                  value={
                    offer.min_order_qty != null
                      ? `${offer.min_order_qty} ${offer.qty_unit}`
                      : "—"
                  }
                  numeric
                />
                <SpecTile
                  icon={<ClockIcon />}
                  label={t("market.leadTimeShort")}
                  value={offer.lead_time_days != null ? String(offer.lead_time_days) : "—"}
                  numeric
                />
              </div>
            </CardBody>
          </Card>

          {/* Sheet …42 splits the long tail into tabs rather than one long scroll. */}
          <Card>
            <CardBody className="space-y-4">
              <Tabs items={tabs} value={tab} onChange={(id) => setTab(id as typeof tab)} label={product} />

              {tab === "description" ? (
                offer.description ? (
                  <p className="whitespace-pre-line text-sm text-text">{offer.description}</p>
                ) : (
                  <p className="text-sm text-text-muted">{t("market.noDescription")}</p>
                )
              ) : null}

              {tab === "specs" ? (
                <SpecList>
                  <SpecItem label={t("market.country")} value={offer.country ?? "—"} />
                  <SpecItem label={t("market.warehouse")} value={offer.warehouse_city ?? "—"} />
                  <SpecItem label={t("market.incoterms")} value={offer.incoterms} />
                  <SpecItem
                    label={t("market.qty")}
                    value={
                      offer.qty_available != null
                        ? `${offer.qty_available} ${offer.qty_unit}`
                        : "—"
                    }
                    numeric
                  />
                  <SpecItem
                    label={t("market.minOrder")}
                    value={
                      offer.min_order_qty != null
                        ? `${offer.min_order_qty} ${offer.qty_unit}`
                        : "—"
                    }
                    numeric
                  />
                  {offer.lead_time_days != null ? (
                    <SpecItem
                      label={t("market.leadTimeShort")}
                      value={t("market.leadTime", { count: offer.lead_time_days })}
                      numeric
                    />
                  ) : null}
                </SpecList>
              ) : null}

              {/* The laboratory claim, with the document behind it. A badge a
                  buyer cannot open is a badge they have to take on trust. */}
              {tab === "documents" ? (
                documents.length > 0 ? (
                  <div className="space-y-2">
                    {documents.map((file) => (
                      <FileRow
                        key={file.id}
                        name={file.file_name}
                        meta={t(`documentKind.${file.kind}`, { defaultValue: file.kind })}
                        status={
                          file.id === passport?.id ? (
                            <Badge variant="lab-verified">{t("lab.badge.passport")}</Badge>
                          ) : undefined
                        }
                        actions={
                          <a
                            href={offerImageUrl(offer.id, file.id)}
                            target="_blank"
                            rel="noreferrer"
                            aria-label={t("common.download")}
                            className="rounded-sm p-1.5 text-text-muted transition-colors hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                          >
                            <DownloadIcon size={16} />
                          </a>
                        }
                      />
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-text-muted">{t("market.noDocuments")}</p>
                )
              ) : null}
            </CardBody>
          </Card>

          {/* Samples: only offered when the seller said so, and never to
              themselves — the API refuses both, this just does not ask. */}
          {offer.samples_available && !offer.is_own ? (
            <Card id="samples">
              <CardHeader>
                <CardTitle>{t("samples.offerTitle")}</CardTitle>
                <CardDescription>
                  {offer.sample_price == null
                    ? t("samples.free")
                    : t("samples.priced", {
                        price: offer.sample_price,
                        currency: offer.currency,
                      })}
                  {offer.sample_dispatch_days != null
                    ? ` · ${t("samples.dispatch", { count: offer.sample_dispatch_days })}`
                    : ""}
                </CardDescription>
              </CardHeader>
              <CardBody>
                {!activeCompany ? (
                  <Alert tone="info">{t("home.noActiveCompany")}</Alert>
                ) : sampleSent ? (
                  <Alert tone="success">{t("samples.sentOk")}</Alert>
                ) : (
                  <SampleRequestForm
                    offerId={offer.id}
                    companyId={activeCompany.id}
                    onSent={() => setSampleSent(true)}
                  />
                )}
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
                    onClick={() => navigate(`/inquiries/${inq.id}`)}
                    className="flex w-full items-center justify-between rounded-md border border-border px-3 py-2 text-left text-sm hover:border-brand"
                  >
                    <span className="text-text-muted">
                      {inq.message ?? `#${inq.id}`}
                    </span>
                    <Badge tone={INQUIRY_STATUS_TONE[inq.status]}>
                      {t(`inquiryStatus.${inq.status}`)}
                    </Badge>
                  </button>
                ))}
              </CardBody>
            </Card>
          ) : null}
        </div>

        <div className="min-w-0 space-y-4">
          <Card>
            <CardHeader
              icon={<ShieldIcon size={16} />}
              action={
                offer.company_verified ? (
                  <Badge variant="verified">{t("market.verified")}</Badge>
                ) : undefined
              }
            >
              <CardTitle>{t("market.seller")}</CardTitle>
            </CardHeader>
            <CardBody className="space-y-2 text-sm">
              <div className="font-medium text-text">{offer.display_name ?? "—"}</div>
              {offer.company_verified ? null : (
                <span className="text-text-muted">{t("market.notVerified")}</span>
              )}
              {/* No `max` here: the detail page has room, and a buyer choosing a
                  counterparty wants the whole picture. */}
              <BusinessRoleBadges roles={offer.business_roles} />
              <OfferReadinessBadges offer={offer} />
              {offer.lead_time_days != null ? (
                <p className="num text-text-muted">
                  {t("market.leadTime", { count: offer.lead_time_days })}
                </p>
              ) : null}
            </CardBody>
          </Card>

          <Card id="inquiry">
            <CardHeader>
              <CardTitle>{t("market.sendInquiry")}</CardTitle>
            </CardHeader>
            <CardBody className="space-y-3">
              {offer.is_own ? (
                <Alert tone="info">{t("market.ownOffer")}</Alert>
              ) : companyId == null ? (
                <Alert tone="warning">{t("market.selectCompanyHint")}</Alert>
              ) : (
                <>
                  {createInquiry.isSuccess ? (
                    <Alert tone="success">{t("market.inquirySent")}</Alert>
                  ) : null}
                  {createInquiry.isError ? (
                    <Alert tone="danger">{t("market.inquiryFailed")}</Alert>
                  ) : null}
                  <FormField label={t("market.quantity")}>
                    {({ id }) => (
                      <Input
                        id={id}
                        inputMode="decimal"
                        value={quantity}
                        onChange={(e) => setQuantity(e.target.value)}
                        placeholder={offer.qty_unit}
                      />
                    )}
                  </FormField>
                  <FormField label={t("market.targetPrice")}>
                    {({ id }) => (
                      <Input
                        id={id}
                        inputMode="decimal"
                        value={targetPrice}
                        onChange={(e) => setTargetPrice(e.target.value)}
                        placeholder={offer.currency}
                      />
                    )}
                  </FormField>
                  <FormField label={t("market.message")}>
                    {({ id }) => (
                      <Textarea
                        id={id}
                        rows={3}
                        value={message}
                        onChange={(e) => setMessage(e.target.value)}
                      />
                    )}
                  </FormField>
                  <Button
                    fullWidth
                    disabled={!canInquire || createInquiry.isPending || (!quantity.trim() && !message.trim())}
                    onClick={submit}
                  >
                    {createInquiry.isPending ? t("common.saving") : t("market.sendInquiry")}
                  </Button>
                </>
              )}
            </CardBody>
          </Card>
        </div>
      </div>

      {/*
       * The sheet pins the primary actions to the bottom of the phone screen.
       * Only on phones: at md+ the inquiry form is already in the right rail, so
       * a second copy of its CTA would be noise rather than reach.
       */}
      {canInquire ? (
        <StickyActionBar className="md:hidden">
          <a
            href="#inquiry"
            className={buttonClasses({ variant: "outline", fullWidth: true })}
          >
            {t("market.sendInquiry")}
          </a>
          {offer.samples_available && !sampleSent ? (
            <a href="#samples" className={buttonClasses({ fullWidth: true })}>
              {t("samples.send")}
            </a>
          ) : null}
        </StickyActionBar>
      ) : null}
    </div>
  );
}
