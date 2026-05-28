 "use client";
import React from "react";

// Cursor: Simple Input component
export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className="border px-3 py-2 rounded w-full focus:outline-none focus:ring-2 focus:ring-sky-400"
    />
  );
}
