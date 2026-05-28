 "use client";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Cursor: Provides client-side providers (React Query, Zustand uses hooks directly)
const queryClient = new QueryClient();

export default function Providers({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
