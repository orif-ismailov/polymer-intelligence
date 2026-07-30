import { useTranslation } from "react-i18next";

import { Button, MessageIcon, SendIcon, StickyActionBar } from "@/shared/ui";

interface ProfileActionBarProps {
  onMessage: () => void;
  onRfq: () => void;
  messageDisabled?: boolean;
}

/**
 * Mockup sticky footer: outline «Написать» + green «Запросить предложение (RFQ)».
 */
export function ProfileActionBar({
  onMessage,
  onRfq,
  messageDisabled = false,
}: ProfileActionBarProps) {
  const { t } = useTranslation();

  return (
    <StickyActionBar>
      <div
        className="flex w-full gap-2"
        data-testid="seller-profile-action-bar"
      >
        <Button
          variant="outline"
          size="lg"
          className="min-w-0 flex-1"
          disabled={messageDisabled}
          onClick={onMessage}
        >
          <MessageIcon size={16} />
          {t("companyProfile.message")}
        </Button>
        <Button size="lg" className="min-w-0 flex-[1.4]" onClick={onRfq}>
          <SendIcon size={16} />
          {t("companyProfile.requestRfq")}
        </Button>
      </div>
    </StickyActionBar>
  );
}
