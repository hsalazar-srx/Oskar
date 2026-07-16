/**
 * RoutingUploadDrawer — drag-and-drop bulk routing operation upload for an ECN.
 *
 * States:
 *   idle       → Drop zone with instructions
 *   preview    → Parsed rows table with inline validation errors; Confirm / Cancel
 *   submitting → Spinner while POST /routing/bulk is in flight
 *
 * Multi-item, ECN-wide template — a single upload can carry one item's full
 * routing (many operations, one Item No) or many items' routing changes at
 * once. Structure mirrors ItemUploadDrawer.tsx; see that file for the
 * client-preview/backend-authoritative architecture note.
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
import { parseRoutingWorkbook, type ParsedRoutingRow, type RoutingParseResult } from "@/lib/ecn-routing-csv-parser"
import { bulkCreateRoutingOps } from "@/api/ecn"

interface RoutingUploadDrawerProps {
  ecnId: string
  open: boolean
  onClose: () => void
  onSuccess: () => void
}

type DrawerState = "idle" | "preview" | "submitting"

const PREVIEW_COLS: { key: keyof ParsedRoutingRow; label: string }[] = [
  { key: "item_number", label: "Item No" },
  { key: "operation_number", label: "Op No" },
  { key: "operation_description", label: "Description" },
  { key: "work_centre", label: "Work Centre" },
  { key: "run_time", label: "Run Time" },
  { key: "setup_time", label: "Setup Time" },
  { key: "change_type", label: "Change Type" },
]

export function RoutingUploadDrawer({ ecnId, open, onClose, onSuccess }: RoutingUploadDrawerProps) {
  const [state, setState] = React.useState<DrawerState>("idle")
  const [parseResult, setParseResult] = React.useState<RoutingParseResult | null>(null)
  const [rawFile, setRawFile] = React.useState<File | null>(null)
  const [submitError, setSubmitError] = React.useState<string | null>(null)

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
        const result = parseRoutingWorkbook(wb)
        setParseResult(result)
        setState("preview")
      } catch {
        setSubmitError("Could not parse the file. Ensure it is a valid .xlsx or .csv.")
        setState("preview")
      }
    }
    reader.readAsArrayBuffer(file)
  }, [])

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
      await bulkCreateRoutingOps(ecnId, rawFile)
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
          <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-100 shrink-0">
            <div>
              <DialogPrimitive.Title className="text-base font-semibold text-neutral-900">
                Upload Routing Operations from Spreadsheet
              </DialogPrimitive.Title>
              <DialogPrimitive.Description className="text-xs text-neutral-400 mt-0.5">
                One item's full routing, or many items' routing changes — Item No, Operation No,
                Operation Description, Work Centre, Run Time, Change Type (.xlsx or .csv)
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

          <div className="flex-1 overflow-y-auto px-6 py-5">

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
                  Items referenced by Item No must already exist on this ECN — add them via item
                  upload first. Rows can share one Item No (a full routing) or span many items.
                </div>
              </div>
            )}

            {state === "preview" && parseResult && (
              <div className="flex flex-col gap-4">

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
                    <span className="text-xs text-neutral-400">{parseResult.skippedRows} blank rows skipped</span>
                  )}
                </div>

                {parseResult.missingColumns.length > 0 && (
                  <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700 flex gap-2">
                    <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                    <div>
                      <p className="font-medium">Wrong template — missing required columns:</p>
                      <p className="mt-0.5">{parseResult.missingColumns.join(", ")}</p>
                      <p className="mt-1 text-xs">Use the standard Oskar routing upload template and try again.</p>
                    </div>
                  </div>
                )}

                {errorRows.length > 0 && parseResult.missingColumns.length === 0 && (
                  <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700 flex gap-2">
                    <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                    <div>
                      <p className="font-medium">Fix the errors below before uploading.</p>
                      <p className="text-xs mt-0.5">
                        All rows must be valid, and every Item No must already exist on this ECN.
                      </p>
                    </div>
                  </div>
                )}

                {submitError && (
                  <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700 flex gap-2">
                    <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                    <div>
                      <p className="font-medium">Upload failed</p>
                      <p className="mt-0.5">{submitError}</p>
                    </div>
                  </div>
                )}

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
                      {parseResult.rows.map((row, i) => (
                        <tr
                          key={`${row.rowIndex}-${i}`}
                          className={cn(row.errors.length > 0 ? "bg-red-50" : "hover:bg-neutral-50")}
                        >
                          <td className="px-3 py-2 text-neutral-400">{row.rowIndex}</td>
                          {PREVIEW_COLS.map((col) => {
                            const val = row[col.key]
                            return (
                              <td key={col.key} className="px-3 py-2 font-mono text-neutral-700 whitespace-nowrap">
                                {val != null && val !== "" ? String(val) : <span className="text-neutral-300">—</span>}
                              </td>
                            )
                          })}
                          <td className="px-3 py-2">
                            {row.errors.length > 0 ? (
                              <ul className="space-y-0.5">
                                {row.errors.map((e, ei) => (
                                  <li key={ei} className="text-red-600">{e}</li>
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

            {state === "submitting" && (
              <div className="mt-6 flex items-center justify-center gap-2 text-sm text-neutral-500">
                <Spinner size="sm" />
                Uploading {validRows.length} routing operation{validRows.length !== 1 ? "s" : ""}…
              </div>
            )}

          </div>

          <div className="flex items-center justify-between px-6 py-4 border-t border-neutral-100 shrink-0 bg-neutral-50 rounded-b-xl">
            <div className="text-xs text-neutral-400">
              {state === "preview" && parseResult && !hasParseErrors && (
                <span className="text-green-600 font-medium">
                  Ready to import {validRows.length} routing operation{validRows.length !== 1 ? "s" : ""}
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
                <Button size="sm" onClick={handleConfirm} disabled={!canConfirm}>
                  {canConfirm
                    ? `Import ${validRows.length} operation${validRows.length !== 1 ? "s" : ""}`
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
