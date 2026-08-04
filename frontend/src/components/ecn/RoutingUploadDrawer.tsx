/**
 * RoutingUploadDrawer — bulk routing operation upload for an ECN. Thin call
 * site over BulkUploadDialog; owns only the routing-specific parse call,
 * preview table, and copy. See BulkUploadDialog.tsx for the shared
 * chrome/state machine.
 *
 * Multi-item, ECN-wide template — a single upload can carry one item's full
 * routing (many operations, one Item No) or many items' routing changes at
 * once.
 */

import { CheckCircle2 } from "lucide-react"
import { cn } from "@/lib/utils"
import { BulkUploadDialog } from "@/components/ecn/BulkUploadDialog"
import { parseRoutingWorkbook, type ParsedRoutingRow, type RoutingParseResult } from "@/lib/ecn-routing-csv-parser"
import { bulkCreateRoutingOps } from "@/api/ecn"

interface RoutingUploadDrawerProps {
  ecnId: string
  open: boolean
  onClose: () => void
  onSuccess: () => void
}

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
  return (
    <BulkUploadDialog<ParsedRoutingRow, RoutingParseResult>
      open={open}
      onClose={onClose}
      onSuccess={onSuccess}
      title="Upload Routing Operations from Spreadsheet"
      description="One item's full routing, or many items' routing changes — Item No, Operation No, Operation Description, Work Centre, Run Time, Change Type (.xlsx or .csv)"
      dropInstructions="Items referenced by Item No must already exist on this ECN — add them via item upload first. Rows can share one Item No (a full routing) or span many items."
      missingColumnsHint="Use the standard Oskar routing upload template and try again."
      entityLabel="operation"
      entityLabelPlural="operations"
      parseFile={(wb) => parseRoutingWorkbook(wb)}
      upload={(file) => bulkCreateRoutingOps(ecnId, file)}
      renderTable={(result) => (
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
              {result.rows.map((row, i) => (
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
      )}
    />
  )
}
