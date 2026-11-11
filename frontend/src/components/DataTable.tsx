import {
  type ColumnDef,
  type SortingState,
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { Fragment, type ReactNode, useState } from "react";
import { Hint } from "./Hint";

export interface ColumnMeta {
  hint?: string;
  csv?: (row: never) => string | number | null | undefined;
  align?: "right" | "left";
}

function toCsv<T>(rows: T[], columns: ColumnDef<T, unknown>[]): string {
  const cols = columns.filter((c) => (c.meta as ColumnMeta | undefined)?.csv);
  const esc = (v: unknown) => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const header = cols.map((c) => esc(typeof c.header === "string" ? c.header : c.id));
  const body = rows.map((r) => cols.map((c) => esc((c.meta as ColumnMeta).csv!(r as never))).join(","));
  return [header.join(","), ...body].join("\n");
}

export function downloadCsv<T>(name: string, rows: T[], columns: ColumnDef<T, unknown>[]) {
  const blob = new Blob([toCsv(rows, columns)], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${name}-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

export function DataTable<T>({
  rows, columns, sorting, onSortingChange, onRowClick, rowClass, expand, pageSize = 50, empty,
}: {
  rows: T[];
  columns: ColumnDef<T, unknown>[];
  sorting: SortingState;
  onSortingChange: (s: SortingState) => void;
  onRowClick?: (row: T) => void;
  rowClass?: (row: T) => string;
  expand?: (row: T) => ReactNode;
  pageSize?: number;
  empty?: ReactNode;
}) {
  const [open, setOpen] = useState<Set<number>>(new Set());
  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting },
    onSortingChange: (u) => onSortingChange(typeof u === "function" ? u(sorting) : u),
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize } },
    sortDescFirst: true,
  });
  const pages = table.getPageCount();

  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => {
                const meta = h.column.columnDef.meta as ColumnMeta | undefined;
                const dir = h.column.getIsSorted();
                return (
                  <th key={h.id} className={meta?.align === "left" ? "left" : ""}>
                    <span
                      className={h.column.getCanSort() ? "sortable" : ""}
                      onClick={h.column.getToggleSortingHandler()}
                    >
                      {flexRender(h.column.columnDef.header, h.getContext())}
                      {dir === "asc" ? " ▲" : dir === "desc" ? " ▼" : ""}
                    </span>
                    {meta?.hint && <Hint text={meta.hint} />}
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <Fragment key={row.id}>
              <tr
                className={`${onRowClick || expand ? "clickable" : ""} ${rowClass ? rowClass(row.original) : ""}`}
                onClick={() => {
                  if (expand) {
                    const next = new Set(open);
                    next.has(row.index) ? next.delete(row.index) : next.add(row.index);
                    setOpen(next);
                  } else onRowClick?.(row.original);
                }}
              >
                {row.getVisibleCells().map((cell) => {
                  const meta = cell.column.columnDef.meta as ColumnMeta | undefined;
                  return (
                    <td key={cell.id} className={meta?.align === "left" ? "left" : ""}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  );
                })}
              </tr>
              {expand && open.has(row.index) && (
                <tr className="expanded">
                  <td colSpan={row.getVisibleCells().length}>{expand(row.original)}</td>
                </tr>
              )}
            </Fragment>
          ))}
          {!rows.length && (
            <tr>
              <td colSpan={columns.length} className="empty">{empty ?? "Nothing to show."}</td>
            </tr>
          )}
        </tbody>
      </table>
      {pages > 1 && (
        <div className="pager">
          <button disabled={!table.getCanPreviousPage()} onClick={() => table.previousPage()}>Previous</button>
          <span>
            Page {table.getState().pagination.pageIndex + 1} of {pages} ({rows.length} rows)
          </span>
          <button disabled={!table.getCanNextPage()} onClick={() => table.nextPage()}>Next</button>
        </div>
      )}
    </div>
  );
}
