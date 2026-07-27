import { useState } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { useCreateInquiry } from "@/entities/inquiry";
import {
  BusinessRoleBadges,
  OfferReadinessBadges,
  offerImageUrl,
  offerPhotos,
  useMarketOffer,
} from "@/entities/market";
import { cn } from "@/shared/lib";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardDescription,
  CardHeader,
  CardTitle,
  FormField,
  Input,
  LinkButton,
  LoadingView,
  Textarea,
} from "@/shared/ui";

const INQUIRY_STATUS_TONE = {
  pending: "warning",
  approved: "success",
  rejected: "danger",
} as const;

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
  const grade = offer.product_text && offer.grade_text ? offer.grade_text : null;
  const canInquire = companyId != null && !offer.is_own;

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
    <div className="space-y-6">
      <LinkButton to="/market" variant="ghost" className="text-sm">
        ← {t("market.backToMarket")}
      </LinkButton>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <CardTitle>{product}</CardTitle>
                {grade ? <CardDescription>{grade}</CardDescription> : null}
              </div>
              <Badge variant={offer.availability === "in_stock" ? "in-stock" : "on-order"}>
                {t(`availability.${offer.availability}`)}
              </Badge>
            </CardHeader>
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
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <Spec
                  label={t("market.qty")}
                  value={offer.qty_available != null ? `${offer.qty_available} ${offer.qty_unit}` : "—"}
                />
                <Spec label={t("market.incoterms")} value={offer.incoterms} />
                <Spec label={t("market.country")} value={offer.country ?? "—"} />
                <Spec label={t("market.warehouse")} value={offer.warehouse_city ?? "—"} />
                <Spec
                  label={t("market.minOrder")}
                  value={offer.min_order_qty != null ? `${offer.min_order_qty} ${offer.qty_unit}` : "—"}
                />
              </dl>
              {offer.description ? (
                <p className="whitespace-pre-line text-sm text-text-muted">{offer.description}</p>
              ) : null}
            </CardBody>
          </Card>

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

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>{t("market.seller")}</CardTitle>
            </CardHeader>
            <CardBody className="space-y-2 text-sm">
              <div className="font-medium text-text">{offer.display_name ?? "—"}</div>
              {offer.company_verified ? (
                <Badge variant="verified">{t("market.verified")}</Badge>
              ) : (
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

          <Card>
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
    </div>
  );
}

function Spec({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-text-muted">{label}</dt>
      <dd className="font-medium text-text">{value}</dd>
    </div>
  );
}
