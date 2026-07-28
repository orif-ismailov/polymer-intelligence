import { useEffect, useState } from "react";

import { useTranslation } from "react-i18next";

import { useCompany } from "@/entities/company";
import { useRequestSample } from "@/entities/sample";
import { Alert, Button, FormField, Input } from "@/shared/ui";

interface SampleRequestFormProps {
  offerId: number;
  companyId: number;
  onSent: () => void;
}

/**
 * The buyer's "send me a sample" form.
 *
 * The address is prefilled from the company profile (TZ: «адрес из профиля
 * компании покупателя») but stays editable: the registered address and the
 * warehouse that should receive the parcel are often different places, and a
 * courier needs the second one.
 */
export function SampleRequestForm({ offerId, companyId, onSent }: SampleRequestFormProps) {
  const { t } = useTranslation();
  const [qty, setQty] = useState("");
  const [address, setAddress] = useState("");
  const [touched, setTouched] = useState(false);
  const request = useRequestSample(offerId);

  // The legal address lives on the company DETAIL, not on the summary the
  // switcher carries, so it arrives a beat later. Seed the field once, and never
  // over the buyer's own typing.
  const company = useCompany(companyId);
  const legalAddress = company.data?.legal_address ?? "";
  useEffect(() => {
    if (!touched && legalAddress) setAddress(legalAddress);
  }, [legalAddress, touched]);

  const error = request.error
    ? request.error.message.includes("already_requested")
      ? t("samples.errors.alreadyRequested")
      : request.error.message.includes("samples_not_available")
        ? t("samples.errors.notAvailable")
        : t("errors.generic")
    : null;

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField label={t("samples.qty")} hint={t("samples.qtyHint")}>
          {({ id }) => (
            <Input id={id} value={qty} onChange={(e) => setQty(e.target.value)} />
          )}
        </FormField>
        <FormField label={t("samples.address")} required>
          {({ id }) => (
            <Input
              id={id}
              value={address}
              onChange={(e) => {
                setTouched(true);
                setAddress(e.target.value);
              }}
            />
          )}
        </FormField>
      </div>

      {error ? <Alert tone="danger">{error}</Alert> : null}

      <Button
        loading={request.isPending}
        disabled={address.trim() === ""}
        onClick={() =>
          request.mutate(
            { company_id: companyId, qty: qty.trim() || null, delivery_address: address.trim() },
            { onSuccess: onSent },
          )
        }
      >
        {t("samples.send")}
      </Button>
    </div>
  );
}
