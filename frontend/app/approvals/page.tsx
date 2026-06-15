"use client";

import { useEffect, useState } from "react";
import { approveProposal, getPendingProposals, type Proposal, rejectProposal } from "@/lib/api";

const RISK_STYLES: Record<string, string> = {
  low: "border-emerald-700 text-emerald-400",
  medium: "border-amber-700 text-amber-400",
  high: "border-red-700 text-red-400",
};

export default function ApprovalsPage() {
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    try {
      setProposals(await getPendingProposals());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load proposals");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, []);

  async function handleApprove(id: string) {
    setBusy(id);
    try {
      await approveProposal(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Approve failed");
    } finally {
      setBusy(null);
    }
  }

  async function handleReject(id: string) {
    const reason = window.prompt("Reason for rejecting this proposal:");
    if (reason === null) return;
    setBusy(id);
    try {
      await rejectProposal(id, reason);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reject failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="px-8 py-8">
      <h1 className="mb-6 text-lg font-semibold text-zinc-100">Approvals</h1>

      {error && (
        <div className="mb-4 rounded-lg border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {!loading && proposals.length === 0 && !error && (
        <p className="text-sm text-zinc-500">No proposals are waiting for review.</p>
      )}

      <ul className="flex flex-col gap-3">
        {proposals.map((proposal) => (
          <li key={proposal.id} className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
            <div className="mb-2 flex items-center gap-2">
              <span className="font-mono text-sm text-zinc-100">{proposal.app_name}</span>
              <span className="rounded-full border border-zinc-700 px-2 py-0.5 text-xs text-zinc-300">
                {proposal.change_type}
              </span>
              <span
                className={`rounded-full border px-2 py-0.5 text-xs ${
                  RISK_STYLES[proposal.risk_level] ?? "border-zinc-700 text-zinc-400"
                }`}
              >
                {proposal.risk_level} risk
              </span>
            </div>
            <p className="mb-3 text-sm text-zinc-300">{proposal.rationale}</p>
            <p className="mb-3 font-mono text-sm text-zinc-400">
              {JSON.stringify(proposal.current_value)} → {JSON.stringify(proposal.proposed_value)}
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => void handleApprove(proposal.id)}
                disabled={busy === proposal.id}
                className="rounded-md bg-zinc-100 px-3 py-1.5 text-xs font-medium text-zinc-900 disabled:opacity-40"
              >
                Approve
              </button>
              <button
                type="button"
                onClick={() => void handleReject(proposal.id)}
                disabled={busy === proposal.id}
                className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 disabled:opacity-40"
              >
                Reject
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
