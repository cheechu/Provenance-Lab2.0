"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createRun, getRuns } from "@/lib/api";

type RunSummary = {
  run_id: string;
  status: string;
  track: string;
  target_gene: string;
  editor_type: string;
  start_time: string;
  end_time: string | null;
  duration_seconds: number | null;
  benchmark_mode: boolean;
};

export default function RunsPage() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    getRuns()
      .then((data) => setRuns(Array.isArray(data) ? data : []))
      .catch(() => setError("Failed to load runs"))
      .finally(() => setLoading(false));
  }, []);

  async function handleCreateRun() {
    setCreating(true);
    setError(null);
    try {
      const newRun = await createRun();
      router.push(`/runs/${newRun.run_id}`);
    } catch {
      setError("Failed to create run");
      setCreating(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-slate-900">Runs</h1>
          <p className="mt-0.5 text-sm text-slate-500">
            CRISPR base-editor design runs
          </p>
        </div>
        <button
          onClick={handleCreateRun}
          disabled={creating}
          className="flex items-center gap-2 rounded-md bg-teal-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-teal-700 disabled:opacity-50 transition-colors"
        >
          {creating ? "Creating…" : "Create test run"}
        </button>
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {loading && (
        <div className="text-sm text-slate-400 font-mono">Loading…</div>
      )}

      {!loading && !error && runs.length === 0 && (
        <div className="rounded-lg border border-slate-200 bg-white px-6 py-10 text-center">
          <p className="text-sm font-medium text-slate-700">No runs yet</p>
          <p className="mt-1 text-sm text-slate-400">
            Click "Create test run" to submit your first design run.
          </p>
        </div>
      )}

      {!loading && runs.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white overflow-hidden">
          <ul className="divide-y divide-slate-100">
            {runs.map((run) => (
              <li
                key={run.run_id}
                className="flex items-center justify-between px-5 py-4 hover:bg-slate-50 transition-colors"
              >
                <div className="min-w-0">
                  <p className="font-mono text-xs text-slate-500 truncate">
                    {run.run_id}
                  </p>
                  <p className="mt-0.5 text-sm text-slate-700">
                    {run.target_gene} &middot; {run.editor_type} &middot;{" "}
                    <span className="capitalize">{run.track.replace("_", " ")}</span>
                  </p>
                </div>
                <div className="flex items-center gap-4 ml-4 flex-shrink-0">
                  <StatusBadge status={run.status} />
                  <button
                    onClick={() => router.push(`/runs/${run.run_id}`)}
                    className="text-sm font-medium text-teal-700 hover:text-teal-800"
                  >
                    View →
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    completed: "bg-teal-50 text-teal-700",
    failed: "bg-red-50 text-red-700",
    running: "bg-blue-50 text-blue-700",
    pending: "bg-slate-100 text-slate-600",
  };
  return (
    <span
      className={`rounded px-2 py-0.5 text-xs font-medium capitalize ${
        styles[status] ?? "bg-slate-100 text-slate-600"
      }`}
    >
      {status}
    </span>
  );
}
