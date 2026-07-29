import { useMutation } from "@tanstack/react-query";

import { accountApi, useAuthStore } from "@/entities/account";
import type { AuthResult } from "@/entities/account";
import type { ApiError } from "@/shared/api";
import { coerceLang, setLanguage } from "@/shared/i18n";

/** Request an OTP for a phone number. Surfaces the 429 Retry-After as an ApiError. */
export function useRequestOtp() {
  return useMutation<void, ApiError, string>({
    mutationFn: (phone) => accountApi.requestOtp(phone),
  });
}

/** Verify an OTP code and persist the resulting session. */
export function useVerifyOtp() {
  const setAuth = useAuthStore((s) => s.setAuth);
  return useMutation<AuthResult, ApiError, { phone: string; code: string }>({
    mutationFn: (payload) => accountApi.verifyOtp(payload),
    onSuccess: (result) => {
      setAuth(result.access_token, result.account);
      setLanguage(coerceLang(result.account.language));
    },
  });
}
