import { useState } from "react";

import { useTranslation } from "react-i18next";

import { useAuthStore, selectIsAuthenticated } from "@/entities/account";
import { useActiveCompany } from "@/entities/company";
import { useCompanyTechRequests, useInviteTechnologist } from "@/entities/tech-request";
import { Alert, Button, LinkButton, Select } from "@/shared/ui";

/**
 * «Пригласить к заявке» on an expert's public page.
 *
 * A session surface on a server-rendered page, so it renders NOTHING until the
 * client knows who is looking (the storefront rule: the server render never
 * varies by visitor). Anonymous → through the login and back to this page; an
 * expert account → nothing (experts do not hire experts); a factory with no
 * open request → a link to post one.
 */
export function InviteToRequest({ profileId, selfHref }: { profileId: number; selfHref: string }) {
  const { t } = useTranslation();
  const isAuthenticated = useAuthStore(selectIsAuthenticated);
  const account = useAuthStore((s) => s.account);
  const isCompanyAccount = isAuthenticated && account?.applied_as !== "technologist";
  const { activeCompanyId } = useActiveCompany(isCompanyAccount);
  const requests = useCompanyTechRequests(isCompanyAccount ? activeCompanyId : null);
  const invite = useInviteTechnologist(activeCompanyId);
  const [picked, setPicked] = useState("");
  const [sentTo, setSentTo] = useState<string | null>(null);

  if (!isAuthenticated) {
    return (
      <LinkButton size="lg" fullWidth to="/cabinet/login" state={{ from: selfHref }}>
        {t("technologists.invite.cta")}
      </LinkButton>
    );
  }
  if (!isCompanyAccount || requests.isLoading || !requests.data) return null;

  const open = requests.data.filter((r) => r.status === "open");
  if (open.length === 0) {
    return (
      <LinkButton size="lg" fullWidth to="/cabinet/tech-requests/new">
        {t("technologists.invite.postFirst")}
      </LinkButton>
    );
  }

  const value = picked || String(open[0]?.id ?? "");
  return (
    <div className="space-y-3" data-testid="tech-invite">
      <Select
        aria-label={t("technologists.invite.pick")}
        value={value}
        onChange={(e) => setPicked(e.target.value)}
        options={open.map((r) => ({
          value: String(r.id),
          label: `${r.number} · ${t(`technologists.process.${r.process}`)} · ${r.product}`,
        }))}
      />
      <Button
        size="lg"
        fullWidth
        loading={invite.isPending}
        onClick={() =>
          invite.mutate(
            { requestId: Number(value), profileId },
            { onSuccess: () => setSentTo(value) },
          )
        }
      >
        {t("technologists.invite.cta")}
      </Button>
      {sentTo === value ? (
        <Alert tone="success" title={t("technologists.invite.sent")} />
      ) : null}
      {invite.isError ? <Alert tone="danger" title={t("errors.generic")} /> : null}
    </div>
  );
}
