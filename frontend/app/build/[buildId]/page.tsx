"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { CodeBlock } from "@/components/CodeBlock";
import { API_BASE_URL } from "@/lib/api";

const STAGES = ["planning", "generating", "deploying", "validating", "done"] as const;
type Stage = (typeof STAGES)[number];

const STAGE_LABELS: Record<Stage, string> = {
  planning: "Planning",
  generating: "Generating",
  deploying: "Deploying",
  validating: "Validating",
  done: "Done",
};

interface FileEntry {
  filename: string;
  content: string;
}

interface ValidationStep {
  name: string;
  passed: boolean;
  detail: string;
}

interface McpAction {
  action: string;
  target: string;
}

interface CompleteData {
  app_name: string;
  app_path: string;
}

export default function BuildPage() {
  const params = useParams<{ buildId: string }>();
  const buildId = params.buildId;

  const [stage, setStage] = useState<Stage>("planning");
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [mcpActions, setMcpActions] = useState<McpAction[]>([]);
  const [validationSteps, setValidationSteps] = useState<ValidationStep[]>([]);
  const [complete, setComplete] = useState<CompleteData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const source = new EventSource(`${API_BASE_URL}/api/build/stream/${buildId}`);

    source.addEventListener("stage_change", (event) => {
      const data = JSON.parse((event as MessageEvent).data) as { stage: Stage };
      setStage(data.stage);
    });

    source.addEventListener("file_written", (event) => {
      const data = JSON.parse((event as MessageEvent).data) as FileEntry;
      setFiles((prev) => [...prev, data]);
      setActiveFile(data.filename);
    });

    source.addEventListener("mcp_action", (event) => {
      const data = JSON.parse((event as MessageEvent).data) as McpAction;
      setMcpActions((prev) => [...prev, data]);
    });

    source.addEventListener("validation_step", (event) => {
      const data = JSON.parse((event as MessageEvent).data) as ValidationStep;
      setValidationSteps((prev) => [...prev, data]);
    });

    source.addEventListener("complete", (event) => {
      const data = JSON.parse((event as MessageEvent).data) as CompleteData;
      setComplete(data);
      source.close();
    });

    source.addEventListener("error", (event) => {
      const messageEvent = event as MessageEvent;
      if (messageEvent.data) {
        const data = JSON.parse(messageEvent.data) as { message: string };
        setError(data.message);
      } else {
        setError("Lost connection to the build stream.");
      }
      source.close();
    });

    return () => source.close();
  }, [buildId]);

  const planFile = files.find((f) => f.filename === "build_plan.json");
  const generatedFiles = files.filter((f) => f.filename !== "build_plan.json");
  const activeGeneratedFile =
    generatedFiles.find((f) => f.filename === activeFile) ?? generatedFiles[generatedFiles.length - 1];

  const stageIndex = STAGES.indexOf(stage);

  return (
    <div className="flex min-h-screen">
      <div className="w-56 flex-shrink-0 border-r border-zinc-800 px-6 py-8">
        <h1 className="mb-6 text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Build progress
        </h1>
        <ol className="flex flex-col gap-3">
          {STAGES.map((s, index) => {
            const isCurrent = s === stage && !error;
            const isPast = index < stageIndex || (!!complete && index <= stageIndex);
            return (
              <li key={s} className="flex items-center gap-3 text-sm">
                <span
                  className={`flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full border text-xs ${
                    isCurrent
                      ? "border-zinc-100 bg-zinc-100 text-zinc-900"
                      : isPast
                        ? "border-emerald-700 bg-emerald-900/40 text-emerald-400"
                        : "border-zinc-700 text-zinc-600"
                  }`}
                >
                  {isPast ? "✓" : index + 1}
                </span>
                <span className={isCurrent ? "font-medium text-zinc-100" : "text-zinc-500"}>
                  {STAGE_LABELS[s]}
                </span>
              </li>
            );
          })}
        </ol>
      </div>

      <div className="min-w-0 flex-1 overflow-y-auto px-8 py-8">
        <div className="mx-auto flex max-w-3xl flex-col gap-8">
          {error && (
            <div className="rounded-lg border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
              {error}
            </div>
          )}

          {planFile && (
            <Section title="Build plan">
              <CodeBlock filename={planFile.filename} content={planFile.content} />
            </Section>
          )}

          {generatedFiles.length > 0 && (
            <Section title="Generated files">
              <div className="flex gap-4">
                <ul className="w-52 flex-shrink-0 overflow-hidden rounded-lg border border-zinc-800">
                  {generatedFiles.map((file) => (
                    <li key={file.filename}>
                      <button
                        type="button"
                        onClick={() => setActiveFile(file.filename)}
                        className={`block w-full truncate px-3 py-2 text-left font-mono text-xs ${
                          activeGeneratedFile?.filename === file.filename
                            ? "bg-zinc-800 text-zinc-100"
                            : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
                        }`}
                      >
                        {file.filename}
                      </button>
                    </li>
                  ))}
                </ul>
                {activeGeneratedFile && (
                  <div className="min-w-0 flex-1">
                    <CodeBlock filename={activeGeneratedFile.filename} content={activeGeneratedFile.content} />
                  </div>
                )}
              </div>
            </Section>
          )}

          {mcpActions.length > 0 && (
            <Section title="Deployment (MCP audit log)">
              <ul className="flex flex-col gap-1 rounded-lg border border-zinc-800 bg-zinc-900 p-4 font-mono text-xs text-zinc-300">
                {mcpActions.map((action, index) => (
                  <li key={index}>
                    <span className="text-emerald-400">→</span> {action.action}{" "}
                    <span className="text-zinc-500">{action.target}</span>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {validationSteps.length > 0 && (
            <Section title="Validation">
              <ul className="flex flex-col gap-2">
                {validationSteps.map((step, index) => (
                  <li key={index} className="flex items-start gap-2 text-sm">
                    <span className={step.passed ? "text-emerald-400" : "text-red-400"}>
                      {step.passed ? "✓" : "✗"}
                    </span>
                    <div>
                      <p className="font-medium text-zinc-200">{step.name}</p>
                      <p className="text-zinc-500">{step.detail}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {complete && (
            <div className="rounded-lg border border-emerald-900 bg-emerald-950/30 px-4 py-4 text-sm text-emerald-300">
              <p className="mb-2 font-medium">Build complete — {complete.app_name}</p>
              <Link href="/apps" className="underline">
                View in Apps
              </Link>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">{title}</h2>
      {children}
    </section>
  );
}
