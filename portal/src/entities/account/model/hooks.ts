import { useEffect } from "react";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { coerceLang, setLanguage } from "@/shared/i18n";

import { accountApi } from "./api";
import { useAuthStore } from "./authStore";
import type { Account, AccountPatch } from "./types";

/**
 * Boot-time session restore. On mount, if there's no in-memory token, try a
 * silent refresh (httpOnly cookie) followed by `GET /portal/me`. Whatever the
 * outcome, `initializing` flips to false so the router guard can decide.
 */
export function useBootstrapAuth(): void {
  const setAuth = useAuthStore((s) => s.setAuth);
  const clear = useAuthStore((s) => s.clear);
  const setInitialized = useAuthStore((s) => s.setInitialized);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap(): Promise<void> {
      // Already authenticated in this tab's memory — nothing to restore.
      if (useAuthStore.getState().token) {
        if (!cancelled) setInitialized();
        return;
      }
      try {
        const result = await accountApi.refresh();
        if (cancelled) return;
        setAuth(result.access_token, result.account);
        setLanguage(coerceLang(result.account.language));
      } catch {
        if (!cancelled) clear();
      } finally {
        if (!cancelled) setInitialized();
      }
    }

    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, [setAuth, clear, setInitialized]);
}

/** Update the current account (name / language). */
export function useUpdateAccount() {
  const qc = useQueryClient();
  const setAccount = useAuthStore((s) => s.setAccount);
  return useMutation<Account, Error, AccountPatch>({
    mutationFn: (patch) => accountApi.updateMe(patch),
    onSuccess: (account) => {
      setAccount(account);
      if (account.language) setLanguage(coerceLang(account.language));
      qc.setQueryData(["account", "me"], account);
    },
  });
}

/** Log out: revoke server session, then clear local auth + query cache. */
export function useLogout() {
  const qc = useQueryClient();
  const clear = useAuthStore((s) => s.clear);
  return useMutation<void, Error, void>({
    mutationFn: async () => {
      try {
        await accountApi.logout();
      } catch {
        // Even if the server call fails, drop local state below.
      }
    },
    onSettled: () => {
      clear();
      qc.clear();
    },
  });
}
