# cairn-platform-onepager

## Tables

### Table 1
| Cairn<br>product intelligence platform | Every stone in its place.<br><br>A unified internal platform replacing disconnected ECN, BOM, and supplier data workflows with a composable, AI-ready intelligence layer built on your M3 part master. |
| --- | --- |

### Table 2
| The problem today |  | What Cairn changes |
| --- | --- | --- |
| ECN, BOM, and supplier data live in separate tools — email threads, spreadsheets, and a legacy portal that cannot be extended.<br><br>Engineering changes don't propagate. Procurement discovers BOM updates late. Supplier pricing requires manual cross-referencing across six distributor sites.<br><br>Nexar/Octopart API costs escalated as usage grew, with no path to cost-effective scale. |  | A single composable platform where a change made in engineering is immediately visible to procurement and operations — with full traceability.<br><br>Live component pricing from DigiKey, Mouser, Arrow, Element14, and Future Electronics — cached, normalized, and enriched against the M3 part master.<br><br>AI-assisted risk signals that surface EOL risks, price spikes, and supply disruptions before they become procurement emergencies. |

### Table 3
| Platform modules — the stones of Cairn | Platform modules — the stones of Cairn | Platform modules — the stones of Cairn | Platform modules — the stones of Cairn | Platform modules — the stones of Cairn |
| --- | --- | --- | --- | --- |
| Ledger<br>Bill of Materials<br><br>Multi-level BOM management with M3 sync, revision history, and live pricing enrichment. |  | Shift<br>Engineering Change Notes<br><br>ECN creation, approval routing, and closure with automatic BOM impact propagation. |  | Vein<br>Supplier & Component Data<br><br>Multi-distributor API fanout with Redis cache. Replaces Nexar/Octopart entirely. |
| Trace<br>Audit & Lineage<br><br>Full change lineage across BOMs, ECNs, and supplier records. Audit-ready export. |  | Signal<br>Alerts & Risk Intelligence<br><br>EOL alerts, price spike detection, PCN notifications. AI-driven supply risk monitoring. |  | Core<br>M3 Integration<br><br>Bidirectional M3 sync (MITMAS, MIPUR). IPN/MPN mapping and approved supplier lists. |

### Table 4
| Delivery roadmap | Delivery roadmap | Delivery roadmap | Delivery roadmap | Delivery roadmap | Delivery roadmap | Delivery roadmap |
| --- | --- | --- | --- | --- | --- | --- |
| Phase 0<br>Foundation<br>Now — Month 1<br><br>  —  API registrations (DigiKey, Mouser, Arrow, E14)<br>  —  M3 part master read integration<br>  —  Core module: IPN → MPN mapping |  | Phase 1<br>Core service<br>Month 1 — 2<br><br>  —  Vein: DigiKey + Mouser integration + Redis cache<br>  —  Ledger: BOM management with pricing enrichment<br>  —  Shift: ECN creation and approval workflow |  | Phase 2<br>Full coverage<br>Month 2 — 3<br><br>  —  Vein: Arrow + Element14 + OEMsecrets fallback<br>  —  Trace: Audit lineage and export<br>  —  Shift: BOM impact propagation on ECN close |  | Phase 3<br>Intelligence<br>Month 3+<br><br>  —  Signal: EOL + price spike + PCN alerts<br>  —  AI-assisted alternate part suggestions<br>  —  M3 write-back: standard cost from market data |

### Table 5
| Cairn is built for internal use on the organizational AI platform.<br>Foundational infrastructure for BOM analysis and ECN management. | Designed principles<br><br>M3 is the source of truth<br>Every API call is cached<br>Every change is traceable<br>No vendor lock-in | Status<br><br>Platform: planned<br>Design phase: Q2 2026<br>Phase 1 target: Q3 2026 |
| --- | --- | --- |
