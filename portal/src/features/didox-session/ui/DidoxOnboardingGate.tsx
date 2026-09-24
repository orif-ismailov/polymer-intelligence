import type { ReactNode } from "react";

import { Navigate, useLocation } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { useDidoxStatus } from "@/entities/edi";

import { wasPrompted } from "../model/onboardingPrompt";

export const DIDOX_ONBOARDING_PATH = "/cabinet/didox";

/**
 * Takes the owner of a verified company that is not yet on Didox to the
 * onboarding screen, once per visit.
 *
 * Never blocks: while the status loads, or when it fails, the cabinet renders as
 * usual — a slow Didox status must not stand between a customer and their own
 * cabinet. Only the owner is sent, since only the owner can register the company
 * and accept the offer.
 */
export function DidoxOnboardingGate({ children }: { children: ReactNode }) {
  const location = useLocation();
  const { activeCompany } = useActiveCompany();
  const verified = activeCompany?.status === "verified";
  const status = useDidoxStatus(
    verified ? (activeCompany?.id ?? null) : null,
  ).data;

  const needs =
    verified &&
    activeCompany != null &&
    status != null &&
    status.can_onboard &&
    (status.state === "not_registered" || status.state === "offer_unsigned");

  // The screen itself records that it was shown (on mount, not here — a render
  // may run twice, and marking during the first would swallow the redirect).
  if (
    needs &&
    location.pathname !== DIDOX_ONBOARDING_PATH &&
    !wasPrompted(activeCompany.id)
  ) {
    return <Navigate to={DIDOX_ONBOARDING_PATH} replace />;
  }
  return <>{children}</>;
}
