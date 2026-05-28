// Cursor: Custom hook for fetching events list (TanStack Query wrapper)
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";

// Cursor (fixed by Claude): align with backend EventOut schema
// status values match EventStatus enum: "planned" | "active" | "completed"
// checkpoints is always [] in list endpoint (detail fetches full list)
export type Event = {
  id: string;
  name: string;
  organizer_id: string;
  start_at: string;
  end_at: string;
  status: "planned" | "active" | "completed";
  allowed_origins?: object | null;
  retention_until?: string | null;
  created_at: string;
  checkpoints: CheckpointSummary[];
};

export type CheckpointSummary = {
  id: string;
  name: string;
  kind: string;
  seq_order: number;
};

// Cursor: Query function using typed API wrapper
async function getEvents(): Promise<Event[]> {
  const result = await apiGet<Event[]>("/internal/events");

  if (!result.success) {
    throw new Error(result.error || "Failed to fetch events");
  }

  return result.data || [];
}

// Cursor: Custom hook for events list with built-in caching + retry
export function useEvents() {
  return useQuery({
    queryKey: ["events"],
    queryFn: getEvents,
    staleTime: 30 * 1000,
    retry: 2
  });
}
