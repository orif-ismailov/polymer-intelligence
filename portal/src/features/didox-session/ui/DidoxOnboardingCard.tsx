import { useState } from "react";

import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { didoxApi } from "@/entities/edi";
import { getEimzoBridge } from "@/shared/lib/eimzo";
import { Badge, Button } from "@/shared/ui";

import { useDidoxSession } from "../model/useDidoxSession";

interface DidoxOnboardingCardProps {
  companyId: number;
  taxId: string;
}

/**
 * Where this company stands with Didox — a card on the company page.
 *
 * Deliberately NOT a step in the registration wizard. Those five steps are pinned
 * to a mockup, run before verification, and a company registering by hand may not
 * have an E-IMZO key at that moment; gating registration on an EDI operator's
 * public offer would block the common path on an optional feature.
 *
 * On `disabled` this renders **nothing at all**. That state is a property of the
 * deployment, not of the company, and announcing a feature nobody enabled is
 * noise — the same rule the registry-prefill notice follows.
 */
export function DidoxOnboardingCard({ companyId, taxId }: DidoxOnboardingCardProps) {
  const { t } = useTranslation();
  const { minting, error, open, withSession } = useDidoxSession(companyId, taxId);
  const [signingOffer, setSigningOffer] = useState(false);
  const [offerError, setOfferError] = useState<string | null>(null);

  /**
   * Sign Didox's public offer — the one-time step that unblocks every send.
   *
   * The bytes come from the server (it does the two round trips their docs
   * describe) and arrive ALREADY base64, so they go through `signBase64`:
   * decoding just to let `sign()` re-encode corrupts every non-ASCII character,
   * and this document is full of them.
   */
  async function signOffer(): Promise<void> {
    setSigningOffer(true);
    setOfferError(null);
    try {
      const bridge = getEimzoBridge();
      if (!(await bridge.probe())) throw new Error("module_missing");
      const certs = await bridge.listCertificates();
      const cert = certs.find((c) => c.tin === taxId);
      if (!cert) throw new Error("cert_mismatch");

      const dataB64 = await withSession(() => didoxApi.offerToSign(companyId));
      const signature = bridge.signBase64
        ? await bridge.signBase64(cert.id, dataB64)
        : await bridge.sign(cert.id, dataB64);
      await withSession(() => didoxApi.acceptOffer(companyId, signature));
      await query.refetch();
    } catch (err) {
      setOfferError(err instanceof Error ? err.message : "failed");
    } finally {
      setSigningOffer(false);
    }
  }

  const query = useQuery({
    queryKey: ["didox", "status", companyId],
    queryFn: () => didoxApi.status(companyId),
  });

  const status = query.data;
  if (!status || status.state === "disabled") return null;

  // `variant` is for the mockups' named badges; anything outside that set uses a
  // plain tone, which is what these three states are.
  const tone =
    status.state === "ready" ? "success" : status.state === "offer_unsigned" ? "warning" : "neutral";

  return (
    <section className="rounded-lg border border-border p-4" data-testid="didox-card">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-base font-medium">{t("didox.title")}</h3>
        <Badge tone={tone} data-testid="didox-state">
          {t(`didox.states.${status.state}`)}
        </Badge>
      </div>

      <p className="mt-2 text-sm text-text-muted">{t(`didox.hints.${status.state}`)}</p>

      <div className="mt-3 flex flex-wrap gap-2">
        {status.state !== "ready" && (
          <Button
            type="button"
            variant="secondary"
            disabled={minting}
            onClick={() => void open().then(() => query.refetch())}
            data-testid="didox-connect"
          >
            {minting ? t("didox.connecting") : t("didox.connect")}
          </Button>
        )}

        {/* The offer is what stands between this company and sending anything —
            and until now the backend had the route while the card had no button. */}
        {status.state === "offer_unsigned" && (
          <Button
            type="button"
            disabled={signingOffer}
            onClick={() => void signOffer()}
            data-testid="didox-sign-offer"
          >
            {signingOffer ? t("didox.signingOffer") : t("didox.signOffer")}
          </Button>
        )}
      </div>

      {offerError && (
        <p className="mt-2 text-sm text-danger" data-testid="didox-offer-error">
          {t(`didox.errors.${offerError}`, { defaultValue: t("didox.errors.failed") })}
        </p>
      )}

      {status.state === "ready" && !status.has_session && (
        <p className="mt-2 text-xs text-text-muted" data-testid="didox-no-session">
          {t("didox.sessionExpired")}
        </p>
      )}

      {error && (
        <p className="mt-2 text-sm text-danger" data-testid="didox-error">
          {t(`didox.errors.${error}`)}
        </p>
      )}
    </section>
  );
}
