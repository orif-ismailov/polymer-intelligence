import { useMutation } from "@tanstack/react-query";

import { accountApi, useAuthStore } from "@/entities/account";
import type { AuthResult, PasswordChangePayload } from "@/entities/account";
import type { ApiError } from "@/shared/api";

/**
 * Change the password and adopt the session that comes back.
 *
 * Writing the returned account is what actually clears the gate on the client:
 * `must_change_password` arrives false, `RequirePasswordCurrent` stops redirecting,
 * and the fresh access token replaces one the server would now refuse.
 */
export function useChangePassword() {
  const setAuth = useAuthStore((s) => s.setAuth);
  return useMutation<AuthResult, ApiError, PasswordChangePayload>({
    mutationFn: (payload) => accountApi.changePassword(payload),
    onSuccess: (result) => {
      setAuth(result.access_token, result.account);
    },
  });
}
