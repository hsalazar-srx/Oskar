/**
 * BOMChangesUploadDrawer — bulk BOM-change upload for an ECN. Thin call site
 * over BulkUploadDialog; owns only the BOM-change-specific parse call,
 * preview table, and copy. See BulkUploadDialog.tsx for the shared
 * chrome/state machine. Mirrors RoutingUploadDrawer.tsx exactly (I2-20).
 *
 * Multi-item, ECN-wide template — a single upload can carry one item's full
 * set of BOM changes or many items' changes at once.
 */

import { CheckCircle2 } from "lucide-react"
import { cn } from "@/lib/utils"
import { BulkUploadDialog } from "@/components/ecn/BulkUploadDialog"
import { parseBomChangeWorkbook, type ParsedBomChangeRow, type BomChangeParseResult } from "@/lib/ecn-bom-changes-csv-parser"
import { bulkCreateBomChanges } from "@/api/ecn"

interface BOMChangesUploadDrawerProps {
  ecnId: string
  open: boolean
  onClose: () => void
  onSuccess: () => void
}

const PREVIEW_COLS: { key: keyof ParsedBomChangeRow; label: string }[] = [
  { key: "item_number", label: "Item No" },
  { key: "component_number", label: "Component No" },
  { key: "change_type", label: "Change Type" },
  { key: "quantity", label: "Quantity" },
  { key: "operation_number", label: "Op No" },
  { key: "old_from_date", label: "Old From Date" },
]

export function BOMChangesUploadDrawer({ ecnId, open, onClose, onSuccess }: BOMChangesUploadDrawerProps) {
  return (
    <BulkUploadDialog<ParsedBomChangeRow, BomChangeParseResult>
      open={open}
      onClose={onClose}
      onSuccess={onSuccess}
      title="Upload BOM Changes from Spreadsheet"
      description="One item's full BOM-change set, or many items' changes — Item No, Component Number, Change Type (ADD/CHANGE/DELETE), Old From Date for CHANGE/DELETE (.xlsx or .csv)"
      dropInstructions="Items referenced by Item No must already exist on this ECN — add them via item upload first. CHANGE/DELETE rows require Old From Date to identify which live Movex line is being superseded."
      missingColumnsHint="Use the standard Oskar BOM change upload template and try again."
      entityLabel="BOM change"
      entityLabelPlural="BOM changes"
      parseFile={(wb) => parseBomChangeWorkbook(wb)}
      upload={(file) => bulkCreateBomChanges(ecnId, file)}
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
