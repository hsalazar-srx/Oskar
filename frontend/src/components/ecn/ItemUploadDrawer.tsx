/**
 * ItemUploadDrawer — drag-and-drop bulk item upload for an ECN.
 *
 * States:
 *   idle       → Drop zone with instructions
 *   preview    → Parsed rows table with inline validation errors; Confirm / Cancel
 *   submitting → Spinner while POST /items/bulk is in flight
 *
 * Architecture (from LLM council 2026-06-17):
 * - SheetJS parses client-side for instant preview (raw:false, leading-zero safe)
 * - Header fingerprint check blocks mismatched templates before preview renders
 * - Raw file is sent to backend as multipart/form-data for authoritative validation
 * - Backend is the source of truth — client validation is for UX speed only
 */

import * as React from "react"
import * as DialogPrimitive from "@radix-ui/react-dialog"
import { useDropzone } from "react-dropzone"
import * as XLSX from "xlsx"
import { UploadCloud, X, AlertTriangle, CheckCircle2, FileSpreadsheet } from "lucide-react"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { Badge } from "@/components/ui/badge"
import { parseWorkbook, type ParsedItemRow, type ParseResult } from "@/lib/ecn-item-csv-parser"
import { bulkCreateItems } from "@/api/ecn"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ItemUploadDrawerProps {
  ecnId: string
  customerNumber: string | null
  open: boolean
  onClose: () => void
  onSuccess: () => void
}

type DrawerState = "idle" | "preview" | "submitting"

// ---------------------------------------------------------------------------
// Preview table columns shown to the user
// ---------------------------------------------------------------------------

