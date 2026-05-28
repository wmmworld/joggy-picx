import React from "react";

// Cursor: Simple Card wrapper for consistent UI
export function Card({ children }: { children: React.ReactNode }) {
  return <div className="bg-white shadow rounded p-4">{children}</div>;
}
