"use client";

import Link from "next/link";
import { useRef, useState } from "react";

import { Panel } from "@/components/Panel";
import { EmptyState, ErrorState, FormErrorLine, LoadingState, PageHeader } from "@/components/States";
import { ApiError, download, fieldErrors, upload } from "@/lib/api";
import { formatDateTime, formatNumber } from "@/lib/format";
import { useSession } from "@/lib/store";
import type { Page, UploadBatch, UploadPreview, UploadRow } from "@/lib/types";
import { useApi } from "@/lib/use-api";

type Mode = "insert" | "upsert";
type Filter = "all" | "error" | "warning";

const ACTION_LABEL: Record<UploadRow["action"], string> = {
  insert: "Add",
  update: "Update",
  skip: "Skip",
  unchanged: "No change",
  error: "Not loaded",
};

const STATUS_STYLE: Record<UploadRow["status"], string> = {
  ok: "bg-ok-wash text-ok",
  warning: "bg-warn-wash text-warn",
  error: "bg-danger-wash text-danger",
};
const STATUS_LABEL: Record<UploadRow["status"], string> = { ok: "Ready", warning: "Check", error: "Error" };
const MAX_SHOWN = 300;

function errorText(err: unknown): string {
  const fe = fieldErrors(err);
  return fe.file ?? fe.mode ?? (err instanceof ApiError ? err.message : "Could not reach the server.");
}

function formOf(file: File, mode: Mode, skipErrors?: boolean) {
  const form = new FormData();
  form.append("file", file);
  form.append("mode", mode);
  if (skipErrors !== undefined) form.append("skip_errors", String(skipErrors));
  return form;
}

function Chip({ tone, children }: { tone: string; children: React.ReactNode }) {
  return <span className={`rounded-sm px-2 py-1 font-mono text-sm ${tone}`}>{children}</span>;
}

