import { QueryClient } from "@tanstack/react-query";

/** Server state (chat list, agents, who am I). Chat streaming stays in the chat store. */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});
