import { type ReactNode, useState } from "react";

import {
  HydrationBoundary,
  QueryClient,
  QueryClientProvider,
  type DehydratedState,
} from "@tanstack/react-query";

import { ApiError } from "@/shared/api";

/** Don't retry auth/permission/not-found errors — only transient failures. */
function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && [401, 403, 404, 409, 422].includes(error.status)) {
    return false;
  }
  return failureCount < 2;
}

function makeClient(): QueryClient {
  return new QueryClient({
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
  });
}

interface QueryProviderProps {
  children: ReactNode;
  /**
   * Client supplied by the SSR entry, which already prefetched into it. Omitted
   * in the browser, where a fresh client is created once per mount.
   */
  client?: QueryClient;
  /**
   * Cache the server dehydrated, inlined into the HTML. Hydrating it is what
   * stops the browser refetching everything the server just fetched, which would
   * flash the same content in a second time.
   */
  dehydratedState?: DehydratedState;
}

export function QueryProvider({ children, client, dehydratedState }: QueryProviderProps) {
  // `useState` initialiser, not a module-level singleton: on the server a shared
  // client would leak one visitor's cache into the next request.
  const [fallback] = useState(makeClient);

  return (
    <QueryClientProvider client={client ?? fallback}>
      <HydrationBoundary state={dehydratedState}>{children}</HydrationBoundary>
    </QueryClientProvider>
  );
}
