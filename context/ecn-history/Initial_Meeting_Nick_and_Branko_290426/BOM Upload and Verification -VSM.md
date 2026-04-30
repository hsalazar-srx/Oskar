# BOM Upload and Verification -VSM

## Content

## Page 1

BOM Upload and Verification
VSM
Value Stream Mapping
Rev 1.1
Updated 9th June 2021

## Page 2

Initial Discussions
Go through the steps involved and find obvious bottlenecks and risks
– Step 1: Get the data – BOM and QCW (Including Labour and Materials
Quote)
• BOM received by email from PM
• QCW received by email from PM
• Waiting time between request and receive
– PE should have access to the ‘source’ and get themselves these files
» QCW – is loaded in the RFQ DB
» PE to get access to RFQ DB to get the QCW
» Data pack (including the BOM) should be loaded in newly created
NPI DB and BOM can be downloaded from there when needed
» Current alternative storage location for the data pack is
S:\PRODENG folder
» On top of that other folders are used by other departments for
storing data packs – risk of mixing up info and retrieving wrong
revisions
2

## Page 3

Initial Discussions
Separate Note regarding RFQ process:
– Often bare PCB is quoted with minimalistic panelisation features and is not following ‘SRX
Panelisation Guideline’ shared with our suppliers
– Often PCB is quoted one per (not panelised)
• Need to find the optimum way to communicate to the quote team the desired panelisation size
and number of boards per panel
– Finalise PCB quote should be shared with PE for approval/validation before is loaded in the QCW
– Otherwise we end up in the situation when we get a very cheap price during RFQ and then when we
place the order price is changed due to the fact that basically the panelisation and features required
for manufacturing are added only at this point. It changes the BOM price and making us lose money
or go back to the customer at this late stage and ask for cost increase and amended PO.
– Too many alternative MPNs are quoted during the RFQ, especially the ones under Consolidation
category, which are our decision to change customer BOMs due to our supply chain arrangements
• All these alternative MPNs need to be approved by the customer before we can upload them in
the system
• They make BOM upload process much slower
• Need to review the “Consolidation” category justification and rules of engagement
• During the RFQ customer MPN should be quoted first and then the alternative should be added
if alternative is a better option (better availability and price)
• In the Quote Letter should be presented the price following the customer BOM/MPN and an
alternative price (lower) that could be achieved if customer wants to get involved in approving a
number of alternative
3

## Page 4

Initial Discussions
Step 2: Data check
– Customer BOM is checked against quoted BOM (from QCW)
– BOM Comparison
• Rev Check
• MPN, Ref Des, Qty check
– BOM Comparison done manually in Excel
– Not Standardised – each PE has his own way of doing it – adds the risk of not
capturing all the time all the possible issues
– Time Consuming
• Need to investigate if BOM Comparison tool can help comparing the customer BOM and
the QCW BOM
• Alternative solution – improve and standardise the EXCEL comparison (template, macros)
• Organise external EXCEL training for PE to improve the skills and offer a better
understanding of the enhanced Excel features/functions
• Alternative solution – create web-based application for BOM Comparison with easy-to-
follow functions for BOM upload and highlight the differences
• Alternative solution – Use Valor MSS BOM Compare Tool – Train Engineers how to
use it
• Trial BOM Connector tool from Siemens – it links with Valor MSS and possibly
Movex
4

## Page 5

Initial Discussions
Step 3: Decide which parts need new PN to be created in Movex
– New BOMs usually mean new part numbers to be created in the system, but system (Movex)
need to be checked first to avoid duplication – for the same customer create a new PN for an
MPN that already has a Movex PN
– Movex check is done manually in Excel
• Need to download the parts that are already created for that customer – report called
Customer Part Mapping
• Report needs to be reformatted before can be compared with the new BOM
• Check is done based on Customer Part Number (Alias) if available or MPN and
Manufacturer
– Comparison done manually in Excel
– Not Standardised – each PE has his own way of doing it – adds the risk of not
capturing all the time all the possible issues
– Time Consuming
• It will help if QCW has also a consolidated BOM, in case of multiple BOMs upload for a
customer. It could be organised as a Pivot Table
• Parts that Match (PN already in the system) don’t require any new PN
• Partial Match – some of the MPNs are matching an existing Movex PN, but not all
– Requires further work and Customer approval or a new PN must be created
– Manual, time consuming work (download, email, explanations)
• No Match – a new PN must be created
5

## Page 6

