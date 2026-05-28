// Cursor: Custom hook for fetching single event detail (TanStack Query wrapper)
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";

// Claude: align with backend CheckpointOut schema
// seq_order (not order), lat/lng (not location)
export type Checkpoint = {
  id: string;
  event_id: string;
  name: string;
  kind: string;
  lat?: number | null;
  lng?: number | null;
  seq_order: number;
};

// Claude: align with backend EventOut schema
// photo_count / pending_review / description are not returned by backend (Phase 3+ fields)
export type EventDetail = {
  id: string;
  name: string;
  organizer_id: string;
  start_at: string;
  end_at: string;
  status: string;
  allowed_origins?: object | null;
  retention_until?: string | null;
  created_at: string;
  checkpoints: Checkpoint[];
};

// Cursor: Query function to fetch event by ID (exported for reuse outside hooks)
export async function getEvent(eventId: string): Promise<EventDetail> {
  const result = await apiGet<EventDetail>(`/internal/events/${eventId}`);

  if (!result.success) {
    throw new Error(result.error || "Failed to fetch event");
  }

  return result.data || ({} as EventDetail);
}

// Cursor: Custom hook for event detail with enabled flag (only query when eventId is provided)
export function useEventDetail(eventId: string | null) {
  return useQuery({
    queryKey: ["event", eventId],
    queryFn: () => getEvent(eventId!),
    enabled: !!eventId,
    staleTime: 60 * 1000
  });
}
