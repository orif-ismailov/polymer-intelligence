import { useTranslation } from "react-i18next";

import { useSubmitVerification } from "@/entities/verification";
import { Alert, Button } from "@/shared/ui";

interface SubmitVerificationButtonProps {
  companyId: number;
  /** `true` renders the "submit again" label (case already exists). */
  resubmit?: boolean;
  onSubmitted?: () => void;
}

export function SubmitVerificationButton({
  companyId,
  resubmit,
  onSubmitted,
}: SubmitVerificationButtonProps) {
  const { t } = useTranslation();
  const submit = useSubmitVerification(companyId);

  function handleClick(): void {
    submit.mutate(undefined, { onSuccess: () => onSubmitted?.() });
  }

  return (
    <div className="space-y-3">
      <Button onClick={handleClick} loading={submit.isPending}>
        {submit.isPending
          ? t("verification.submitting")
          : resubmit
            ? t("verification.resubmit")
            : t("verification.submit")}
      </Button>
      {submit.isError ? (
        <Alert tone="danger" title={t("wizard.errors.submitFailed")}>
          {submit.error.message}
        </Alert>
      ) : null}
    </div>
  );
}
