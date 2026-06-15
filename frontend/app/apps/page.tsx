import Link from "next/link";
import { type AppSummary, getApps } from "@/lib/api";

export default async function AppsPage() {
  let apps: AppSummary[] = [];
  let error: string | null = null;
  try {
    apps = await getApps();
  } catch (err) {
    error = err instanceof Error ? err.message : "Failed to load apps";
  }

  return (
    <div className="px-8 py-8">
      <h1 className="mb-6 text-lg font-semibold text-zinc-100">Apps</h1>

      {error && (
        <div className="rounded-lg border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {!error && apps.length === 0 && (
        <p className="text-sm text-zinc-500">No apps deployed yet. Build one from Chat.</p>
      )}

      {!error && apps.length > 0 && (
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-zinc-800 text-xs uppercase tracking-wide text-zinc-500">
              <th className="py-2 font-medium">App name</th>
              <th className="py-2 font-medium">Current version</th>
              <th className="py-2 font-medium">Last modified</th>
              <th className="py-2 font-medium" />
            </tr>
          </thead>
          <tbody>
            {apps.map((app) => (
              <tr key={app.app_name} className="border-b border-zinc-900">
                <td className="py-3 font-mono text-zinc-100">{app.app_name}</td>
                <td className="py-3 text-zinc-300">v{app.current_version}</td>
                <td className="py-3 text-zinc-400">{new Date(app.last_changed_at).toLocaleString()}</td>
                <td className="py-3 text-right">
                  <Link href={`/changelog/${app.app_name}`} className="text-zinc-400 underline hover:text-zinc-200">
                    View Changelog
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
