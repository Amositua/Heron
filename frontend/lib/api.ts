export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export interface AppSummary {
  app_name: string;
  current_version: number;
  last_changed_at: string;
}

export interface ChangelogEntry {
  id: number;
  proposal_id: string | null;
  app_name: string;
  change_type: string;
  target: Record<string, unknown>;
  previous_value: unknown;
  new_value: unknown;
  message: string;
  before_version: number;
  after_version: number;
  applied_at: string;
  rolled_back: boolean;
}

export interface Proposal {
  id: string;
  app_name: string;
  change_type: "alert_threshold" | "spl_rewrite" | "panel_add" | "schema_update";
  target: Record<string, unknown>;
  current_value: unknown;
  proposed_value: unknown;
  rationale: string;
  risk_level: "low" | "medium" | "high";
  created_at: string;
  status: "pending" | "approved" | "rejected" | "applied";
}

export interface ApplyResult {
  success: boolean;
  proposal_id: string;
  app_name: string;
  before_version: number | null;
  after_version: number | null;
  changelog_message: string | null;
  error: string | null;
}

export interface RollbackResult {
  success: boolean;
  app_name: string;
  restored_version: number | null;
  new_version: number | null;
  changelog_message: string | null;
  error: string | null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    ...init,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${init?.method ?? "GET"} ${path} failed (${response.status}): ${detail}`);
  }
  return response.json() as Promise<T>;
}

export function startBuild(prompt: string): Promise<{ build_id: string }> {
  return request("/api/build/start", { method: "POST", body: JSON.stringify({ prompt }) });
}

export function getApps(): Promise<AppSummary[]> {
  return request("/api/apps");
}

export function getChangelog(appName: string): Promise<ChangelogEntry[]> {
  return request(`/api/changelog/${appName}`);
}

export function getPendingProposals(): Promise<Proposal[]> {
  return request("/api/proposals?status=pending");
}

export function approveProposal(proposalId: string): Promise<ApplyResult> {
  return request(`/api/proposals/${proposalId}/approve`, { method: "POST" });
}

export function rejectProposal(proposalId: string, reason: string): Promise<{ status: string; proposal_id: string }> {
  return request(`/api/proposals/${proposalId}/reject`, { method: "POST", body: JSON.stringify({ reason }) });
}

export function rollback(appName: string, targetVersionId: number): Promise<RollbackResult> {
  return request("/api/rollback", {
    method: "POST",
    body: JSON.stringify({ app_name: appName, target_version_id: targetVersionId }),
  });
}
