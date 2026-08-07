import {
  isCarrierCompany,
  isLaboratoryCompany,
  useActiveCompany,
} from "@/entities/company";
import { LabPoolPage } from "@/pages/lab";
import { LogisticsPoolPage } from "@/pages/logistics";
import { RequestsPage } from "@/pages/requests";
import { LoadingView } from "@/shared/ui";

/**
 * `/cabinet/requests` — «Заявки», which means three different things.
 *
 * A carrier and a laboratory both file zero polymer purchase requests, so the
 * buyer's page is permanently empty for them; what belongs in that slot is the
 * broadcast pool for whatever they actually do. Everyone else keeps exactly the
 * page they had.
 *
 * A switch rather than a branch inside `RequestsPage` on purpose: the buyer's
 * module stays untouched, and the whole rule is one file a reviewer can read in
 * ten seconds. It lives in `app/router/` because it is a routing decision
 * serving three domains, not a page belonging to any one of them.
 *
 * Waits for the active company rather than defaulting to the buyer view —
 * rendering the wrong page and swapping it a tick later is a visible flash, and
 * `declared_roles` rides on the summary precisely so this costs no extra fetch.
 *
 * A company can hold only one account type (`assert_single_account_type`), so
 * the two role arms cannot both match.
 */
export function RequestsRouteSwitch() {
  const { activeCompany, isLoading } = useActiveCompany();

  if (isLoading) return <LoadingView />;
  if (isCarrierCompany(activeCompany)) return <LogisticsPoolPage />;
  if (isLaboratoryCompany(activeCompany)) return <LabPoolPage />;
  return <RequestsPage />;
}
