import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { sampleApi, type SampleRequest } from "@/entities/sample";
import { EimzoSignButton } from "@/features/eimzo-sign";
import type { EimzoSigner } from "@/features/eimzo-sign";
import { coerceLang } from "@/shared/i18n";
import { formatDateTime } from "@/shared/lib";
import { Alert, Button, LoadingView } from "@/shared/ui";

interface SampleLetterCardProps {
  sample: SampleRequest;
}

/**
 * The письмо-обязательство attached to one sample request (P7.a W8).
 *
 * Both parties see the same card, and that is the point: the buyer undertakes
 * something, and evidence only one side can read is not evidence. What differs
 * is the verb — the buyer signs, the seller reads.
 *
 * The GET also RENDERS the letter for the buyer, so opening the card is what
 * brings it into existence; that is why there is no «создать письмо» button. A
 * seller opening it can never cause a render — otherwise a re-render could
 * change the bytes a signature was about to cover.
 */
export function SampleLetterCard({ sample }: SampleLetterCardProps) {
  const { t, i18n } = useTranslation();
  const lang = coerceLang(i18n.language);
  const queryClient = useQueryClient();
  const isBuyer = sample.my_role === "buyer";
  const signed = sample.letter_signed_at != null;

  const letter = useQuery({
    queryKey: ["sample-letter", sample.id],
    queryFn: () => sampleApi.letter(sample.id),
  });

  async function openPdf(): Promise<void> {
    window.open(await sampleApi.letterUrl(sample.id), "_blank", "noopener");
  }

  const signer: EimzoSigner<SampleRequest> = {
    getChallenge: () => sampleApi.letterChallenge(sample.id),
    verify: ({ pkcs7_64 }) =>
      sampleApi.signLetter(sample.id, pkcs7_64).then((data) => ({ ok: true, reason: null, data })),
  };

  if (letter.isLoading) return <LoadingView label={t("common.loading")} />;
  if (letter.isError || !letter.data) {
    return (
      <Alert tone="warning" title={t("sampleLetter.title")}>
        {t("sampleLetter.loadFailed")}
      </Alert>
    );
  }

  return (
    <section
      className="space-y-3 rounded-lg border border-border p-4"
      data-testid="sample-letter-card"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-base font-medium text-text">{t("sampleLetter.title")}</h3>
          <p className="mt-1 text-sm text-text-muted">
            {signed
              ? t("sampleLetter.signedAt", {
                  number: letter.data.number ?? "—",
                  at: formatDateTime(sample.letter_signed_at as string, lang),
                })
              : isBuyer
                ? t("sampleLetter.buyerPending")
                : t("sampleLetter.sellerPending")}
          </p>
        </div>
      </div>

      {/* The seller's clause, exactly as it will be (or was) signed — read from
          the snapshot, so editing the offer afterwards never rewrites it. */}
      {letter.data.terms ? (
        <blockquote
          className="border-l-2 border-border pl-3 text-sm text-text-muted"
          data-testid="sample-letter-terms"
        >
          {letter.data.terms}
        </blockquote>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        {letter.data.number ? (
          <Button variant="secondary" onClick={() => void openPdf()} data-testid="sample-letter-pdf">
            {t("sampleLetter.open")}
          </Button>
        ) : null}

        {isBuyer && !signed ? (
          <EimzoSignButton
            signer={signer}
            variant="primary"
            label={t("sampleLetter.sign")}
            onConfirmed={() => {
              void queryClient.invalidateQueries({ queryKey: ["samples"] });
              void queryClient.invalidateQueries({ queryKey: ["sample-letter", sample.id] });
            }}
          />
        ) : null}
      </div>

      {!signed && isBuyer ? (
        <p className="text-xs text-warning" data-testid="sample-letter-not-sent">
          {t("sampleLetter.notSentYet")}
        </p>
      ) : null}
    </section>
  );
}