Initial Discussions
Step 4: ECN - Create SRX PN & Stock Code – need SRX PN, Desc, Status, ECN No, ECN
Line
– Each PN has a certain format like LF-if is lead-free, XX-customer code like RM, XX –
commodity code and XXXX- 4 digits incremental number
– LFRM120008
– PE must find, manually, the right commodity code based on MPN description or checking
the Data Sheet
– PE must find, manually, the last PN allocated for that customer and that commodity and
pick the next available number for the new PN that will be created
– Description of the SRX PN must be MAX 30 characters otherwise Movex won’t accept it
– Template & QCW including the SRX PN column must be sent by email to Procurement
to add Procurement parameters
– UOM once created can't be changed, if is wrong a new PN must be created
– All the templates need to be saved as Text(Tab Delimited) otherwise upload fails
– Stargile – doesn’t have any error checking mechanism
– All Stargile issues have been centralised in WIKI
6

## Page 7

Initial Discussions
STEP 5 – ECN – Routing Upload
– PE needs to get from PM the batch quantity in order to load the right routings
– Movex doesn’t support multiple routings for the same BOM
– If Batch QTY changes then routings need to be updated
Step 6 – ECN – BOM Upload: PN, QTY, Designator, Operation Number
– Operation numbers used:
• 50-SMT
• 100-TH
• 160-Mechanical
• 190-Packing
– By this stage you need to know which parts are SMT, TH, Mechanical, Packing – at this stage
manual search no automatic scripts or help
– Reference Designators will be available in Movex Reports only next day – updating scripts
introduce by IT at 10AM, 2PM, 6PM to shorten the wait
– Add manually the Rev Data in Movex
– QTY difficult to be determined at BOM upload stage for glues, conformal coating and other
consumables
– All the templates need to be saved as Text(Tab Delimited) otherwise upload fails
– Stargile – doesn’t have any error checking mechanism
– All Stargile issues have been centralised in WIKI
7

## Page 8

Initial Discussions
Step 7 – ECN MPN Uploads (different template): PN, MPN, Manufacturer (30), Manufacturer Code
– Manufacturer and Manufacturer Code – manually searched and updated in the template
– Is Manufacturer Code used anywhere? Can we eliminate it?
– Currency is also a mandatory field which is not used – by default PE put AUD
– All the templates need to be saved as Text(Tab Delimited) otherwise upload fails
– Stargile – doesn’t have any error checking mechanism
– All Stargile issues have been centralised in WIKI
Step 8 – Check the Movex BOM against customer BOM
– Download BOM from Movex
– Compare against customer BOM
• Comparison done manually in Excel
• Not Standardised – each PE has his own way of doing it – adds the risk of not capturing all the
time all the possible issues
• Time Consuming
– Can we create a new Crystal report that has PN with multiple MPNs on multiple lines?
– Is BOM Comparison Tool still working? Can it be used to simplify this step?
– Can we organise External EXCEL Training to improve PE Excel skills?
– BOM is also send to customer to verify
• Some customers are checking it, some don’t
• Some customers have advanced tools for BOM check – we need something similar
– Trial BOM Connector tool from Siemens – it links with Valor MSS and possibly Movex
8

## Page 9

Initial Discussions
Step 9 – Optional – Purge
– Purge is still done on paper – time consuming – database could simplify the process
– Purge Template – end date for MPN doesn’t work – escalate to Karen and John B
Step 10 – Transmittal for PCB and Mechanical parts (build by drawing)
– All the Gerbers and drawings are uploaded in DMR
– Signed Transmittals are kept on S Drive
– Transmittals are requested and sent manually (PE asking Thu) or picked up by QA from
the ECN
– Manual search for Supplier Number to be added on Transmittal
– Notes are added in Transmittal for PCBs regarding panelisation
– Transmittal should have a database to be able to check/find what was sent, when, by
whom, etc.
–
9

## Page 10

Initial Discussions
Step 11 – Upload BOM in MTS
– BOM downloaded from Movex and uploaded in MTS?
– Can it be transferred automatically?
Step 12 – Create routings, process flow in MTS
10

## Page 11

