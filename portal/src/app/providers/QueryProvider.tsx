import { type ReactNode, useState } from "react";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ApiError } from "@/shared/api";

/** Don't retry auth/permission/not-found errors — only transient failures. */
function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && [401, 403, 404, 409, 422].includes(error.status)) {
    return false;
  }
  return failureCount < 2;
}

export function QueryProvider({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: shouldRetry,
            staleTime: 30_000,
            refetchOnWindowFocus: false,
          },
          mutations: {
            retry: false,
          },
        },
      }),
  );

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