function History({ version }: { version: number }) {
  const history = useApi<Page<UploadBatch>>(`/uploads/history?page_size=50&v=${version}`);
  const [error, setError] = useState<string | null>(null);

  return (
    <Panel title="Upload history" note="every committed upload">
      {history.loading ? (
        <LoadingState label="Loading history" rows={2} />
      ) : history.error ? (
        <ErrorState message={history.error.message} onRetry={history.reload} />
      ) : history.data?.results.length === 0 ? (
        <p className="text-sm text-ink-soft">Nothing has been uploaded yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[44rem] text-left text-sm">
            <thead className="border-b border-line text-ink-soft">
              <tr>
                {["When", "Who", "File", "Added", "Updated", "Skipped", "Errors", ""].map((h, i) => (
                  <th key={i} scope="col" className={`px-3 py-1.5 font-medium ${i >= 3 && i <= 6 ? "text-right" : ""}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {history.data?.results.map((b) => (
                <tr key={b.id} className="border-b border-line last:border-0">
                  <td className="whitespace-nowrap px-3 py-1.5 font-mono">{formatDateTime(b.created_at)}</td>
                  <td className="px-3 py-1.5">{b.username || "–"}</td>
                  <td className="px-3 py-1.5">{b.file_name}<span className="ml-1.5 text-xs text-ink-soft">{b.mode === "upsert" ? "add and update" : "add only"}</span></td>
                  <td className="px-3 py-1.5 text-right font-mono">{formatNumber(b.rows_inserted)}</td>
                  <td className="px-3 py-1.5 text-right font-mono">{formatNumber(b.rows_updated)}</td>
                  <td className="px-3 py-1.5 text-right font-mono">{formatNumber(b.rows_skipped + b.rows_unchanged)}</td>
                  <td className="px-3 py-1.5 text-right font-mono">{b.rows_error ? formatNumber(b.rows_error) : "–"}</td>
                  <td className="px-3 py-1.5 text-right">
                    {b.rows_error + b.rows_warning > 0 && (
                      <button
                        type="button"
                        className="inline-flex min-h-6 items-center text-link underline-offset-2 hover:underline"
                        onClick={() => download(`/uploads/history/${b.id}/errors.xlsx`, `upload-${b.id}-problems.xlsx`).catch((e) => setError(errorText(e)))}
                      >
                        Problems (Excel)
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {error && <p role="alert" className="mt-2 text-sm text-danger">{error}</p>}
    </Panel>
  );
}

export default function UploadPage() {
  const role = useSession((s) => s.user!.role);
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<Mode>("insert");
  const [preview, setPreview] = useState<UploadPreview | null>(null);
  const [busy, setBusy] = useState<"preview" | "commit" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [skipErrors, setSkipErrors] = useState(false);
  const [done, setDone] = useState<UploadBatch | null>(null);
  const [version, setVersion] = useState(0);

  if (role === "viewer") {
    return (
      <>
        <PageHeader title="Upload schedule" />
        <EmptyState title="You do not have access to this screen">Only a Planner or Admin can upload a schedule.</EmptyState>
      </>
    );
  }

  async function run(nextFile: File, nextMode: Mode) {
    setBusy("preview");
    setError(null);
    setDone(null);
    setPreview(null);
    setSkipErrors(false);
    setFilter("all");
    try {
      setPreview(await upload<UploadPreview>("/uploads/preview", formOf(nextFile, nextMode)));
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(null);
    }
  }

  function choose(f: File | null) {
    setFile(f);
    if (f) void run(f, mode);
  }

  function changeMode(next: Mode) {
    setMode(next);
    if (file) void run(file, next);
  }

  async function commit() {
    if (!file) return;
    setBusy("commit");
    setError(null);
    try {
      setDone(await upload<UploadBatch>("/uploads/commit", formOf(file, mode, skipErrors)));
      setPreview(null);
      setFile(null);
      if (input.current) input.current.value = "";
      setVersion((v) => v + 1);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(null);
    }
  }

  const s = preview?.summary;
  const shown = preview ? preview.rows.filter((r) => (filter === "all" ? true : r.status === filter)) : [];
  const toSave = s ? s.insert + s.update : 0;
  const blocked = !s || toSave === 0 || (s.error > 0 && !skipErrors) || busy !== null;

  return (
    <>
      <p className="mb-2 text-sm"><Link href="/scheduler" className="inline-flex min-h-6 items-center text-link underline-offset-2 hover:underline">← Monthly Scheduler</Link></p>
      <PageHeader title="Upload schedule" subtitle="Load many dispatch lines from Excel or CSV. You see a preview first and nothing is saved until you confirm." />

      <div className="space-y-6">
        <Panel title="1. Choose a file" actions={
          <button type="button" className="text-sm inline-flex min-h-6 items-center text-link underline-offset-2 hover:underline" onClick={() => download("/uploads/template", "schedule-template.xlsx").catch((e) => setError(errorText(e)))}>
            Download template
          </button>
        }>
          <label htmlFor="schedule-file" className="mb-1 block text-sm font-medium">Excel (.xlsx) or CSV file, up to 5,000 rows</label>
          <input
            ref={input}
            id="schedule-file"
            type="file"
            accept=".xlsx,.csv"
            className="field !py-2 file:mr-3 file:rounded-sm file:border-0 file:bg-sunken file:px-3 file:py-1.5 file:text-sm"
            onChange={(e) => choose(e.target.files?.[0] ?? null)}
            disabled={busy !== null}
          />
          <p className="mt-1 text-xs text-ink-soft">Dates can be DD-MM-YYYY, DD/MM/YYYY or real Excel dates.</p>
          <fieldset className="mt-4">
            <legend className="mb-1 text-sm font-medium">If a line is already in the schedule (same customer, part and date)</legend>
            <label className="flex min-h-9 items-center gap-2 text-sm">
              <input type="radio" name="mode" className="accent-[var(--action)]" checked={mode === "insert"} onChange={() => changeMode("insert")} />
              Leave it alone and add only the new lines
            </label>
            <label className="flex min-h-9 items-center gap-2 text-sm">
              <input type="radio" name="mode" className="accent-[var(--action)]" checked={mode === "upsert"} onChange={() => changeMode("upsert")} />
              Update it with the file&apos;s quantity (blank cells keep what is already recorded)
            </label>
          </fieldset>
        </Panel>

        {busy === "preview" && <LoadingState label="Checking the file" rows={3} />}
        {error && <FormErrorLine message={error} />}

        {done && (
          <div role="status" className="rounded-md border border-ok bg-ok-wash px-4 py-3">
            <p className="font-medium text-ok">Uploaded {done.file_name}</p>
            <p className="mt-1 text-sm">
              {formatNumber(done.rows_inserted)} added, {formatNumber(done.rows_updated)} updated
              {done.rows_skipped + done.rows_unchanged > 0 && `, ${formatNumber(done.rows_skipped + done.rows_unchanged)} left as they were`}
              {done.rows_error > 0 && `, ${formatNumber(done.rows_error)} rows with errors not loaded`}.
            </p>
            <p className="mt-2 text-sm"><Link href="/scheduler" className="font-medium inline-flex min-h-6 items-center text-link underline-offset-2 hover:underline">View the schedule →</Link></p>
          </div>
        )}

        {preview && s && (
          <Panel title="2. Check the preview" note={preview.file_name}>
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2" aria-label="Summary">
                <Chip tone="bg-sunken">{formatNumber(s.total)} rows</Chip>
                <Chip tone={STATUS_STYLE.ok}>{formatNumber(s.ok)} ready</Chip>
                <Chip tone={STATUS_STYLE.warning}>{formatNumber(s.warning)} to check</Chip>
                <Chip tone={STATUS_STYLE.error}>{formatNumber(s.error)} errors</Chip>
              </div>
              <p className="text-sm">
                This will add <strong>{formatNumber(s.insert)}</strong>
                {mode === "upsert" && <>, update <strong>{formatNumber(s.update)}</strong></>}
                {s.skip + s.unchanged > 0 && <>, and leave <strong>{formatNumber(s.skip + s.unchanged)}</strong> as they are</>}
                {s.error > 0 && <>. <strong>{formatNumber(s.error)}</strong> rows with errors will not be loaded</>}.
              </p>

              <div role="group" aria-label="Show rows" className="flex flex-wrap gap-1">
                {([["all", `All (${s.total})`], ["error", `Errors (${s.error})`], ["warning", `To check (${s.warning})`]] as [Filter, string][]).map(([value, text]) => (
                  <button key={value} type="button" aria-pressed={filter === value} onClick={() => setFilter(value)} className={`btn !min-h-8 !px-3 ${filter === value ? "btn-primary" : "btn-quiet"}`}>
                    {text}
                  </button>
                ))}
              </div>

              <div className="max-h-[32rem] overflow-auto rounded-md border border-line">
                <table className="w-full min-w-[56rem] text-left text-sm">
                  <thead className="sticky top-0 border-b border-line bg-sunken text-ink-soft">
                    <tr>
                      {["Row", "Result", "What happens", "Customer", "Part", "Qty", "Internal date", "Problem"].map((h) => (
                        <th key={h} scope="col" className="px-3 py-2 font-medium">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {shown.slice(0, MAX_SHOWN).map((r) => (
                      <tr key={r.row} className="border-b border-line align-top last:border-0">
                        <td className="px-3 py-1.5 font-mono">{r.row}</td>
                        <td className="px-3 py-1.5"><span className={`rounded-sm px-1.5 py-0.5 text-xs ${STATUS_STYLE[r.status]}`}>{STATUS_LABEL[r.status]}</span></td>
                        <td className="px-3 py-1.5">{ACTION_LABEL[r.action]}</td>
                        <td className="px-3 py-1.5">{r.raw.customer_code || r.raw.customer_name || "–"}</td>
                        <td className="px-3 py-1.5">{r.raw.part_number || "–"}</td>
                        <td className="px-3 py-1.5 font-mono">{r.raw.dispatch_qty || "–"}</td>
                        <td className="px-3 py-1.5 font-mono">{r.raw.internal_date || "–"}</td>
                        <td className="px-3 py-1.5">
                          {r.messages.length === 0 ? <span className="text-ink-soft">–</span> : (
                            <ul className="space-y-0.5">
                              {r.messages.map((m, i) => (
                                <li key={i} className={m.level === "error" ? "text-danger" : "text-warn"}>{m.text}</li>
                              ))}
                            </ul>
                          )}
                        </td>
                      </tr>
                    ))}
                    {shown.length === 0 && (
                      <tr><td colSpan={8} className="px-3 py-4 text-center text-ink-soft">No rows in this view.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
              {shown.length > MAX_SHOWN && (
                <p className="text-sm text-ink-soft">Showing the first {MAX_SHOWN} of {formatNumber(shown.length)} rows. The error report lists every problem row.</p>
              )}

              <div className="flex flex-wrap items-center gap-3 border-t border-line pt-4">
                {s.error > 0 && (
                  <label className="flex min-h-10 items-center gap-2 text-sm font-medium">
                    <input type="checkbox" className="size-4 accent-[var(--action)]" checked={skipErrors} onChange={(e) => setSkipErrors(e.target.checked)} />
                    Skip the {formatNumber(s.error)} rows with errors and load the rest
                  </label>
                )}
                <span className="ml-auto flex flex-wrap items-center gap-2">
                  {s.error + s.warning > 0 && file && (
                    <button type="button" className="btn btn-quiet" onClick={() => download("/uploads/error-report", "schedule-upload-problems.xlsx", formOf(file, mode)).catch((e) => setError(errorText(e)))}>
                      Download problems (Excel)
                    </button>
                  )}
                  <button type="button" className="btn btn-primary" onClick={commit} disabled={blocked}>
                    {busy === "commit" ? "Loading…" : `Load ${formatNumber(toSave)} line${toSave === 1 ? "" : "s"} into the schedule`}
                  </button>
                </span>
              </div>
              {s.error > 0 && !skipErrors && <p className="text-sm text-ink-soft">Fix the file and upload it again, or tick the box above to load only the rows that have no errors. Either way, the whole upload is saved together or not at all.</p>}
            </div>
          </Panel>
        )}

        <History version={version} />
      </div>
    </>
  );
}
