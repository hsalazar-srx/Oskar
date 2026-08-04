/**
 * MPNUploadDrawer — bulk MPN upload for an ECN, from a CAD BOM export (C P/N,
 * Manufacturer 1/2, Manufacturer 1/2 Part Number). Thin call site over
 * BulkUploadDialog; owns only the MPN-specific parse call, preview table,
 * and copy. See BulkUploadDialog.tsx for the shared chrome/state machine.
 *
 * One CAD BOM row expands to 1-2 preview rows (primary + optional alternate
 * manufacturer). A row with a real component but no C P/N is a hard error —
 * items must already exist on this ECN (add via item upload first); this
 * does not auto-create items or auto-resolve missing C P/N.
 */

import { CheckCircle2 } from "lucide-react"
import { cn } from "@/lib/utils"
import { BulkUploadDialog } from "@/components/ecn/BulkUploadDialog"
import { parseMpnWorkbook, type ParsedMpnRow, type MpnParseResult } from "@/lib/ecn-mpn-csv-parser"
import { bulkCreateMPNs } from "@/api/ecn"

interface MPNUploadDrawerProps {
  ecnId: string
  open: boolean
  onClose: () => void
  onSuccess: () => void
}

export function MPNUploadDrawer({ ecnId, open, onClose, onSuccess }: MPNUploadDrawerProps) {
  return (
    <BulkUploadDialog<ParsedMpnRow, MpnParseResult>
      open={open}
      onClose={onClose}
      onSuccess={onSuccess}
      title="Upload MPNs from CAD BOM Export"
      description="C P/N, Manufacturer 1/2, Manufacturer 1/2 Part Number (.xlsx or .csv)"
      dropInstructions="C P/N must already match an item on this ECN (add items via item upload first). Rows with a part but no C P/N filled in will be rejected — fill in C P/N and re-upload, or handle them individually from the item panel."
      missingColumnsHint="Use a CAD BOM export with C P/N and Manufacturer 1 columns."
      entityLabel="MPN"
      entityLabelPlural="MPNs"
      parseFile={(wb) => parseMpnWorkbook(wb)}
      upload={(file) => bulkCreateMPNs(ecnId, file)}
      renderTable={(result) => (
        <div className="rounded-lg border border-neutral-200 overflow-auto max-h-[420px]">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-neutral-50 border-b border-neutral-200 sticky top-0">
                <th className="px-3 py-2 text-left font-medium text-neutral-500 w-8">#</th>
                <th className="px-3 py-2 text-left font-medium text-neutral-500 whitespace-nowrap">Item No (C P/N)</th>
                <th className="px-3 py-2 text-left font-medium text-neutral-500 whitespace-nowrap">MPN</th>
                <th className="px-3 py-2 text-left font-medium text-neutral-500 whitespace-nowrap">Manufacturer</th>
                <th className="px-3 py-2 text-left font-medium text-neutral-500 whitespace-nowrap">Default?</th>
                <th className="px-3 py-2 text-left font-medium text-neutral-500">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100">
              {result.rows.map((row, i) => (
                <tr
                  key={`${row.rowIndex}-${i}`}
                  className={cn(row.errors.length > 0 ? "bg-red-50" : "hover:bg-neutral-50")}
                >
                  <td className="px-3 py-2 text-neutral-400">
                    {row.rowIndex}{row.isAlternate && <span className="ml-1 text-neutral-300">(alt)</span>}
                  </td>
                  <td className="px-3 py-2 font-mono text-neutral-700 whitespace-nowrap">
                    {row.item_number ?? <span className="text-neutral-300">—</span>}
                  </td>
                  <td className="px-3 py-2 font-mono text-neutral-700 whitespace-nowrap">{row.mpn}</td>
                  <td className="px-3 py-2 text-neutral-700 whitespace-nowrap">
                    {row.manufacturer ?? <span className="text-neutral-300">—</span>}
                  </td>
                  <td className="px-3 py-2">
                    {row.is_default
                      ? <span className="text-indigo-600">Yes</span>
                      : <span className="text-neutral-300">No</span>}
                  </td>
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
