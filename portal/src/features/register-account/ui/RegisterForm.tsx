import { type FormEvent, useState } from "react";

import { useTranslation } from "react-i18next";

import type { AppliedAs } from "@/entities/account";
import { ApiError } from "@/shared/api";
import { formatPhoneMask, isValidPhone, normalizePhone } from "@/shared/lib";
import { Alert, Button, FormField, Input, Textarea } from "@/shared/ui";

import { useRegister } from "../model/useRegister";

interface RegisterFormProps {
  /** Called once the request is accepted — there is no session to hand over. */
  onSubmitted: () => void;
  /**
   * `technologist` — a private expert (0055). They have no company to name, so
   * that field becomes «Специализация», which staff read beside the note.
   */
  appliedAs?: AppliedAs;
}

/**
 * The access-request form. It is not a sign-up: nobody chooses a password here.
 *
 * The phone is contact information — staff call it — so it is validated for shape and
 * nothing else. There is no code to confirm it with any more, which is why the form
 * asks for a company name and a note: those are what a staff member reads while
 * deciding whether to issue credentials.
 */
export function RegisterForm({ onSubmitted, appliedAs = "company" }: RegisterFormProps) {
  const isExpert = appliedAs === "technologist";
  const { t } = useTranslation();
  const [contactName, setContactName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [phoneDisplay, setPhoneDisplay] = useState("");
  const [note, setNote] = useState("");
  const [touched, setTouched] = useState(false);
  const register = useRegister();

  const phoneValid = isValidPhone(phoneDisplay);
  const showPhoneError = touched && !phoneValid;
  const filled = contactName.trim().length > 0 && companyName.trim().length > 0 && phoneValid;

  function handleSubmit(e: FormEvent<HTMLFormElement>): void {
    e.preventDefault();
    setTouched(true);
    if (!filled) return;
    // For an expert the second field is their specialisation — staff read it
    // first, so it heads the note rather than riding in a company-name column.
    const expertNote = [companyName.trim(), note.trim()].filter(Boolean).join("\n\n");
    register.mutate(
      {
        contact_name: contactName.trim(),
        company_name: isExpert ? undefined : companyName.trim(),
        phone: normalizePhone(phoneDisplay),
        note: (isExpert ? expertNote : note.trim()) || undefined,
        applied_as: appliedAs,
      },
      { onSuccess: onSubmitted },
    );
  }

  const error = register.error;
  const rateLimited = error instanceof ApiError && error.status === 429;

  return (
    <form onSubmit={handleSubmit} className="space-y-5" noValidate>
      <FormField label={t("register.contactName")} required>
        {({ id, invalid, describedBy }) => (
          <Input
            id={id}
            autoFocus
            autoComplete="name"
            value={contactName}
            invalid={invalid}
            aria-describedby={describedBy}
            onChange={(e) => setContactName(e.target.value)}
          />
        )}
      </FormField>

      <FormField
        label={t(isExpert ? "register.specialization" : "register.companyName")}
        required
        hint={t(isExpert ? "register.specializationHint" : "register.companyHint")}
      >
        {({ id, invalid, describedBy }) => (
          <Input
            id={id}
            autoComplete={isExpert ? "organization-title" : "organization"}
            value={companyName}
            invalid={invalid}
            aria-describedby={describedBy}
            onChange={(e) => setCompanyName(e.target.value)}
          />
        )}
      </FormField>

      <FormField
        label={t("auth.phoneLabel")}
        required
        hint={t("register.phoneHint")}
        error={showPhoneError ? t("auth.phoneInvalid") : null}
      >
        {({ id, invalid, describedBy }) => (
          <Input
            id={id}
            type="tel"
            inputMode="tel"
            autoComplete="tel"
            value={phoneDisplay}
            invalid={invalid}
            aria-describedby={describedBy}
            onChange={(e) => setPhoneDisplay(formatPhoneMask(e.target.value))}
            onBlur={() => setTouched(true)}
          />
        )}
      </FormField>

      <FormField
        label={t("register.note")}
        hint={t(isExpert ? "register.expertNoteHint" : "register.noteHint")}
      >
        {({ id, describedBy }) => (
          <Textarea
            id={id}
            rows={3}
            value={note}
            aria-describedby={describedBy}
            onChange={(e) => setNote(e.target.value)}
          />
        )}
      </FormField>

      {error ? (
        <Alert
          tone="danger"
          title={rateLimited ? t("auth.tooManyRequests") : t("errors.generic")}
        >
          {rateLimited ? t("auth.tryLater") : error.message}
        </Alert>
      ) : null}

      <Button
        type="submit"
        fullWidth
        size="lg"
        loading={register.isPending}
        disabled={!filled || register.isPending}
      >
        {register.isPending ? t("register.submitting") : t("register.submit")}
      </Button>
    </form>
  );
}
