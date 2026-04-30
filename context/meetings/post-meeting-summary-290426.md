Here's a summary of the meeting:

Meeting Summary: Stargile Re-write + PLM Features (Oskar Project)

Participants: Karen Lewin, Hector Salazar, Branko Polak, Nick Niculita

Duration: ~1 hour 13 minutes

Context & Background

The team is planning to replace Stargile (an internal legacy system), which manages the Engineering Change Notice (ECN) workflow and MoveX integration. Two key drivers for the replacement:

No suitable replacement tool yet offered by Scanfil
Legacy systems are blocking SRX-SCA integration progress
The new system has been named "OSKAR". Hector is leading the development using AI-assisted coding.

ECN Workflow Discussion

The current ECN flow: Draft → Document Controller → Engineering Review → Management/Quality/Supply Chain approval (parallel) → Approved → Implemented/Closed
Key issues identified:
Roles should be customisable (add/remove approvers per ECN) rather than fixed
Doc Control approves twice currently — this is redundant; should approve only once, just before the MoveX update
An "Emergency path" exists in the code but no one uses it (likely obsolete)
Stage 1 proposal: a standard default flow where the person raising the ECN can add or remove approvers as needed
BOM Processing Pain Points

Nick shared data showing that processing a 100-part BOM takes approximately 1,180 minutes in total (820 minutes for ECN/MoveX steps, 300 minutes for pre-checks). Key manual pain points:

MPN validation — currently checked manually against DigiKey/Mouser/Octopart APIs; should be automated
Packaging type (tape & reel, tray, tube) — procurement often selects the wrong type; DigiKey API returns this data in JSON and can be parsed automatically
Description sanitisation — descriptions from customers are often too long for MoveX's 30-character limit
Long MPNs — some MPNs exceed MoveX field limits
BOM comparison — comparing customer BOM vs quoted BOM is still ~50% done manually in Excel; a comparison tool would highlight unapproved alternative MPNs before a PO arrives
EOL/NRND status — parts flagged as End-of-Life or "Not Recommended for New Design" should be flagged at BOM upload time; Scanfield recommends parts with more than 7 years to EOL
MSL (Moisture Sensitivity Level) — currently inconsistently recorded; needs a dedicated field
Part number creation — 4+ ECNs needed to create a new product; should be streamlined with alias/MPN-based matching against existing MoveX stock codes
Scope Definition

Karen proposed focusing Stage 1 tightly on replacing the 820 minutes of ECN/MoveX work with a faster, more automated tool — rather than expanding scope prematurely. The team agreed this is the right starting point, with BOM tools and supplier comparison as later modules.

The platform architecture: Python backend, Postgres database, REST API (to allow future integrations with IoT, AI agents, and other systems).

AI & MCP Integration

Nick demonstrated an MCP server connected to the DigiKey API, allowing AI-assisted MPN lookups via chatbot. The team agreed AI integration must be done carefully given customer IP sensitivity — Hector noted they need guidance from Scanfil on approved AI infrastructure and data boundaries before enabling AI agents in production workflows.

Next Steps

Karen — draft a scope document for Stage 1, focused on the 820-minute ECN/MoveX pain points
Nick — send files (BOM analysis spreadsheet + presentations) via email; locate or create a shared Teams/SharePoint space for project documentation
Hector — share his design document (covering all 16 pain points and proposed solutions) with Nick and Branko for review and validation
Branko & Nick — review Hector's assumptions and contribute any additional requirements or historical context
Cadence — fortnightly meetings, with ad-hoc meetings and a shared documentation space for ongoing collaboration
 

 

 

Regards, Karen