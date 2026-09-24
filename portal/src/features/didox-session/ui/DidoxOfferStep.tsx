import { useEffect, useState } from "react";

import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { didoxApi } from "@/entities/edi";
import { detailCode } from "@/shared/api";
import {
  Alert,
  Button,
  Card,
  CardBody,
  CardDescription,
  CardHeader,
  CardTitle,
  Checkbox,
  Spinner,
} from "@/shared/ui";

import { useDidoxOffer } from "../model/useDidoxOffer";
import { useDidoxSession } from "../model/useDidoxSession";

interface DidoxOfferStepProps {
  companyId: number;
  taxId: string;
}

/**
 * Step 2 — read Didox's public offer, then sign it.
 *
 * The text is the PDF Didox publishes, shown here in full; the signature goes
 * on the document Didox builds around it, which is what `useDidoxOffer` fetches.
 * Signing stays disabled until the owner says they have read it.
 *
 * The PDF needs a Didox session. It is NOT minted automatically on arrival — an
 * E-IMZO password prompt nobody asked for is worse than one button.
 */
export function DidoxOfferStep({ companyId, taxId }: DidoxOfferStepProps) {
  const { t } = useTranslation();
  const session = useDidoxSession(companyId, taxId);
  const offer = useDidoxOffer(companyId, taxId);
  const [agreed, setAgreed] = useState(false);
  const [url, setUrl] = useState<string | null>(null);

  const pdf = useQuery({
    queryKey: ["didox", "offer-pdf", companyId],
    queryFn: () => didoxApi.offerPdf(companyId),
    retry: false,
    staleTime: Infinity,
  });

  useEffect(() => {
    if (!pdf.data) return undefined;
    const objectUrl = URL.createObjectURL(pdf.data);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [pdf.data]);

  const needsSession =
    pdf.isError && detailCode(pdf.error) === "didox_session_required";

  return (
    <Card data-testid="didox-offer-step">
      <CardHeader>
        <CardTitle>{t("didoxOnboarding.offer.title")}</CardTitle>
        <CardDescription>{t("didoxOnboarding.offer.body")}</CardDescription>
      </CardHeader>
      <CardBody className="space-y-4">
        {pdf.isLoading && (
          <div className="flex items-center gap-2 text-sm text-text-muted">
            <Spinner /> {t("didoxOnboarding.offer.loading")}
          </div>
        )}

        {needsSession && (
          <div className="space-y-2">
            <p className="text-sm text-text-muted">
              {t("didoxOnboarding.offer.sessionHint")}
            </p>
            <Button
              type="button"
              variant="secondary"
              disabled={session.minting}
              onClick={() =>
                void session.open().then((opened) => {
                  if (opened) void pdf.refetch();
                })
              }
              data-testid="didox-offer-sign-in"
            >
              {session.minting ? t("didox.connecting") : t("ikpu.session.open")}
            </Button>
            {session.error && (
              <p className="text-sm text-danger">
                {t(`didox.errors.${session.error}`, {
                  message: session.errorMessage ?? "",
                })}
              </p>
            )}
          </div>
        )}

        {pdf.isError && !needsSession && (
          <Alert tone="danger" title={t("didoxOnboarding.offer.loadFailed")}>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => void pdf.refetch()}
            >
              {t("common.retry")}
            </Button>
          </Alert>
        )}

        {url && (
          <>
            <iframe
              src={url}
              title={t("didoxOnboarding.offer.title")}
              className="h-[70vh] w-full rounded-md border border-border"
              data-testid="didox-offer-pdf"
            />
            <a
              href={url}
              target="_blank"
              rel="noopener"
              className="text-sm text-brand underline"
            >
              {t("didoxOnboarding.offer.openInTab")}
            </a>
            <Checkbox
              id="didox-offer-agree"
              label={t("didoxOnboarding.offer.agree")}
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
              data-testid="didox-offer-agree"
            />
            <Button
              type="button"
              disabled={!agreed || offer.signing}
              onClick={() => void offer.sign()}
              data-testid="didox-sign-offer"
            >
              {offer.signing ? t("didox.signingOffer") : t("didox.signOffer")}
            </Button>
          </>
        )}

        {offer.error && (
          <p className="text-sm text-danger" data-testid="didox-offer-error">
            {t(`didoxOnboarding.offer.errors.${offer.error}`)}
          </p>
        )}
      </CardBody>
    </Card>
  );
}
