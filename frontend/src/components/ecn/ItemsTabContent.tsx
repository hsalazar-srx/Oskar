import { Badge } from "@/components/ui/badge"

export interface ItemRow {
  id: string
  item_number: string
  item_name: string
  customer_alias: string | null
  is_new_item: boolean
}

interface Props {
  items: ItemRow[]
  onSelectItem: (itemId: string) => void
}

export default function ItemsTabContent({ items, onSelectItem }: Props) {
  if (items.length === 0) {
    return (
      <div className="py-10 flex flex-col items-center gap-2">
        <div className="w-10 h-10 rounded-full bg-[#f1f5f9] flex items-center justify-center">
          <svg className="w-5 h-5 text-[#94a3b8]" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25zM6.75 12h.008v.008H6.75V12zm0 3h.008v.008H6.75V15zm0 3h.008v.008H6.75V18z"/>
          </svg>
        </div>
        <p className="text-sm text-[#94a3b8]">No items added yet.</p>
        <p className="text-xs text-[#cbd5e1]">Items represent the parts or assemblies being changed.</p>
      </div>
    )
  }

  return (
    <>
      <div className="divide-y divide-[#f1f5f9]">
        {items.map((item) => (
          <button
            key={item.id}
            type="button"
            className="w-full flex items-center justify-between py-3 px-1 rounded-lg hover:bg-[#f8fafc] text-left transition-colors duration-150 group"
            onClick={() => onSelectItem(item.id)}
          >
            <div className="flex items-center gap-3 min-w-0">
              <span className="font-mono text-sm font-semibold text-[#0066cc] shrink-0">
                {item.item_number || <span className="text-[#cbd5e1] font-normal">—</span>}
              </span>
              <div className="flex flex-col min-w-0">
                <span className="text-sm text-[#475569] truncate">{item.item_name || "Untitled item"}</span>
                {item.customer_alias && (
                  <span className="text-[11px] font-mono text-[#94a3b8] truncate">Alias: {item.customer_alias}</span>
                )}
              </div>
              {item.is_new_item && <Badge variant="info" className="shrink-0 text-[11px]">New</Badge>}
            </div>
            <svg className="w-4 h-4 text-[#cbd5e1] group-hover:text-[#94a3b8] transition-colors duration-150 shrink-0 ml-2" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5"/>
            </svg>
          </button>
        ))}
      </div>
      {/* Item count footer */}
      <div className="mt-3 pt-3 border-t border-[#f1f5f9] text-right">
        <span className="text-xs text-[#94a3b8]">
          {items.length} item{items.length !== 1 ? "s" : ""} total
        </span>
      </div>
    </>
  )
}
