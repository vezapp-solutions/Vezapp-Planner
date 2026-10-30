"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { Panel } from "@/components/Panel";
import { ErrorState, FormErrorLine, LoadingState, PageHeader } from "@/components/States";
import { AddChange } from "@/components/whatif/AddChange";
import { ResultPanel } from "@/components/whatif/ResultPanel";
import { ApiError, del, patch, post } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useSession } from "@/lib/store";
import { CHANGE_KIND_LABEL, type AppliedSummary, type ScenarioDetail } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { EFFECT, STATE_TEXT } from "@/lib/whatif";

const messageOf = (err: unknown) => (err instanceof ApiError ? err.message : "Could not reach the server.");

function Details({ scenario, onSaved }: { scenario: ScenarioDetail; onSaved: () => void }) {
  const [name, setName] = useState(scenario.name);
  const [notes, setNotes] = useState(scenario.notes);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const dirty = name !== scenario.name || notes !== scenario.notes;

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await patch(`/scenarios/${scenario.id}`, { name, notes });
      onSaved();
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <label className="text-sm font-medium">
        Name
        <input className="field mt-1" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
      </label>
      <label className="text-sm font-medium">
        Notes
        <input className="field mt-1" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Why you are trying this" />
      </label>
      <div className="flex items-center gap-3 sm:col-span-2">
        <button type="button" className="btn btn-quiet" onClick={save} disabled={!dirty || busy || !name.trim()}>
          {busy ? "Saving…" : "Save name and notes"}
        </button>
        {error && <FormErrorLine message={error} />}
      </div>
    </div>
  );
}

