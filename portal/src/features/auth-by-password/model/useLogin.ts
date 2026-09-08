import { useMutation } from "@tanstack/react-query";

import { accountApi, useAuthStore } from "@/entities/account";
import type { AuthResult, LoginPayload } from "@/entities/account";
import type { ApiError } from "@/shared/api";
import { coerceLang, setLanguage } from "@/shared/i18n";

/**
 * Sign in with the staff-issued login + password.
 *
 * The success handler only writes the session; it navigates nowhere. `RedirectIfAuthed`
 * fires the instant a token lands and sends the visitor to `state.from` (or the cabinet
 * home), so a `navigate` here would race a guard that always wins.
 */
export function useLogin() {
  const setAuth = useAuthStore((s) => s.setAuth);
  return useMutation<AuthResult, ApiError, LoginPayload>({
    mutationFn: (payload) => accountApi.login(payload),
    onSuccess: (result) => {
      setAuth(result.access_token, result.account);
      setLanguage(coerceLang(result.account.language));
    },
  });
}
