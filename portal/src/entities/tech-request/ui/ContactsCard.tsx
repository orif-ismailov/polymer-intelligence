import { useTranslation } from "react-i18next";

import { Card, CardBody, SpecItem, SpecList } from "@/shared/ui";

import type { Contacts } from "../model/types";

/** The counterparty's contacts — shown to both sides once an offer is accepted. */
export function ContactsCard({ contacts, title }: { contacts: Contacts; title: string }) {
  const { t } = useTranslation();
  return (
    <Card data-testid="tech-contacts">
      <CardBody>
        <h2 className="text-sm font-semibold text-text">{title}</h2>
        <p className="mt-1 text-xs text-text-muted">{t("techRequest.contactsHint")}</p>
        <div className="mt-3">
          <SpecList>
            {contacts.name ? <SpecItem label={t("techRequest.contactName")} value={contacts.name} /> : null}
            {contacts.phone ? (
              <SpecItem
                label={t("techRequest.contactPhone")}
                value={<a className="text-brand hover:underline" href={`tel:${contacts.phone}`}>{contacts.phone}</a>}
              />
            ) : null}
            {contacts.email ? (
              <SpecItem
                label={t("techRequest.contactEmail")}
                value={<a className="text-brand hover:underline" href={`mailto:${contacts.email}`}>{contacts.email}</a>}
              />
            ) : null}
          </SpecList>
        </div>
      </CardBody>
    </Card>
  );
}
