import { useTranslation } from "react-i18next";

import { useDidoxStatus } from "@/entities/edi";
import { Badge, LinkButton } from "@/shared/ui";

interface DidoxOnboardingCardProps {
  companyId: number;
}

/**
 * Where this company stands with Didox — a card on the company page.
 *
 * It reports; the steps themselves live on `/cabinet/didox`, the screen a
 * verified company's owner is taken to on entering the cabinet. One place to
 * register, read the offer and sign it, rather than a second copy of the same
 * buttons here.
 *
 * On `disabled` this renders **nothing at all**. That state is a property of the
 * deployment, not of the company, and announcing a feature nobody enabled is
 * noise — the same rule the registry-prefill notice follows.
 */
export function DidoxOnboardingCard({ companyId }: DidoxOnboardingCardProps) {
  const { t } = useTranslation();
  const query = useDidoxStatus(companyId);

  const status = query.data;
  if (!status || status.state === "disabled") return null;

  // `variant` is for the mockups' named badges; anything outside that set uses a
  // plain tone, which is what these three states are.
  const tone =
    status.state === "ready"
      ? "success"
      : status.state === "offer_unsigned"
        ? "warning"
        : "neutral";

  return (
    <section
      className="rounded-lg border border-border p-4"
      data-testid="didox-card"
    >
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-base font-medium">{t("didox.title")}</h3>
        <Badge tone={tone} data-testid="didox-state">
          {t(`didox.states.${status.state}`)}
        </Badge>
      </div>

      <p className="mt-2 text-sm text-text-muted">
        {t(`didox.hints.${status.state}`)}
      </p>

      {status.state !== "ready" &&
        (status.can_onboard ? (
          <div className="mt-3">
            <LinkButton
              to="/cabinet/didox"
              variant="secondary"
              data-testid="didox-connect"
            >
              {t("didox.connect")}
            </LinkButton>
          </div>
        ) : (
          <p
            className="mt-2 text-xs text-text-muted"
            data-testid="didox-owner-only"
          >
            {t("didox.ownerOnly")}
          </p>
        ))}

      {status.state === "ready" && !status.has_session && (
        <p
          className="mt-2 text-xs text-text-muted"
          data-testid="didox-no-session"
        >
          {t("didox.sessionExpired")}
        </p>
      )}
    </section>
  );
}
