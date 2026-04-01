"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { getRunById } from "@/lib/api";

type StepTrace = {
  step_name: string;
  start_time: string;
  end_time: string | null;
  exit_status: number;
  docker_image: string;
  command_args: string[];
  seed_used: number | null;
};

type RunManifest = {
  run_id: string;
  status: string;
  track: string;
  start_time: string;
  end_time: string | null;
  duration_seconds: number | null;
  instrument_name: string;
  instrument_version: string;
  git_sha: string;
  docker_image: string;
  benchmark_mode: boolean;
  inputs_digest: string;
  step_traces: StepTrace[];
  run_request: {
    guide_rna: {
      sequence: string;
      pam: string;
      target_gene: string;
    };
    editor_config: {
      editor_type: string;
    };
    track: string;
  };
};

export default function RunDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const router = useRouter();

  const [run, setRun] = useState<RunManifest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    getRunById(id)
      .then(setRun)
      .catch(() => setError("Run not found or failed to load"))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return <div className="text-sm text-slate-400 font-mono mt-2">Loading…</div>;
  }

  if (error || !run) {
    return (
      <div className="space-y-4">
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error ?? "Run not found"}
        </div>
        <button
          onClick={() => router.push("/runs")}
          className="text-sm font-medium text-teal-700 hover:text-teal-800"
        >
          ← Back to runs
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-3xl">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <button
            onClick={() => router.push("/runs")}
            className="text-xs font-mono text-slate-400 hover:text-slate-600 mb-2 block"
          >
            ← runs
          </button>
          <h1 className="text-lg font-semibold text-slate-900">Run detail</h1>
        </div>
        <StatusBadge status={run.status} />
      </div>

      {/* Identity */}
      <Section title="Identity">
        <Field label="Run ID">
          <span className="font-mono text-xs text-slate-700">{run.run_id}</span>
        </Field>
        <Field label="Status">
          <span className="capitalize">{run.status}</span>
        </Field>
        <Field label="Track">
          <span className="capitalize">{run.track.replace(/_/g, " ")}</span>
        </Field>
        <Field label="Benchmark mode">{run.benchmark_mode ? "Yes" : "No"}</Field>
        <Field label="Inputs digest">
          <span className="font-mono text-xs text-slate-600 break-all">
            {run.inputs_digest}
          </span>
        </Field>
      </Section>

      {/* Timing */}
      <Section title="Timing">
        <Field label="Started">{formatDate(run.start_time)}</Field>
        <Field label="Ended">
          {run.end_time ? formatDate(run.end_time) : "—"}
        </Field>
        <Field label="Duration">
          {run.duration_seconds != null
            ? `${run.duration_seconds.toFixed(2)}s`
            : "—"}
        </Field>
      </Section>

      {/* Inputs */}
      <Section title="Inputs">
        <Field label="Target gene">
          {run.run_request.guide_rna.target_gene}
        </Field>
        <Field label="Sequence">
          <span className="font-mono text-xs tracking-widest text-slate-700">
            {run.run_request.guide_rna.sequence}
          </span>
        </Field>
        <Field label="PAM">{run.run_request.guide_rna.pam}</Field>
        <Field label="Editor type">
          {run.run_request.editor_config.editor_type}
        </Field>
      </Section>

      {/* Orchestration — Prefect not integrated in backend */}
      <Section title="Orchestration">
        <div className="px-5 py-4 space-y-3">
          <p className="text-xs text-slate-500">
            <span className="font-medium text-slate-700">Prefect flow status</span>
            {" — "}not available. The backend does not yet expose a Prefect
            flow ID or flow run status. Step traces are shown below as the
            current execution record.
          </p>
          {run.step_traces.length === 0 ? (
            <p className="text-xs text-slate-400 font-mono">No step traces recorded.</p>
          ) : (
            <ul className="space-y-2">
              {run.step_traces.map((step, i) => (
                <li
                  key={i}
                  className="rounded border border-slate-100 bg-slate-50 px-3 py-2 text-xs font-mono"
                >
                  <div className="flex items-center justify-between gap-4">
                    <span className="text-slate-800 font-medium">{step.step_name}</span>
                    <ExitBadge code={step.exit_status} />
                  </div>
                  <div className="mt-1 text-slate-400">
                    {formatDate(step.start_time)}
                    {step.end_time ? ` → ${formatDate(step.end_time)}` : " → running"}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Section>

      {/* Environment */}
      <Section title="Environment">
        <Field label="Instrument">
          {run.instrument_name} v{run.instrument_version}
        </Field>
        <Field label="Git SHA">
          <span className="font-mono text-xs text-slate-600">{run.git_sha}</span>
        </Field>
        <Field label="Docker image">
          <span className="font-mono text-xs text-slate-600">{run.docker_image}</span>
        </Field>
      </Section>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white overflow-hidden">
      <div className="border-b border-slate-100 px-5 py-3">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
          {title}
        </h2>
      </div>
      <dl className="divide-y divide-slate-100">{children}</dl>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline gap-4 px-5 py-3">
      <dt className="w-36 flex-shrink-0 text-xs font-medium text-slate-500">
        {label}
      </dt>
      <dd className="text-sm text-slate-800 min-w-0">{children}</dd>
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
      className={`rounded px-2.5 py-1 text-xs font-medium capitalize ${
        styles[status] ?? "bg-slate-100 text-slate-600"
      }`}
    >
      {status}
    </span>
  );
}

function ExitBadge({ code }: { code: number }) {
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
        code === 0 ? "bg-teal-50 text-teal-700" : "bg-red-50 text-red-700"
      }`}
    >
      exit {code}
    </span>
  );
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}