const PREVIEW_COLS: { key: keyof ParsedItemRow; label: string }[] = [
  { key: "item_number", label: "Item No" },
  { key: "item_name", label: "Item Name" },
  { key: "item_status", label: "Status" },
  { key: "procurement_group", label: "Proc. Group" },
  { key: "product_group", label: "Prod. Group" },
  { key: "unit_of_measure", label: "UoM" },
  { key: "order_type", label: "Order Type" },
  { key: "lead_free_code", label: "Lead Free" },
  { key: "good_receiving_method", label: "Recv. Method" },
  { key: "is_new_item", label: "New?" },
]

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ItemUploadDrawer({ ecnId, customerNumber, open, onClose, onSuccess }: ItemUploadDrawerProps) {
  const [state, setState] = React.useState<DrawerState>("idle")
  const [parseResult, setParseResult] = React.useState<ParseResult | null>(null)
  const [rawFile, setRawFile] = React.useState<File | null>(null)
  const [submitError, setSubmitError] = React.useState<string | null>(null)

  // Reset to idle when drawer is closed
  React.useEffect(() => {
    if (!open) {
      setTimeout(() => {
        setState("idle")
        setParseResult(null)
        setRawFile(null)
        setSubmitError(null)
      }, 200)
    }
  }, [open])

  const onDrop = React.useCallback((acceptedFiles: File[]) => {
    const file = acceptedFiles[0]
    if (!file) return
    setRawFile(file)
    setSubmitError(null)

    const reader = new FileReader()
    reader.onload = (e) => {
      try {
        const data = e.target?.result
        if (!data) return
        const wb = XLSX.read(data, { type: "array", raw: false })
        const result = parseWorkbook(wb, customerNumber ?? undefined)
        setParseResult(result)
        setState("preview")
      } catch {
        setSubmitError("Could not parse the file. Ensure it is a valid .xlsx or .csv.")
        setState("preview")
      }
    }
    reader.readAsArrayBuffer(file)
  }, [customerNumber])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
      "application/vnd.ms-excel": [".xls"],
      "text/csv": [".csv"],
    },
    maxFiles: 1,
    multiple: false,
  })

  // -- Submit ----------------------------------------------------------------
  const handleConfirm = async () => {
    if (!rawFile || !parseResult) return
    setState("submitting")
    setSubmitError(null)
    try {
      await bulkCreateItems(ecnId, rawFile)
      onSuccess()
      onClose()
    } catch (err: unknown) {
      // AxiosError keeps the server body in err.response.data.detail
      const axiosDetail =
        typeof err === "object" && err !== null && "response" in err
          ? (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
          : undefined
      const msg = axiosDetail
        ? String(axiosDetail)
        : err instanceof Error
          ? err.message
          : "Upload failed. Check the errors and try again."
      setSubmitError(msg)
      setState("preview")
    }
  }

  // -- Derived state --------------------------------------------------------
  const hasParseErrors = parseResult
    ? parseResult.missingColumns.length > 0 || parseResult.rows.some((r) => r.errors.length > 0)
    : false
  const validRows = parseResult?.rows.filter((r) => r.errors.length === 0) ?? []
  const errorRows = parseResult?.rows.filter((r) => r.errors.length > 0) ?? []
  const warnRows = parseResult?.rows.filter((r) => r.errors.length === 0 && r.warnings.length > 0) ?? []
  const canConfirm = state === "preview" && !hasParseErrors && validRows.length > 0

  // ---------------------------------------------------------------------------
  return (
    <DialogPrimitive.Root open={open} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/40 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <DialogPrimitive.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-50 -translate-x-1/2 -translate-y-1/2",
            "w-[95vw] max-w-5xl max-h-[90vh] flex flex-col",
            "bg-white rounded-xl shadow-2xl",
            "data-[state=open]:animate-in data-[state=closed]:animate-out",
            "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
            "data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95",
          )}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-100 shrink-0">
            <div>
              <DialogPrimitive.Title className="text-base font-semibold text-neutral-900">
                Upload Items from Spreadsheet
              </DialogPrimitive.Title>
              <DialogPrimitive.Description className="text-xs text-neutral-400 mt-0.5">
                Use the standard Oskar item upload template (.xlsx or .csv)
              </DialogPrimitive.Description>
            </div>
            <DialogPrimitive.Close asChild>
              <button
                className="rounded-md p-1 text-neutral-400 hover:text-neutral-700 hover:bg-neutral-100 transition-colors"
                aria-label="Close"
              >
                <X className="h-4 w-4" />
              </button>
            </DialogPrimitive.Close>
          </div>

          {/* Body — scrollable */}
          <div className="flex-1 overflow-y-auto px-6 py-5">

            {/* ── IDLE: drop zone ── */}
            {state === "idle" && (
              <div className="flex flex-col items-center gap-6">
                <div
                  {...getRootProps()}
                  className={cn(
                    "w-full border-2 border-dashed rounded-xl p-12 flex flex-col items-center gap-3 cursor-pointer transition-colors",
                    isDragActive
                      ? "border-indigo-400 bg-indigo-50"
                      : "border-neutral-200 hover:border-neutral-300 hover:bg-neutral-50",
                  )}
                >
                  <input {...getInputProps()} />
                  <UploadCloud className={cn("h-10 w-10", isDragActive ? "text-indigo-500" : "text-neutral-300")} />
                  <div className="text-center">
                    <p className="text-sm font-medium text-neutral-700">
                      {isDragActive ? "Drop the file here" : "Drag & drop your spreadsheet here"}
                    </p>
                    <p className="text-xs text-neutral-400 mt-1">or click to browse — .xlsx or .csv</p>
                  </div>
                </div>

                <div className="text-xs text-neutral-400 text-center max-w-md">
                  Use the standard Oskar item upload template. Delete the instruction rows (rows 2–6)
                  before uploading. All required columns must be present.
                </div>
              </div>
            )}

            {/* ── PREVIEW: parsed rows ── */}
            {state === "preview" && parseResult && (
              <div className="flex flex-col gap-4">

                {/* Summary bar */}
                <div className="flex items-center gap-3 flex-wrap">
                  {rawFile && (
                    <div className="flex items-center gap-1.5 text-xs text-neutral-500">
                      <FileSpreadsheet className="h-4 w-4 text-neutral-400" />
                      {rawFile.name}
                    </div>
                  )}
                  <Badge variant="default" className="bg-green-100 text-green-800 border-green-200">
                    {validRows.length} valid
                  </Badge>
                  {warnRows.length > 0 && (
                    <Badge variant="default" className="bg-amber-100 text-amber-800 border-amber-200">
                      {warnRows.length} with warnings
                    </Badge>
                  )}
                  {errorRows.length > 0 && (
                    <Badge variant="destructive">
                      {errorRows.length} with errors
                    </Badge>
                  )}
                  {parseResult.skippedRows > 0 && (
                    <span className="text-xs text-neutral-400">{parseResult.skippedRows} instruction rows skipped</span>
                  )}
                </div>

                {/* Missing columns banner */}
                {parseResult.missingColumns.length > 0 && (
                  <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700 flex gap-2">
                    <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                    <div>
                      <p className="font-medium">Wrong template — missing required columns:</p>
                      <p className="mt-0.5">{parseResult.missingColumns.join(", ")}</p>
                      <p className="mt-1 text-xs">Use the standard Oskar item upload template and try again.</p>
                    </div>
                  </div>
                )}

                {/* Error banner */}
                {errorRows.length > 0 && parseResult.missingColumns.length === 0 && (
                  <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700 flex gap-2">
                    <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                    <div>
                      <p className="font-medium">Fix the errors below before uploading.</p>
                      <p className="text-xs mt-0.5">All rows must be valid — correct the spreadsheet and re-upload.</p>
                    </div>
                  </div>
                )}

                {/* Warning banner — shown only when there are warnings but no blocking errors */}
                {warnRows.length > 0 && errorRows.length === 0 && parseResult.missingColumns.length === 0 && (
                  <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-800 flex gap-2">
                    <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                    <div>
                      <p className="font-medium">{warnRows.length} item name{warnRows.length !== 1 ? "s" : ""} will be truncated to 30 characters (MOVEX limit).</p>
                      <p className="text-xs mt-0.5">The full name is preserved in Item Description. Hover the amber cells to see the original.</p>
                    </div>
                  </div>
                )}

                {/* Submit error from backend */}
                {submitError && (
                  <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700 flex gap-2">
                    <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                    <div>
                      <p className="font-medium">Upload failed</p>
                      <p className="mt-0.5">{submitError}</p>
                    </div>
                  </div>
                )}

                {/* Preview table */}
                <div className="rounded-lg border border-neutral-200 overflow-auto max-h-[420px]">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-neutral-50 border-b border-neutral-200 sticky top-0">
                        <th className="px-3 py-2 text-left font-medium text-neutral-500 w-8">#</th>
                        {PREVIEW_COLS.map((col) => (
                          <th key={col.key} className="px-3 py-2 text-left font-medium text-neutral-500 whitespace-nowrap">
                            {col.label}
                          </th>
                        ))}
                        <th className="px-3 py-2 text-left font-medium text-neutral-500">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-neutral-100">
                      {parseResult.rows.map((row) => (
                        <tr
                          key={row.rowIndex}
                          className={cn(
                            row.errors.length > 0
                              ? "bg-red-50"
                              : row.warnings.length > 0
                                ? "bg-amber-50"
                                : "hover:bg-neutral-50",
                          )}
                        >
                          <td className="px-3 py-2 text-neutral-400">{row.rowIndex}</td>
                          {PREVIEW_COLS.map((col) => {
                            const val = row[col.key]
                            const isTruncatedName = col.key === "item_name" && row.item_name_original != null
                            return (
                              <td
                                key={col.key}
                                className={cn(
                                  "px-3 py-2 font-mono text-neutral-700 whitespace-nowrap",
                                  isTruncatedName && "text-amber-700",
                                )}
                                title={isTruncatedName ? `Original: "${row.item_name_original}"` : undefined}
                              >
                                {col.key === "is_new_item"
                                  ? (val ? <span className="text-indigo-600">Yes</span> : <span className="text-neutral-300">No</span>)
                                  : val != null && val !== ""
                                    ? <>
                                        {String(val)}
                                        {isTruncatedName && <span className="ml-1 text-amber-500 text-[10px]">✂</span>}
                                      </>
                                    : <span className="text-neutral-300">—</span>
                                }
                              </td>
                            )
                          })}
                          <td className="px-3 py-2">
                            {row.errors.length > 0 ? (
                              <ul className="space-y-0.5">
                                {row.errors.map((e, i) => (
                                  <li key={i} className="text-red-600">{e}</li>
                                ))}
                              </ul>
                            ) : row.warnings.length > 0 ? (
                              <ul className="space-y-0.5">
                                {row.warnings.map((w, i) => (
                                  <li key={i} className="text-amber-600">{w}</li>
                                ))}
                              </ul>
                            ) : (
                              <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* ── SUBMITTING overlay ── */}
            {state === "submitting" && (
              <div className="mt-6 flex items-center justify-center gap-2 text-sm text-neutral-500">
                <Spinner size="sm" />
                Uploading {validRows.length} items…
              </div>
            )}

          </div>

          {/* Footer */}
          <div className="flex items-center justify-between px-6 py-4 border-t border-neutral-100 shrink-0 bg-neutral-50 rounded-b-xl">
            <div className="text-xs text-neutral-400">
              {state === "preview" && parseResult && !hasParseErrors && (
                <span className="text-green-600 font-medium">
                  Ready to import {validRows.length} item{validRows.length !== 1 ? "s" : ""}
                  {warnRows.length > 0 && ` — ${warnRows.length} name${warnRows.length !== 1 ? "s" : ""} will be truncated`}
                </span>
              )}
              {state === "preview" && hasParseErrors && (
                <span className="text-amber-600">Fix errors in the spreadsheet, then re-upload</span>
              )}
            </div>
            <div className="flex gap-2">
              {state === "preview" && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => { setState("idle"); setParseResult(null); setRawFile(null); setSubmitError(null) }}
                >
                  Upload different file
                </Button>
              )}
              <Button variant="outline" size="sm" onClick={onClose} disabled={state === "submitting"}>
                Cancel
              </Button>
              {state === "preview" && (
                <Button
                  size="sm"
                  onClick={handleConfirm}
                  disabled={!canConfirm}
                >
                  {canConfirm
                    ? `Import ${validRows.length} item${validRows.length !== 1 ? "s" : ""}${warnRows.length > 0 ? ` (${warnRows.length} truncated)` : ""}`
                    : "Fix errors first"
                  }
                </Button>
              )}
            </div>
          </div>

        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
