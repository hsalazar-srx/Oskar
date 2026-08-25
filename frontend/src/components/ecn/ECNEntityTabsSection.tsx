import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import ItemsTabContent, { type ItemRow } from "@/components/ecn/ItemsTabContent"
import RoutingTabContent from "@/components/ecn/RoutingTabContent"
import BOMChangesTabContent from "@/components/ecn/BOMChangesTabContent"
import MPNsTabContent from "@/components/ecn/MPNsTabContent"
import { ItemUploadDrawer } from "@/components/ecn/ItemUploadDrawer"
import { RoutingUploadDrawer } from "@/components/ecn/RoutingUploadDrawer"
import { BOMChangesUploadDrawer } from "@/components/ecn/BOMChangesUploadDrawer"
import AddBomChangeDrawer from "@/components/ecn/AddBomChangeDrawer"
import { MPNUploadDrawer } from "@/components/ecn/MPNUploadDrawer"
import { exportItems, exportRoutingOps, exportBomChanges, exportMPNs } from "@/api/ecn"

type EntityTab = "items" | "routing" | "bom" | "mpns"

interface Props {
  ecnId: string
  ecnNumber: string
  customerNumber: string | null
  items: ItemRow[]
  canUpload: boolean
  canExport: boolean
  onSelectItem: (itemId: string, tab?: "details" | "routing" | "bom" | "mpns") => void
  onAddItem: () => void
  onItemsChanged: () => void
}

export default function ECNEntityTabsSection({
  ecnId,
  ecnNumber,
  customerNumber,
  items,
  canUpload,
  canExport,
  onSelectItem,
  onAddItem,
  onItemsChanged,
}: Props) {
  const [tab, setTab] = useState<EntityTab>("items")
  const [itemUploadOpen, setItemUploadOpen] = useState(false)
  const [routingUploadOpen, setRoutingUploadOpen] = useState(false)
  const [bomUploadOpen, setBomUploadOpen] = useState(false)
  const [addBomChangeOpen, setAddBomChangeOpen] = useState(false)
  const [mpnUploadOpen, setMpnUploadOpen] = useState(false)

  function manageItem(itemId: string, entityTab: "routing" | "bom" | "mpns") {
    onSelectItem(itemId, entityTab)
  }

  return (
    <div className="rounded-xl border border-[#e8ecf0] bg-white shadow-[var(--shadow-sm)] overflow-hidden">
      <div className="flex items-center justify-between px-5 pt-4 border-b border-[#f1f5f9] bg-[#f8fafc]">
        <Tabs value={tab} onValueChange={(v) => setTab(v as EntityTab)}>
          <TabsList>
            <TabsTrigger value="items">Items ({items.length})</TabsTrigger>
            <TabsTrigger value="routing">Routing</TabsTrigger>
            <TabsTrigger value="bom">BOM Changes</TabsTrigger>
            <TabsTrigger value="mpns">MPNs</TabsTrigger>
          </TabsList>
        </Tabs>

        <div className="flex gap-2 pb-3">
          {tab === "items" && (
            <>
              <ExportButton canExport={canExport} label="↓ Export" onExport={() => exportItems(ecnId, ecnNumber)} />
              <UploadButton canUpload={canUpload} label="↑ Upload" onClick={() => setItemUploadOpen(true)} />
              <Button size="sm" variant="outline" onClick={onAddItem}>+ Add item</Button>
            </>
          )}
          {tab === "routing" && (
            <>
              <ExportButton canExport={canExport} label="↓ Export" onExport={() => exportRoutingOps(ecnId, ecnNumber)} />
              <UploadButton canUpload={canUpload} label="↑ Upload Routing" onClick={() => setRoutingUploadOpen(true)} />
            </>
          )}
          {tab === "bom" && (
            <>
              <ExportButton canExport={canExport} label="↓ Export" onExport={() => exportBomChanges(ecnId, ecnNumber)} />
              <UploadButton canUpload={canUpload} label="↑ Upload BOM Changes" onClick={() => setBomUploadOpen(true)} />
              {/* ADR-014 — author a BOM change with no item on the ECN.
                  Gated on canUpload, the same "can still edit this ECN"
                  permission the upload path uses. */}
              {canUpload && (
                <Button size="sm" variant="outline" onClick={() => setAddBomChangeOpen(true)}>
                  + Add BOM change
                </Button>
              )}
            </>
          )}
          {tab === "mpns" && (
            <>
              <ExportButton canExport={canExport} label="↓ Export" onExport={() => exportMPNs(ecnId, ecnNumber)} />
              <UploadButton canUpload={canUpload} label="↑ Upload MPNs" onClick={() => setMpnUploadOpen(true)} />
            </>
          )}
        </div>
      </div>

      <div className="p-5">
        {tab === "items" && <ItemsTabContent items={items} onSelectItem={(id) => onSelectItem(id)} />}
        {tab === "routing" && (
          <RoutingTabContent ecnId={ecnId} onManageItem={(id) => manageItem(id, "routing")} />
        )}
        {tab === "bom" && (
          <BOMChangesTabContent ecnId={ecnId} onManageItem={(id) => manageItem(id, "bom")} />
        )}
        {tab === "mpns" && (
          <MPNsTabContent ecnId={ecnId} onManageItem={(id) => manageItem(id, "mpns")} />
        )}
      </div>

      <ItemUploadDrawer
        ecnId={ecnId}
        customerNumber={customerNumber}
        open={itemUploadOpen}
        onClose={() => setItemUploadOpen(false)}
        onSuccess={onItemsChanged}
      />

      <RoutingUploadDrawer
        ecnId={ecnId}
        open={routingUploadOpen}
        onClose={() => setRoutingUploadOpen(false)}
        onSuccess={onItemsChanged}
      />

      <BOMChangesUploadDrawer
        ecnId={ecnId}
        open={bomUploadOpen}
        onClose={() => setBomUploadOpen(false)}
        onSuccess={onItemsChanged}
      />

      <AddBomChangeDrawer
        ecnId={ecnId}
        open={addBomChangeOpen}
        onClose={() => setAddBomChangeOpen(false)}
        onSuccess={onItemsChanged}
      />

      <MPNUploadDrawer
        ecnId={ecnId}
        open={mpnUploadOpen}
        onClose={() => setMpnUploadOpen(false)}
        onSuccess={onItemsChanged}
      />
    </div>
  )
}

function ExportButton({ canExport, label, onExport }: { canExport: boolean; label: string; onExport: () => Promise<void> }) {
  const [isExporting, setIsExporting] = useState(false)

  if (!canExport) {
    return (
      <Button
        size="sm"
        variant="outline"
        disabled
        title="Export is only available once the ECN is marked Movex Updated"
        className="opacity-40 cursor-not-allowed"
      >
        {label}
      </Button>
    )
  }

  return (
    <Button
      size="sm"
      variant="outline"
      disabled={isExporting}
      onClick={async () => {
        setIsExporting(true)
        try {
          await onExport()
        } finally {
          setIsExporting(false)
        }
      }}
    >
      {isExporting ? "Exporting…" : label}
    </Button>
  )
}

function UploadButton({ canUpload, label, onClick }: { canUpload: boolean; label: string; onClick: () => void }) {
  if (!canUpload) {
    return (
      <Button
        size="sm"
        variant="outline"
        disabled
        title="Uploads only available in Draft status"
        className="opacity-40 cursor-not-allowed"
      >
        {label}
      </Button>
    )
  }
  return (
    <Button size="sm" variant="outline" onClick={onClick}>
      {label}
    </Button>
  )
}
