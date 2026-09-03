import { useEffect, useState } from "react";

import { useTranslation } from "react-i18next";

import { useCompany } from "@/entities/company";
import { useRequestSample, type SampleRequest } from "@/entities/sample";
import { Alert, Button, FormField, Input } from "@/shared/ui";

interface SampleRequestFormProps {
  offerId: number;
  companyId: number;
  /**
   * Receives the CREATED request, not just "done".
   *
   * An offer may demand a signed письмо-обязательство, and then the request lands
   * in `pending_letter` — asked, but deliberately not with the seller yet. Saying
   * "sent to the seller" there would be false, and would leave the buyer with no
   * hint that a signature is still owed.
   */
  onSent: (sample: SampleRequest) => void;
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

  // The server codes its refusals (`detail: {code}`); the fetch client puts that
  // in `ApiError.code` and leaves `.message` as "Request failed with status 409",
  // so matching on the message made every refusal read as a generic failure.
  const ERRORS: Record<string, string> = {
    already_requested: t("samples.errors.alreadyRequested"),
    samples_not_available: t("samples.errors.notAvailable"),
    own_offer: t("samples.errors.ownOffer"),
  };
  const error = request.error
    ? (ERRORS[request.error.code ?? ""] ?? t("errors.generic"))
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
            { onSuccess: (sample) => onSent(sample) },
          )
        }
      >
        {t("samples.send")}
      </Button>
    </div>
  );
}
