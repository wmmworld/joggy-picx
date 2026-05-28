// Cursor: Typed API client with automatic Supabase JWT injection (D-019)
import { createClient } from "./supabase";

// Cursor: Base URL สำหรับ Internal API (default: localhost:8000 for local dev)
const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type ApiResponse<T> = {
  success: boolean;
  data?: T;
  error?: string;
};

// Cursor: GET helper with auth + error handling
export async function apiGet<T>(endpoint: string): Promise<ApiResponse<T>> {
  try {
    const supabase = createClient();
    const {
      data: { session }
    } = await supabase.auth.getSession();

    if (!session) {
      return { success: false, error: "Unauthorized" };
    }

    const response = await fetch(`${BASE_URL}${endpoint}`, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${session.access_token}`
      }
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      return {
        success: false,
        error: errorData.detail || `HTTP ${response.status}`
      };
    }

    const data = await response.json();
    return { success: true, data };
  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error.message : "Unknown error"
    };
  }
}

// Cursor: POST helper with auth + payload
export async function apiPost<T, B = unknown>(
  endpoint: string,
  body?: B
): Promise<ApiResponse<T>> {
  try {
    const supabase = createClient();
    const {
      data: { session }
    } = await supabase.auth.getSession();

    if (!session) {
      return { success: false, error: "Unauthorized" };
    }

    const response = await fetch(`${BASE_URL}${endpoint}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${session.access_token}`
      },
      body: body ? JSON.stringify(body) : undefined
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      return {
        success: false,
        error: errorData.detail || `HTTP ${response.status}`
      };
    }

    const data = await response.json();
    return { success: true, data };
  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error.message : "Unknown error"
    };
  }
}
