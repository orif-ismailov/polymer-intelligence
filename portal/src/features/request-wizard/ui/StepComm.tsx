import { useTranslation } from "react-i18next";

import {
  MailIcon,
  MessageIcon,
  RadioCard,
  ShieldCheckIcon,
  StoreIcon,
  UsersIcon,
} from "@/shared/ui";

import {
  COUNTED_STEPS,
  OFFER_CHANNELS,
  STEP_COMM,
  VISIBILITY_OPTIONS,
  type OfferChannel,
  type VisibilityOption,
} from "../model/constants";
import { useRequestDraft } from "../model/draftStore";
import { StepNav } from "./StepNav";

interface StepCommProps {
  onNext: () => void;
  onBack: () => void;
}

const CHANNEL_ICON = {
  app: <StoreIcon size={18} />,
  email: <MailIcon size={18} />,
  telegram: <MessageIcon size={18} />,
} as const;

const VISIBILITY_ICON = {
  verified: <ShieldCheckIcon size={18} />,
  all: <StoreIcon size={18} />,
  selected: <UsersIcon size={18} />,
} as const;

/**
 * Sheet 4 — «Условия общения»: how offers arrive, and who can see the request.
 * Soft preferences — folded into `comment` at submit.
 */
export function StepComm({ onNext, onBack }: StepCommProps) {
  const { t } = useTranslation();
  const draft = useRequestDraft((s) => s.draft);
  const setField = useRequestDraft((s) => s.setField);

  return (
    <div className="space-y-6" data-testid="request-wizard-step-4">
      <header>
        <p className="num text-xs text-text-muted">
          {t("requestWizard.stepOf", { current: STEP_COMM, total: COUNTED_STEPS })}
        </p>
        <h2 className="mt-1 text-xl font-semibold text-text">
          {t("requestWizard.comm.title")}
        </h2>
      </header>

      <fieldset className="space-y-2">
        <legend className="mb-2 text-sm font-medium text-text">
          {t("requestWizard.comm.channelLabel")}
        </legend>
        {OFFER_CHANNELS.map((channel) => (
          <RadioCard
            key={channel}
            name="offer-channel"
            value={channel}
            checked={draft.offerChannel === channel}
            onChange={(v) => setField("offerChannel", v as OfferChannel)}
            title={t(`requestWizard.comm.channel.${channel}.title`)}
            description={t(`requestWizard.comm.channel.${channel}.body`)}
            icon={CHANNEL_ICON[channel]}
            data-testid={`request-wizard-channel-${channel}`}
          />
        ))}
      </fieldset>

      <fieldset className="space-y-2">
        <legend className="mb-2 text-sm font-medium text-text">
          {t("requestWizard.comm.visibilityLabel")}
        </legend>
        {VISIBILITY_OPTIONS.map((opt) => (
          <RadioCard
            key={opt}
            name="visibility"
            value={opt}
            checked={draft.visibility === opt}
            onChange={(v) => setField("visibility", v as VisibilityOption)}
            title={t(`requestWizard.comm.visibility.${opt}.title`)}
            description={t(`requestWizard.comm.visibility.${opt}.body`)}
            icon={VISIBILITY_ICON[opt]}
            data-testid={`request-wizard-visibility-${opt}`}
          />
        ))}
      </fieldset>

      <StepNav onNext={onNext} onBack={onBack} />
    </div>
  );
}