function ApplyBox({ scenario, onApplied }: { scenario: ScenarioDetail; onApplied: (s: ScenarioDetail) => void }) {
  const [open, setOpen] = useState(false);
  const [recalc, setRecalc] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function apply() {
    setBusy(true);
    setError(null);
    try {
      onApplied(await post<ScenarioDetail>(`/scenarios/${scenario.id}/apply`, { recalculate: recalc }));
    } catch (err) {
      setError(messageOf(err));
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button type="button" className="btn btn-primary" onClick={() => setOpen(true)}>
        Apply to the real data…
      </button>
    );
  }
  return (
    <div role="group" aria-label="Confirm apply" className="space-y-3 rounded-md border border-warn bg-warn-wash px-4 py-3">
      <p className="font-medium">Applying makes these changes real, under your name. This cannot be undone with one click.</p>
      <ul className="list-disc space-y-1 pl-5 text-sm">
        {scenario.changes.map((c) => (
          <li key={c.id}>
            <span className="font-medium">{c.text}.</span> <span className="text-ink-soft">{EFFECT[c.kind]}</span>
          </li>
        ))}
      </ul>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" className="size-4 accent-[var(--action)]" checked={recalc} onChange={(e) => setRecalc(e.target.checked)} />
        Recalculate the plan straight away (a confirmed plan is kept; a new plan is started)
      </label>
      {error && <FormErrorLine message={error} />}
      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn btn-primary" onClick={apply} disabled={busy}>
          {busy ? "Applying…" : "Yes, apply"}
        </button>
        <button type="button" className="btn btn-quiet" onClick={() => setOpen(false)} disabled={busy}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function AppliedNote({ scenario, summary }: { scenario: ScenarioDetail; summary?: AppliedSummary }) {
  const parts = summary
    ? [
        summary.downtimes && `${summary.downtimes} blocked period${summary.downtimes === 1 ? "" : "s"}`,
        summary.line_edits && `${summary.line_edits} schedule line edit${summary.line_edits === 1 ? "" : "s"}`,
        summary.adjustments && `${summary.adjustments} extra shift or overtime entr${summary.adjustments === 1 ? "y" : "ies"}`,
      ].filter(Boolean)
    : [];
  return (
    <div role="status" className="space-y-1 rounded-md border border-ok bg-ok-wash px-4 py-3 text-sm">
      <p className="font-medium text-ok">
        Applied{scenario.applied_by_name ? ` by ${scenario.applied_by_name}` : ""}
        {scenario.applied_at ? ` on ${formatDateTime(scenario.applied_at)}` : ""}.
      </p>
      {parts.length > 0 && <p>Created or changed: {parts.join(", ")}.</p>}
      {summary?.plan && (
        <p>
          {summary.plan.new ? `Started plan v${summary.plan.version}` : `Recalculated plan v${summary.plan.version}`}.{" "}
          <Link href="/plan" className="text-link underline-offset-2 hover:underline">Open the plan</Link>
        </p>
      )}
      {summary && !summary.plan && (
        <p>The plan was not recalculated. <Link href="/plan" className="text-link underline-offset-2 hover:underline">Open the plan</Link> to recalculate it.</p>
      )}
    </div>
  );
}

export default function ScenarioPage() {
  const id = useParams<{ id: string }>().id;
  const router = useRouter();
  const [version, setVersion] = useState(0);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<AppliedSummary | undefined>();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const role = useSession((s) => s.user!.role);
  const scenario = useApi<ScenarioDetail>(`/scenarios/${id}?v=${version}`);
  const reload = () => setVersion((v) => v + 1);

  if (scenario.loading) return <LoadingState label="Loading the scenario" rows={4} />;
  if (scenario.error || !scenario.data) return <ErrorState title="Cannot open this scenario" message={scenario.error?.message ?? "Not found."} onRetry={reload} />;
  const s = scenario.data;
  const draft = s.status === "draft";
  const canEdit = role !== "viewer" && draft;
  const stale = s.state === "changes_edited" || s.state === "data_changed";

  async function run() {
    setRunning(true);
    setError(null);
    try {
      await post(`/scenarios/${s.id}/run`);
      reload();
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setRunning(false);
    }
  }

  async function removeChange(changeId: number) {
    setError(null);
    try {
      await del(`/scenarios/${s.id}/changes/${changeId}`);
      reload();
    } catch (err) {
      setError(messageOf(err));
    }
  }

  async function removeScenario() {
    try {
      await del(`/scenarios/${s.id}`);
      router.push("/what-if");
    } catch (err) {
      setError(messageOf(err));
      setConfirmDelete(false);
    }
  }

  return (
    <>
      <p className="mb-2 text-sm">
        <Link href="/what-if" className="inline-flex min-h-6 items-center text-link underline-offset-2 hover:underline">← What-if</Link>
      </p>
      <PageHeader title={s.name} subtitle={draft ? "Draft scenario · nothing here changes the real data until you apply it" : "Applied scenario · kept as a record"}>
        {canEdit && (
          confirmDelete ? (
            <button type="button" className="btn btn-quiet !border-danger !text-danger" onClick={removeScenario}>Yes, delete scenario</button>
          ) : (
            <button type="button" className="btn btn-quiet" onClick={() => setConfirmDelete(true)}>Delete scenario</button>
          )
        )}
      </PageHeader>

      <div className="space-y-5">
        {!draft && <AppliedNote scenario={s} summary={summary} />}
        {error && <FormErrorLine message={error} />}

        {canEdit && (
          <Panel title="Name and notes">
            <Details key={`${s.name}|${s.notes}`} scenario={s} onSaved={reload} />
          </Panel>
        )}

        <Panel title="Changes" note={`${s.changes.length} in this scenario`}>
          {s.changes.length === 0 ? (
            <p className="text-sm text-ink-soft">No changes yet. Add one below.</p>
          ) : (
            <ol className="divide-y divide-line rounded-md border border-line text-sm">
              {s.changes.map((c) => (
                <li key={c.id} className="flex items-center justify-between gap-3 px-3 py-2">
                  <span>
                    <span className="mr-2 rounded-sm bg-sunken px-1.5 py-0.5 text-xs text-ink-soft">{CHANGE_KIND_LABEL[c.kind]}</span>
                    {c.text}
                  </span>
                  {canEdit && (
                    <button type="button" className="shrink-0 inline-flex min-h-6 items-center text-link underline-offset-2 hover:underline" onClick={() => void removeChange(c.id)} aria-label={`Remove: ${c.text}`}>
                      Remove
                    </button>
                  )}
                </li>
              ))}
            </ol>
          )}
          {canEdit && (
            <div className="mt-4 border-t border-line pt-4">
              <AddChange scenarioId={s.id} onAdded={reload} />
            </div>
          )}
        </Panel>

        {canEdit && (
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" className="btn btn-primary" onClick={run} disabled={running || s.changes.length === 0}>
              {running ? "Running both plans…" : s.last_run_at ? "Run again" : "Run scenario"}
            </button>
            {s.changes.length === 0 && <span className="text-sm text-ink-soft">Add at least one change to run it.</span>}
          </div>
        )}

        {STATE_TEXT[s.state] && draft && s.state !== "never_run" && (
          <div role="status" className="rounded-md border border-warn bg-warn-wash px-4 py-2 text-sm">
            <span className="font-medium text-warn">Result out of date.</span> {STATE_TEXT[s.state]}
          </div>
        )}

        {s.result?.diff && (
          <Panel title="What changes" note={s.last_run_at ? `run ${formatDateTime(s.last_run_at)}` : undefined}>
            <ResultPanel result={s.result} ranAt={s.last_run_at} stale={stale && draft} />
          </Panel>
        )}

        {canEdit && s.state === "fresh" && (
          <Panel title="Apply">
            <p className="mb-3 text-sm text-ink-soft">
              Applying writes the changes above to the real schedule and masters so that every plan uses them. Only a result that matches today&apos;s data can be applied.
            </p>
            <ApplyBox
              scenario={s}
              onApplied={(done) => {
                setSummary(done.applied_summary);
                reload();
              }}
            />
          </Panel>
        )}
      </div>
    </>
  );
}
