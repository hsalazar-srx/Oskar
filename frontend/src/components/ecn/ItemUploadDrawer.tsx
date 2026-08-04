/**
 * ItemUploadDrawer — bulk item upload for an ECN. Thin call site over
 * BulkUploadDialog; owns only the item-specific parse call, preview table,
 * and copy. See BulkUploadDialog.tsx for the shared chrome/state machine.
 */

import { CheckCircle2 } from "lucide-react"
import { cn } from "@/lib/utils"
import { BulkUploadDialog } from "@/components/ecn/BulkUploadDialog"
import { parseWorkbook, type ParsedItemRow, type ParseResult } from "@/lib/ecn-item-csv-parser"
import { bulkCreateItems } from "@/api/ecn"

interface ItemUploadDrawerProps {
  ecnId: string
  customerNumber: string | null
  open: boolean
  onClose: () => void
  onSuccess: () => void
}

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

export function ItemUploadDrawer({ ecnId, customerNumber, open, onClose, onSuccess }: ItemUploadDrawerProps) {
  const warnRows = (result: ParseResult) =>
    result.rows.filter((r) => r.errors.length === 0 && r.warnings.length > 0)

  return (
    <BulkUploadDialog<ParsedItemRow, ParseResult>
      open={open}
      onClose={onClose}
      onSuccess={onSuccess}
      title="Upload Items from Spreadsheet"
      description="Use the standard Oskar item upload template (.xlsx or .csv)"
      dropInstructions="Use the standard Oskar item upload template. Delete the instruction rows (rows 2–6) before uploading. All required columns must be present."
      missingColumnsHint="Use the standard Oskar item upload template and try again."
      entityLabel="item"
      entityLabelPlural="items"
      parseFile={(wb) => parseWorkbook(wb, customerNumber ?? undefined)}
      upload={(file) => bulkCreateItems(ecnId, file)}
      renderTable={(result) => {
        const warns = warnRows(result)
        return (
          <>
            {warns.length > 0 && result.rows.every((r) => r.errors.length === 0 || r.warnings.length > 0) && (
              <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-800 flex gap-2 mb-4">
                <p className="font-medium">
                  {warns.length} item name{warns.length !== 1 ? "s" : ""} will be truncated to 30 characters (MOVEX limit).
                  <span className="block font-normal text-xs mt-0.5">
                    The full name is preserved in Item Description. Hover the amber cells to see the original.
                  </span>
                </p>
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
                  {result.rows.map((row) => (
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
          </>
        )
      }}
    />
  )
}
