"use client";
import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { Input } from "../../../components/ui/Input";
import { Button } from "../../../components/ui/Button";
import { createClient } from "../../../lib/supabase";

// Cursor: Login page for Internal Users (Admin/Staff) with Supabase Auth (D-019)
export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Cursor: Handle Supabase email/password sign-in
  const handleSignIn = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const supabase = createClient();
      const { error: signInError } = await supabase.auth.signInWithPassword({
        email,
        password
      });

      if (signInError) {
        setError(signInError.message);
        return;
      }

      // Cursor: Redirect to dashboard on successful login
      router.push("/dashboard");
    } catch (err) {
      setError("เกิดข้อผิดพลาด — โปรดลองอีกครั้ง");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 p-4">
      <div className="w-full max-w-md">
        <div className="bg-white shadow rounded p-6">
          <h1 className="text-2xl font-semibold mb-1">Joggy-PicX Internal</h1>
          <p className="text-sm text-slate-500 mb-6">ระบบจัดการภาพ — Admin/Staff เท่านั้น</p>

          {/* Cursor: Error message display */}
          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
              {error}
            </div>
          )}

          <form onSubmit={handleSignIn} className="space-y-4">
            <div>
              <label className="block mb-2 text-sm font-medium">Email</label>
              <Input
                type="email"
                placeholder="you@organizer.example"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>

            <div>
              <label className="block mb-2 text-sm font-medium">Password</label>
              <Input
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>

            {/* Cursor: Submit button with loading state */}
            <Button
              onClick={() => {}}
              className={`w-full ${loading ? "opacity-50 cursor-not-allowed" : ""}`}
            >
              {loading ? "กำลังเข้าสู่ระบบ..." : "เข้าสู่ระบบ"}
            </Button>
          </form>

          <p className="mt-4 text-xs text-slate-500">
            สำหรับ MFA setup, โปรดติดต่อ admin — ไม่มี self-signup (D-019)
          </p>
        </div>
      </div>
    </div>
  );
}
