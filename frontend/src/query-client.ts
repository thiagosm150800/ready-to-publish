// One QueryClient for the whole app; the provider in app/_layout.tsx uses
// this instance. Import it for cache calls outside components.
import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Never retry auth failures (they sign the user out); retry others twice.
      retry: (count, error) => !(error as { status?: number })?.status?.toString().startsWith("4") && count < 2,
    },
  },
});
