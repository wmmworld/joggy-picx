"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPatch } from "../lib/api";

// Cursor: Review Queue types — Phase 4B
export type ReviewQueueItem = {
  queue_id: string;
  photo_id: string;
  reason: "low_ocr_conf" | "no_bib";
  bib_number: string | null;
  bib_confidence: number | null;
  thumbnail_url: string | null;
  checkpoint_name: string | null;
  created_at: string;
};

type ReviewActionPayload = {
  action: "approve" | "reject";
  decision_bib?: string | null;
};

type ReviewActionResponse = {
  status: "approved" | "rejected";
  queue_id: string;
};

// Cursor: Fetch review queue items for a given event
async function getReviewQueue(eventId: string): Promise<ReviewQueueItem[]> {
  const result = await apiGet<ReviewQueueItem[]>(
    `/internal/review-queue?event_id=${eventId}`
  );
  if (!result.success) throw new Error(result.error || "Failed to fetch review queue");
  return result.data || [];
}

// Cursor: TanStack Query hook for review queue list
export function useReviewQueue(eventId: string | null) {
  return useQuery({
    queryKey: ["review-queue", eventId],
    queryFn: () => getReviewQueue(eventId!),
    enabled: !!eventId,
    staleTime: 30 * 1000,
    retry: 2,
  });
}

// Cursor: Mutation hook for approve/reject/override actions
export function useResolveItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      queueId,
      payload,
    }: {
      queueId: string;
      payload: ReviewActionPayload;
    }) => {
      const result = await apiPatch<ReviewActionResponse>(
        `/internal/review-queue/${queueId}`,
        payload
      );
      if (!result.success) throw new Error(result.error || "Failed to resolve item");
      return result.data;
    },
  });
}
