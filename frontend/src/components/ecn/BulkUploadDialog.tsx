/**
 * BulkUploadDialog — generic drag-and-drop bulk upload dialog shell shared by
 * ItemUploadDrawer, RoutingUploadDrawer, MPNUploadDrawer.
 *
 * States:
 *   idle       → Drop zone with instructions
 *   preview    → Parsed rows table (entity-specific, via renderTable) with
 *                inline validation errors; Confirm / Cancel
 *   submitting → Spinner while the upload POST is in flight
 *
 * Architecture (from LLM council 2026-06-17, ItemUploadDrawer.tsx):
 * - SheetJS parses client-side for instant preview
 * - Header fingerprint check blocks mismatched templates before preview renders
 * - Raw file is sent to backend as multipart/form-data for authoritative validation
 * - Backend is the source of truth — client validation is for UX speed only
 *
 * Table rendering is entity-specific (Items has truncated-name styling, MPNs
 * has alt-row/is_default columns, Routing is a flat column set) — callers
 * supply `renderTable`, this shell owns everything else: chrome, drop zone,
 * banners, footer, and the parse/submit state machine.
 */

import * as React from "react"
import * as DialogPrimitive from "@radix-ui/react-dialog"
import { useDropzone } from "react-dropzone"
import * as XLSX from "xlsx"
import { UploadCloud, X, AlertTriangle, FileSpreadsheet } from "lucide-react"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { Badge } from "@/components/ui/badge"

// ---------------------------------------------------------------------------
// Shared row/result shape — every parser's row/result type is a superset of
// these fields (see ecn-item-csv-parser.ts, ecn-routing-csv-parser.ts,
// ecn-mpn-csv-parser.ts).
// ---------------------------------------------------------------------------

export interface BaseParsedRow {
  rowIndex: number
  errors: string[]
  warnings: string[]
}

export interface BaseParseResult<Row extends BaseParsedRow> {
  rows: Row[]
  skippedRows: number
  missingColumns: string[]
}

interface Props<Row extends BaseParsedRow, Result extends BaseParseResult<Row>> {
  open: boolean
  onClose: () => void
  onSuccess: () => void
  title: string
  description: string
  dropInstructions: string
  entityLabel: string
  entityLabelPlural: string
  parseFile: (workbook: XLSX.WorkBook) => Result
  upload: (file: File) => Promise<unknown>
  renderTable: (result: Result) => React.ReactNode
  missingColumnsHint: string
}

type DialogState = "idle" | "preview" | "submitting"

export function BulkUploadDialog<Row extends BaseParsedRow, Result extends BaseParseResult<Row>>({
  open,
  onClose,
  onSuccess,
  title,
  description,
  dropInstructions,
  entityLabel,
  entityLabelPlural,
  parseFile,
  upload,
  renderTable,
  missingColumnsHint,
}: Props<Row, Result>) {
  const [state, setState] = React.useState<DialogState>("idle")
  const [parseResult, setParseResult] = React.useState<Result | null>(null)
  const [rawFile, setRawFile] = React.useState<File | null>(null)
  const [submitError, setSubmitError] = React.useState<string | null>(null)

  // Reset to idle when dialog is closed
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
        setParseResult(parseFile(wb))
        setState("preview")
      } catch {
        setSubmitError("Could not parse the file. Ensure it is a valid .xlsx or .csv.")
        setState("preview")
      }
    }
    reader.readAsArrayBuffer(file)
  }, [parseFile])

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

  const handleConfirm = async () => {
    if (!rawFile || !parseResult) return
    setState("submitting")
    setSubmitError(null)
    try {
      await upload(rawFile)
      onSuccess()
      onClose()
    } catch (err: unknown) {
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

  const hasParseErrors = parseResult
    ? parseResult.missingColumns.length > 0 || parseResult.rows.some((r) => r.errors.length > 0)
    : false
  const validRows = parseResult?.rows.filter((r) => r.errors.length === 0) ?? []
  const errorRows = parseResult?.rows.filter((r) => r.errors.length > 0) ?? []
  const canConfirm = state === "preview" && !hasParseErrors && validRows.length > 0

  function resetToIdle() {
    setState("idle")
    setParseResult(null)
    setRawFile(null)
    setSubmitError(null)
  }

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
                {title}
              </DialogPrimitive.Title>
              <DialogPrimitive.Description className="text-xs text-neutral-400 mt-0.5">
                {description}
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
                  {dropInstructions}
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
                  {errorRows.length > 0 && (
                    <Badge variant="destructive">
                      {errorRows.length} with errors
                    </Badge>
                  )}
                  {parseResult.skippedRows > 0 && (
                    <span className="text-xs text-neutral-400">{parseResult.skippedRows} rows skipped</span>
                  )}
                </div>

                {/* Missing columns banner */}
                {parseResult.missingColumns.length > 0 && (
                  <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700 flex gap-2">
                    <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                    <div>
                      <p className="font-medium">Wrong template — missing required columns:</p>
                      <p className="mt-0.5">{parseResult.missingColumns.join(", ")}</p>
                      <p className="mt-1 text-xs">{missingColumnsHint}</p>
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

                {/* Preview table — entity-specific */}
                {renderTable(parseResult)}
              </div>
            )}

            {/* ── SUBMITTING overlay ── */}
            {state === "submitting" && (
              <div className="mt-6 flex items-center justify-center gap-2 text-sm text-neutral-500">
                <Spinner size="sm" />
                Uploading {validRows.length} {validRows.length !== 1 ? entityLabelPlural : entityLabel}…
              </div>
            )}

          </div>

          {/* Footer */}
          <div className="flex items-center justify-between px-6 py-4 border-t border-neutral-100 shrink-0 bg-neutral-50 rounded-b-xl">
            <div className="text-xs text-neutral-400">
              {state === "preview" && parseResult && !hasParseErrors && (
                <span className="text-green-600 font-medium">
                  Ready to import {validRows.length} {validRows.length !== 1 ? entityLabelPlural : entityLabel}
                </span>
              )}
              {state === "preview" && hasParseErrors && (
                <span className="text-amber-600">Fix errors in the spreadsheet, then re-upload</span>
              )}
            </div>
            <div className="flex gap-2">
              {state === "preview" && (
                <Button variant="outline" size="sm" onClick={resetToIdle}>
                  Upload different file
                </Button>
              )}
              <Button variant="outline" size="sm" onClick={onClose} disabled={state === "submitting"}>
                Cancel
              </Button>
              {state === "preview" && (
                <Button size="sm" onClick={handleConfirm} disabled={!canConfirm}>
                  {canConfirm
                    ? `Import ${validRows.length} ${validRows.length !== 1 ? entityLabelPlural : entityLabel}`
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
