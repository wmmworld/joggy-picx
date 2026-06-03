"use client";
import { useState } from "react";
import { apiPost } from "../../lib/api";
import { formatThaiDateTime } from "../../lib/datetime";

// Cursor: Event Token Generation Modal — Phase 5
interface EventTokenResponse {
  token_id: string;
  token_prefix: string;
  plaintext_token: string;
  expires_at: string;
  event_id: string;
  event_name: string;
}

interface Props {
  isOpen: boolean;
  eventId: string;
  eventName: string;
  onClose: () => void;
}

export default function GenerateEventTokenModal({
  isOpen,
  eventId,
  eventName,
  onClose,
}: Props) {
  const [token, setToken] = useState<EventTokenResponse | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Cursor: Generate new event token via API
  const handleGenerate = async () => {
    setGenerating(true);
    setError(null);
    const result = await apiPost<EventTokenResponse, undefined>(
      `/internal/events/${eventId}/tokens`,
      undefined
    );
    setGenerating(false);
    if (!result.success) {
      setError(result.error || "Token generation failed");
      return;
    }
    setToken(result.data!);
  };

  // Cursor: Copy plaintext token to clipboard
  const handleCopy = async () => {
    if (!token) return;
    await navigator.clipboard.writeText(token.plaintext_token);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Cursor: Close modal and reset state
  const handleClose = () => {
    setToken(null);
    setError(null);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
      onClick={handleClose}
    >
      <div
        className="bg-white rounded-lg shadow-xl max-w-xl w-full p-6"
        onClick={(e) => e.stopPropagation()}
      >
        {!token ? (
          // Cursor: Step 1 — Confirm token generation
          <>
            <h2 className="text-xl font-bold mb-3">สร้าง Event Token</h2>
            <p className="text-slate-600 mb-2">
              สำหรับใช้กับ Raspberry Pi edge daemon ของงาน:
            </p>
            <p className="font-semibold text-slate-900 mb-4">{eventName}</p>
            <div className="bg-amber-50 border border-amber-200 rounded p-3 mb-4 text-sm text-amber-900">
              ⚠️ Token จะแสดง <strong>ครั้งเดียว</strong> หลังคลิก "สร้าง"
              <br />
              เก็บใส่ <code className="bg-white px-1">/home/pi/joggy/.env</code>
              ทันที — เก่าก่อนหน้าจะยังใช้ได้ (ไม่ revoke อัตโนมัติ)
            </div>
            {error && (
              <div className="bg-red-50 border border-red-200 rounded p-2 mb-3 text-sm text-red-800">
                {error}
              </div>
            )}
            <div className="flex justify-end gap-2">
              <button
                onClick={handleClose}
                disabled={generating}
                className="px-4 py-2 bg-slate-100 text-slate-700 rounded hover:bg-slate-200 disabled:opacity-50"
              >
                ยกเลิก
              </button>
              <button
                onClick={handleGenerate}
                disabled={generating}
                className="px-4 py-2 bg-emerald-600 text-white rounded hover:bg-emerald-700 disabled:opacity-50"
              >
                {generating ? "กำลังสร้าง..." : "🔑 สร้าง Token"}
              </button>
            </div>
          </>
        ) : (
          // Cursor: Step 2 — Show plaintext token (one-time display)
          <>
            <h2 className="text-xl font-bold mb-3">✅ สร้าง Token สำเร็จ</h2>
            <div className="bg-red-50 border border-red-300 rounded p-3 mb-4 text-sm text-red-900">
              ⚠️ <strong>คัดลอกตอนนี้</strong> — Token จะไม่แสดงอีก
            </div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Event Token (plaintext)
            </label>
            <div className="flex gap-2 mb-3">
              <input
                type="text"
                value={token.plaintext_token}
                readOnly
                className="flex-1 px-3 py-2 border border-slate-300 rounded font-mono text-sm bg-slate-50"
                onClick={(e) => (e.target as HTMLInputElement).select()}
              />
              <button
                onClick={handleCopy}
                className="px-4 py-2 bg-sky-600 text-white rounded hover:bg-sky-700 text-sm whitespace-nowrap"
              >
                {copied ? "✓ คัดลอกแล้ว" : "📋 คัดลอก"}
              </button>
            </div>
            <div className="text-sm text-slate-600 space-y-1 mb-4">
              <p>
                <strong>Token prefix:</strong>{" "}
                <code className="bg-slate-100 px-1">{token.token_prefix}</code>
              </p>
              <p>
                <strong>Expires at:</strong> {formatThaiDateTime(token.expires_at)}
              </p>
            </div>
            <div className="bg-slate-50 border border-slate-200 rounded p-3 mb-4 text-xs text-slate-700 font-mono">
              # บน Pi: แก้ /home/pi/joggy/.env แล้ว restart service
              <br />
              EVENT_TOKEN={token.plaintext_token.slice(0, 20)}...
              <br />
              sudo systemctl restart joggy-edge
            </div>
            <div className="flex justify-end">
              <button
                onClick={handleClose}
                className="px-4 py-2 bg-emerald-600 text-white rounded hover:bg-emerald-700"
              >
                เสร็จสิ้น
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
