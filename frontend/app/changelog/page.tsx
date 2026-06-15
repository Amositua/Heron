import Link from "next/link";
import { type AppSummary, getApps } from "@/lib/api";

export default async function ChangelogIndexPage() {
  let apps: AppSummary[] = [];
  let error: string | null = null;
  try {
    apps = await getApps();
  } catch (err) {
    error = err instanceof Error ? err.message : "Failed to load apps";
  }

  return (
    <div className="px-8 py-8">
      <h1 className="mb-6 text-lg font-semibold text-zinc-100">Changelog</h1>

      {error && (
        <div className="rounded-lg border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {!error && apps.length === 0 && <p className="text-sm text-zinc-500">No apps deployed yet.</p>}

      <ul className="flex flex-col gap-2">
        {apps.map((app) => (
          <li key={app.app_name}>
            <Link
              href={`/changelog/${app.app_name}`}
              className="font-mono text-sm text-zinc-200 underline hover:text-zinc-50"
            >
              {app.app_name}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
