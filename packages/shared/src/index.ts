// Cursor: Shared types placeholder (will be generated from OpenAPI in future)
// Codex: export placeholder generated type เพื่อให้ shared package มีจุดอ้างอิงเดียว
export * from "./types.generated";

export type ApiPhoto = {
  id: string;
  event_id: string;
  thumbnail_url?: string;
  original_url?: string;
  captured_at?: string;
};

export type ApiUser = {
  id: string;
  email: string;
  role: "admin" | "staff";
};
