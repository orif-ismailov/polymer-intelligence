import { useMutation } from "@tanstack/react-query";

import { accountApi } from "@/entities/account";
import type { RegisterPayload } from "@/entities/account";
import type { ApiError } from "@/shared/api";

/**
 * Submit an access request.
 *
 * Deliberately touches no auth state: this grants nothing. The server records a
 * `pending` account and answers the same 202 every time — including for a phone that
 * has applied before — so there is no session to store and nothing to branch on.
 */
export function useRegister() {
  return useMutation<{ status: string }, ApiError, RegisterPayload>({
    mutationFn: (payload) => accountApi.register(payload),
  });
}
