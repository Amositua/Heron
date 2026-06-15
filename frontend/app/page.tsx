"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { startBuild } from "@/lib/api";

export default function ChatPage() {
  const [prompt, setPrompt] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  async function handleSubmit() {
    const trimmed = prompt.trim();
    if (!trimmed || submitting) return;

    setSubmitting(true);
    setError(null);
    try {
      const { build_id } = await startBuild(trimmed);
      router.push(`/build/${build_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start build");
      setSubmitting(false);
    }
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      void handleSubmit();
    }
  }

  return (
    <div className="flex h-full min-h-screen flex-col">
      <div className="flex flex-1 items-center justify-center px-6">
        <p className="max-w-md text-center text-zinc-500">
          Describe what you want to monitor in Splunk.
        </p>
      </div>
      <div className="border-t border-zinc-800 px-6 py-6">
        <div className="mx-auto flex w-full max-w-xl flex-col gap-2">
          {error && <p className="text-sm text-red-400">{error}</p>}
          <textarea
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="I need to monitor pod restart spikes in our payments namespace. Alert me when there are more than 5 restarts in 10 minutes for any pod in that namespace."
            rows={3}
            className="w-full resize-none rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-3 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-zinc-600 focus:outline-none"
          />
          <div className="flex items-center justify-between text-xs text-zinc-500">
            <span>⌘+Enter to submit</span>
            <button
              type="button"
              onClick={() => void handleSubmit()}
              disabled={submitting || !prompt.trim()}
              className="rounded-md bg-zinc-100 px-4 py-1.5 text-sm font-medium text-zinc-900 transition-opacity disabled:opacity-40"
            >
              {submitting ? "Starting…" : "Build"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
