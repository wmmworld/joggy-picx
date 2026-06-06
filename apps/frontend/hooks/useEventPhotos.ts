"use client";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";

// Cursor: BibOut — ADR-0008 Phase B4 (multi-bib pipeline)
export type BibOut = {
  bib_number: string;
  confidence: number;  // 0.0–1.0 (from OCR, not YOLO)
  bbox_x1: number;     // bounding box in ORIGINAL image pixel space
  bbox_y1: number;
  bbox_x2: number;
  bbox_y2: number;
};

// Cursor: Photo Gallery types — Phase 4C; bibs field added ADR-0008 Phase B4
export type PhotoItem = {
  photo_id: string;
  bib_number: string | null;      // DEPRECATED — best bib only; use `bibs` instead
  bib_confidence: number | null;  // DEPRECATED
  bibs: BibOut[];                 // NEW — sorted by confidence desc, may be empty
  ai_review_status: "auto" | "manual_pending" | "manual_approved" | "manual_rejected";
  thumbnail_url: string | null;
  checkpoint_name: string | null;
  captured_at: string | null;
};

export type EventPhotosResponse = {
  items: PhotoItem[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
};

export type PhotoFilters = {
  page?: number;
  bib?: string;
  checkpointId?: string;
  aiStatus?: string;
};

// Cursor: Fetch paginated event photos with filters
async function getEventPhotos(
  eventId: string,
  filters: PhotoFilters
): Promise<EventPhotosResponse> {
  const params = new URLSearchParams();
  params.set("page", String(filters.page || 1));
  params.set("per_page", "24");
  if (filters.bib) params.set("bib", filters.bib);
  if (filters.checkpointId) params.set("checkpoint_id", filters.checkpointId);
  if (filters.aiStatus) params.set("ai_status", filters.aiStatus);

  const result = await apiGet<EventPhotosResponse>(
    `/internal/events/${eventId}/photos?${params.toString()}`
  );
  if (!result.success) throw new Error(result.error || "Failed to fetch photos");
  return result.data!;
}

// Cursor: TanStack Query hook for event photos
export function useEventPhotos(eventId: string | null, filters: PhotoFilters = {}) {
  return useQuery({
    queryKey: ["event-photos", eventId, filters],
    queryFn: () => getEventPhotos(eventId!, filters),
    enabled: !!eventId,
    staleTime: 30 * 1000,
  });
}