Stargile (ComActivity) Issues & Improvement Suggestions
GENERAL
Stargile only works properly in Windows Internet Explorer 9 (very old version!). Needs update to work in latest browsers.
ECN RELATED
1. Would be good if we can create some pre-set process configurations and distribution lists based on the type of ECN
changes. Currently relying on initiator to select the right roles and enter the right names for every ECN one by one.
2. Process configuration and distribution list should be customizable. Eg, there are two mandatory doc control approvals which
is not necessary and just adds delays to ECN implementation.
3. There is no validation between the names entered in Distribution List and the roles ticked in Process Configuration and vice
versa. If a process is ticked but no name entered against the role the ECN goes to a random person. Vice versa if a name is
entered but role not ticked then that person will never receive the ECN. Very EASY TO MAKE MISTAKE!
4. Need to be able to upload files directly into an ECN (such as approvals, e-mails, working files, etc). Currently we have to
upload in DMR and then type the path into the ECN so that people can find the related files.
5. In View BoMs there is no validation when a duplicate sequence number is entered in a new BoM upload, or BoM update. If
you have duplicate sequence in a BoM upload, Stargile will only load one of the line items with a mixture of part number and
circuit references from the two separate lines – THIS MEANS WE CAN MISS TO ORDER A REQUIRED COMPONENT.
6. View BOM, MPN, ITEM, ROUTES buttons should be highlighted when there is information entered in them.
7. Bom Revision and ECN Text in PDS001 not in Stargile has to be updated manually.
8. Cannot delete customer Alias number via ECN, can only add additional Alias. If want to delete have to do in Movex.
9. Add extra columns to the ecn “View Items” summary screen – “Name” “Purchase Price” and “Currency”.
10. If two ECN’s created at same time affecting same p/n in same bom there is no warning message. If both ECN’s are at a
status prior to 50 only one of the updates will take affect.
11. Uploading items works even on ECN that is at status 95 – Complete
Also it lets you delete line items from the ECN even after Movex update is done.
12. In View Items it does not retain the old information of the change. The fields on the right should show what was before, and
the left what is the new information. All the fields just display whatever is the latest information in Movex after ECN is
completed. so there is no history of the changes.
11

## Page 12

Stargile (ComActivity) Issues & Improvement Suggestions
13.. ECR Implementation Schedule needs to be customizable, or at least we need CommActivity to update to add the following
checks:
A. AOI programs to be updated.
B. New wave pallets required?
C. MES update required?
D. Valor MSS update required?
14. Separate ECN’s required to create new items, upload routes, upload BoM & MPN. It would be good if all can be done in one
ECN, as it adds a lot of delay and processing time to some basic BoM updates.
15. When adding MPN’s the “currency” field is mandatory even though we don’t use it. Please make it non-manadatory as it’s
waste of time entering data there.
16. When adding MPN’s we have to enter the Movex manufacturer code, as well as the manufacturer name. Should be one or
the other as it wastes time to do both. The manufacturer code could be linked to Movex to display the name automatically.
MAINTENANCE RELATED
1. Can we have a customizable view’s that show all information we need in one page. eg. would be good to have one view that
displays Part Number, Description, Manufacturer, MPN, Stock On Hand.
2. Would be good to have more fields for MPN updates such as:
– Shelf life
– Packaging (eg. Tape & Reel, Tube, Tray, Bulk, etc.)
– EOL, Obsolete Status
– YEOL – Years to EOL
– Do Not Buy / Not Preferred status
– NRND – Not recommended for new designs
– MSL (Moisture Sensitivity Level)
12

## Tables

### Table 1 (Page 2)

|  |  |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- | --- |

### Table 2 (Page 3)

|  |  |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- | --- |

### Table 3 (Page 4)

| Trial BOM Connector tool from Siemens | – |  | it links with Valor MSS and possibly |
| --- | --- | --- | --- |
| Movex | None | None | None |

### Table 4 (Page 4)

|  |  |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- | --- |

### Table 5 (Page 5)

|  |  |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- | --- |

### Table 6 (Page 6)

|  |  |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- | --- |

### Table 7 (Page 7)

|  |  |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- | --- |

### Table 8 (Page 8)

| Trial BOM Connector tool from Siemens | – |  | it links with Valor MSS and possibly Movex |
| --- | --- | --- | --- |

### Table 9 (Page 8)

|  |  |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- | --- |

### Table 10 (Page 9)

| Transmittal should have a database to be able to check/find what was sent, when, by |
| --- |
| whom, etc. |

### Table 11 (Page 9)

|  |  |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- | --- |

### Table 12 (Page 10)

|  |  |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- | --- |

### Table 13 (Page 11)

|  |  |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- | --- |

### Table 14 (Page 12)

|  |  |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- | --- |
