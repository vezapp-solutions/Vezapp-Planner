"use client";

import { useState, type ReactNode } from "react";

import { Issues } from "@/components/Explain";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { SlideOver } from "@/components/SlideOver";
import { RecordForm, FormError, toDraft, toPayload, type Draft, type FieldSpec } from "@/components/forms";
import { ApiError, del, fieldErrors, patch, post } from "@/lib/api";
import type { Issue, Page } from "@/lib/types";
import { useApi } from "@/lib/use-api";

export interface Column<T> {
  header: string;
  cell: (row: T) => ReactNode;
  className?: string;
}

export interface CrudProps<T extends { id: number }> {
  path: string;
  query?: string;
  noun: string;
  fields: FieldSpec[];
  columns: Column<T>[];
  canEdit: boolean;
  defaults?: Draft;
  emptyHint?: string;
  warnings?: (row: T) => Issue[];
  renderExtra?: (ctx: { row: T | null; draft: Draft; setDraft: (d: Draft) => void; reload: () => void }) => ReactNode;
  adjustPayload?: (payload: Record<string, unknown>, draft: Draft, row: T | null) => Record<string, unknown>;
  /** Draft values that do not come straight from a row field (for example, ids pulled out of a nested list). */
  extraDraft?: (row: T | null) => Draft;
  toolbar?: ReactNode;
  subtitle?: (row: T) => string;
  canDelete?: (row: T) => boolean;
  wide?: boolean;
  onChanged?: () => void;
}

export function CrudScreen<T extends { id: number }>(props: CrudProps<T>) {
  const { path, query = "", noun, fields, columns, canEdit, defaults, emptyHint, warnings, renderExtra, adjustPayload, extraDraft, toolbar, subtitle, canDelete, wide, onChanged } = props;
  const list = useApi<Page<T>>(`${path}?page_size=500${query}`);

  // undefined: closed, null: adding, row: editing
  const [editing, setEditing] = useState<T | null | undefined>(undefined);
  const [draft, setDraft] = useState<Draft>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  function open(row: T | null) {
    setDraft({ ...toDraft(row as Record<string, unknown> | null, fields, defaults), ...extraDraft?.(row) });
    setErrors({});
    setFormError(null);
    setConfirmDelete(false);
    setEditing(row);
  }

  const close = () => setEditing(undefined);

  async function save() {
    setBusy(true);
    setErrors({});
    setFormError(null);
    try {
      let payload = toPayload(draft, fields);
      if (adjustPayload) payload = adjustPayload(payload, draft, editing ?? null);
      if (editing) await patch(`${path}/${editing.id}`, payload);
      else await post(path, payload);
      close();
      list.reload();
      onChanged?.();
    } catch (err) {
      const fe = fieldErrors(err);
      const known = new Set(fields.map((f) => f.key));
      setErrors(fe);
      const stray = Object.entries(fe).filter(([k]) => !known.has(k));
      setFormError(
        err instanceof ApiError && !Object.keys(fe).length
          ? err.message
          : stray.length
            ? stray.map(([k, v]) => (k === "detail" || k === "non_field_errors" ? v : `${k}: ${v}`)).join(" ")
            : "Please fix the highlighted fields.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!editing) return;
    setBusy(true);
    try {
      await del(`${path}/${editing.id}`);
      close();
      list.reload();
      onChanged?.();
    } catch (err) {
      setFormError(err instanceof ApiError ? (fieldErrors(err).detail ?? err.message) : "Could not delete.");
      setConfirmDelete(false);
    } finally {
      setBusy(false);
    }
  }

  const rows = list.data?.results ?? [];
  const current = editing ?? null;

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">{toolbar}</div>
        {canEdit && (
          <button type="button" className="btn btn-primary" onClick={() => open(null)}>
            Add {noun}
          </button>
        )}
      </div>

      {list.loading ? (
        <LoadingState label={`Loading ${noun}s`} rows={4} />
      ) : list.error ? (
        <ErrorState message={list.error.message} onRetry={list.reload} />
      ) : rows.length === 0 ? (
        <EmptyState
          title={`No ${noun}s yet`}
          action={canEdit ? <button type="button" className="btn btn-primary" onClick={() => open(null)}>Add {noun}</button> : undefined}
        >
          {emptyHint}
        </EmptyState>
      ) : (
        <div className="panel overflow-x-auto">
          <table className="w-full min-w-[32rem] text-left text-sm">
            <thead className="border-b border-line bg-sunken text-ink-soft">
              <tr>
                {columns.map((c) => (
                  <th key={c.header} scope="col" className={`px-4 py-2 font-medium ${c.className ?? ""}`}>
                    {c.header}
                  </th>
                ))}
                <th scope="col" className="w-20 px-4 py-2" />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-b border-line last:border-0 hover:bg-sunken/60">
                  {columns.map((c, i) => (
                    <td key={c.header} className={`px-4 py-2 ${c.className ?? ""}`}>
                      {i === 0 ? (
                        <button type="button" className="inline-flex min-h-6 min-w-6 items-center text-left font-medium underline-offset-2 hover:underline" onClick={() => open(row)}>
                          {c.cell(row)}
                        </button>
                      ) : (
                        c.cell(row)
                      )}
                    </td>
                  ))}
                  <td className="px-4 py-2 text-right">
                    <button type="button" className="text-sm inline-flex min-h-6 items-center text-link underline-offset-2 hover:underline" onClick={() => open(row)}>
                      {canEdit ? "Edit" : "View"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editing !== undefined && (
        <SlideOver
          wide={wide}
          title={current ? `${canEdit ? "Edit" : "View"} ${noun}` : `Add ${noun}`}
          subtitle={current && subtitle ? subtitle(current) : undefined}
          onClose={close}
          footer={
            <>
              {canEdit && (
                <button type="button" className="btn btn-primary" onClick={save} disabled={busy}>
                  {busy ? "Saving…" : "Save"}
                </button>
              )}
              <button type="button" className="btn btn-quiet" onClick={close}>
                {canEdit ? "Cancel" : "Close"}
              </button>
              {canEdit && current && (canDelete?.(current) ?? true) && (
                <span className="ml-auto">
                  {confirmDelete ? (
                    <button type="button" className="btn btn-danger" onClick={remove} disabled={busy}>
                      Yes, delete
                    </button>
                  ) : (
                    <button type="button" className="btn btn-quiet" onClick={() => setConfirmDelete(true)} disabled={busy}>
                      Delete
                    </button>
                  )}
                </span>
              )}
            </>
          }
        >
          <div className="space-y-4">
            <FormError message={formError} />
            {warnings && current && <Issues issues={warnings(current)} />}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (canEdit) void save();
              }}
            >
              <RecordForm fields={fields} draft={draft} setDraft={setDraft} errors={errors} readOnly={!canEdit} idPrefix={`crud-${noun.replaceAll(" ", "-")}`} />
              <button type="submit" className="sr-only" tabIndex={-1}>
                Save
              </button>
            </form>
            {renderExtra?.({ row: current, draft, setDraft, reload: list.reload })}
          </div>
        </SlideOver>
      )}
    </>
  );
}
