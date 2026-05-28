"use client";
import React from "react";

// Cursor: Base Button component with form support (shadcn/ui inspired)
interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  children: React.ReactNode;
  disabled?: boolean;
}

export function Button({ children, className = "", disabled = false, ...props }: ButtonProps) {
  return (
    <button
      {...props}
      disabled={disabled}
      className={`px-4 py-2 rounded bg-sky-600 text-white hover:bg-sky-700 disabled:opacity-50 disabled:cursor-not-allowed ${className}`}
    >
      {children}
    </button>
  );
}
