"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { type ChangelogEntry, getChangelog, rollback } from "@/lib/api";

const CHANGE_TYPE_LABELS: Record<string, string> = {
  alert_threshold: "Auto-tuned",
  rollback: "Rollback",
  spl_rewrite: "SPL rewrite",
  panel_add: "Panel added",
  schema_update: "Schema update",
};

export default function ChangelogPage() {
  const params = useParams<{ appName: string }>();
  const appName = params.appName;

  const [entries, setEntries] = useState<ChangelogEntry[]>([]);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [rollingBack, setRollingBack] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    try {
      setEntries(await getChangelog(appName));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load changelog");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appName]);

  function toggle(id: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleRollback(entry: ChangelogEntry) {
    setRollingBack(entry.id);
    try {
      await rollback(appName, entry.before_version);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rollback failed");
    } finally {
      setRollingBack(null);
    }
  }

  return (
    <div className="px-8 py-8">
      <h1 className="mb-6 text-lg font-semibold text-zinc-100">
        Changelog <span className="font-mono text-zinc-400">— {appName}</span>
      </h1>

      {error && (
        <div className="mb-4 rounded-lg border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {!loading && entries.length === 0 && !error && (
        <p className="text-sm text-zinc-500">No changes recorded yet.</p>
      )}

      <ul className="flex flex-col gap-3">
        {entries.map((entry) => {
          const isExpanded = expanded.has(entry.id);
          return (
            <li key={entry.id} className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="mb-1 flex items-center gap-2">
                    <span className="rounded-full border border-zinc-700 px-2 py-0.5 text-xs text-zinc-300">
                      {CHANGE_TYPE_LABELS[entry.change_type] ?? entry.change_type}
                    </span>
                    {entry.rolled_back && (
                      <span className="rounded-full border border-amber-700 px-2 py-0.5 text-xs text-amber-400">
                        rolled back
                      </span>
                    )}
                    <span className="text-xs text-zinc-500">{new Date(entry.applied_at).toLocaleString()}</span>
                  </div>
                  <p className="text-sm text-zinc-200">{entry.message}</p>
                </div>
                <div className="flex flex-shrink-0 flex-col items-end gap-2 sm:flex-row">
                  <button
                    type="button"
                    onClick={() => toggle(entry.id)}
                    className="text-xs text-zinc-400 underline hover:text-zinc-200"
                  >
                    {isExpanded ? "Hide diff" : "Show diff"}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleRollback(entry)}
                    disabled={rollingBack === entry.id}
                    className="text-xs text-zinc-400 underline hover:text-zinc-200 disabled:opacity-40"
                  >
                    {rollingBack === entry.id ? "Rolling back…" : "Rollback to before this change"}
                  </button>
                </div>
              </div>
              {isExpanded && (
                <div className="mt-3 grid grid-cols-2 gap-3 font-mono text-xs">
                  <div className="rounded-md border border-zinc-800 bg-zinc-950 p-3">
                    <p className="mb-1 text-zinc-500">Before (v{entry.before_version})</p>
                    <pre className="whitespace-pre-wrap text-zinc-300">
                      {JSON.stringify(entry.previous_value, null, 2)}
                    </pre>
                  </div>
                  <div className="rounded-md border border-zinc-800 bg-zinc-950 p-3">
                    <p className="mb-1 text-zinc-500">After (v{entry.after_version})</p>
                    <pre className="whitespace-pre-wrap text-zinc-300">
                      {JSON.stringify(entry.new_value, null, 2)}
                    </pre>
                  </div>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
