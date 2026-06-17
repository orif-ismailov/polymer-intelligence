import { QueryClient } from "@tanstack/react-query";

/**
 * TanStack QueryClient singleton.
 * staleTime = 30s aligns with the SSE polling fallback interval (DEC-realtime-sse-not-websocket).
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

export default queryClient;
