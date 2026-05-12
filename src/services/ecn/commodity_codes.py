"""
OSKAR — Scanfil APAC Part Number Commodity Code Table

Maps (procurement_group, product_group) → default 2-digit commodity code, plus
the full set of valid codes for that pair when multiple exist.

Scanfil APAC item number format for new items created via OSKAR:
    LF + {2-char CUNO} + {2-digit commodity} + {4-digit zero-padded seq}
    Example: LFAA120023  (customer AA, RESISTOR SMD, seq 23)

'LF' is the company prefix (legacy Startronics/SRXGlobal identifier). It does NOT
encode lead-free status — the Lead Free Code field (BBB=Non-RoHS / PBF=RoHS) is a
separate MITMAS field, not part of the item number.

Source: Nick's ecn_item_upload_v13 template (engineers meeting 2026-04-29).
All commodity entries from ecn_item_upload_v13_ecn_item_upload.csv.

When a (prgp, itcl) pair maps to multiple commodity codes (e.g. RES TH=11,
RES SMD=12), the engineer must supply commodity_override. The endpoint returns
the options list so the UI can prompt for clarification.
"""

from __future__ import annotations

# (procurement_group, product_group) → (default_code, [all_valid_codes])
# "default" is the most common/specific variant; "all" is what the UI offers.
_RAW: list[tuple[str, str, str]] = [
    # prgp   itcl     code
    ("PCA",  "PCBA",  "05"),
    ("PCB",  "RIGID", "10"),
    ("PCB",  "FLEXI", "10"),
    ("PAS",  "RES",   "11"),  # Resistor TH / Thermistor
    ("PAS",  "RES",   "12"),  # Resistor SMD  ← same key, two codes
    ("PAS",  "RES",   "13"),  # ResNet / Resistor Network
    ("PAS",  "RES",   "14"),  # Varistor / Trimpot
    ("PAS",  "CAPS",  "20"),  # Capacitor TH
    ("PAS",  "CAPS",  "21"),  # Capacitor SMD  ← same key, two codes
    ("PAS",  "CAPS",  "22"),  # Variable Capacitor
    ("PAS",  "XTAL",  "27"),
    ("ACT",  "DIODE", "24"),  # Diode TH
    ("ACT",  "DIODE", "25"),  # Diode SMD      ← same key, two codes
    ("ACT",  "LED",   "26"),
    ("EM",   "DISP",  "26"),  # LCD/Display/Monitor — different prgp from LED
    ("ACT",  "XSTOR", "30"),  # Transistor / MOSFET TH
    ("ACT",  "XSTOR", "31"),  # Transistor / MOSFET SMD
    ("ACT",  "XSTOR", "32"),  # Thyristor / DIAC / TRIAC
    ("EM",   "CONNT", "35"),  # Connector TH
    ("EM",   "CONNT", "36"),  # Connector SMD
    ("EM",   "CONNT", "37"),  # Connector Other
    ("EM",   "CONNT", "38"),  # Socket
    ("ACT",  "IC",    "40"),  # IC TH
    ("ACT",  "IC",    "41"),  # IC SMD
    ("ACT",  "IC",    "49"),  # Opto-Electronic
    ("ACT",  "IC",    "51"),  # Sensor
    ("EM",   "SWTCH", "44"),  # Switch/Button TH
    ("EM",   "SWTCH", "45"),  # Switch/Button SMD
    ("MAG",  "RELAY", "52"),
    ("EM",   "TRFMR", "53"),
    ("MAG",  "INDTR", "54"),  # Inductor / Choke / Filter / Ferrite
    ("MAG",  "INDTR", "55"),  # Filter/Suppressor — also 55 range
    ("MAG",  "INDTR", "56"),  # Ferrite
    ("MAG",  "FUSE",  "55"),
    ("HWR",  "ACCES", "55"),  # Fuse holder
    ("EM",   "RFDVC", "56"),  # Antenna
    ("EM",   "RFDVC", "57"),  # Buzzer / Speaker / Microphone
    ("EM",   "BATT",  "58"),
    ("EM",   "PSU",   "59"),
    ("HWR",  "WIRES", "61"),
    ("EM",   "CBASY", "62"),
    ("MET",  "DCAST", "64"),
    ("MET",  "MCHNG", "64"),
    ("MET",  "STAMP", "64"),
    ("PLA",  "INJEC", "65"),
    ("PLA",  "INJEC", "67"),  # Plastic component (off the shelf)
    ("PLA",  "PLAMC", "65"),
    ("PLA",  "PLAMC", "67"),  # Plastic machining — cable tie range
    ("CUT",  "D-CUT", "65"),
    ("TEM",  "TEMP",  "66"),
    ("TEM",  "TEMP",  "76"),  # Electrical component
    ("TEM",  "TEMP",  "81"),  # Software / firmware
    ("TEM",  "TEMP",  "90"),  # Miscellaneous
    ("MET",  "SPRNG", "66"),
    ("PKG",  "INNBX", "68"),
    ("PKG",  "OUTBX", "68"),
    ("PKG",  "RTAIL", "68"),
    ("PKG",  "CFOAM", "68"),
    ("PKG",  "BAG",   "68"),
    ("HWR",  "HARDW", "69"),
    ("PKG",  "LABEL", "70"),
    ("PKG",  "PAPER", "70"),
    ("IDM",  "ADHES", "91"),
    ("IDM",  "CHEM",  "91"),
    ("IDM",  "SOLDR", "91"),
    ("PKG",  "TAPE",  "90"),
    ("RUB",  "RUBOT", "90"),
    ("RUB",  "RUBMD", "90"),
    ("CSP",  "CSP",   "XX"),  # Customer-supplied — not sequenced
]

# Build: (prgp, itcl) → sorted list of valid commodity codes
_COMMODITY_MAP: dict[tuple[str, str], list[str]] = {}
for _prgp, _itcl, _code in _RAW:
    _key = (_prgp.upper(), _itcl.upper())
    _COMMODITY_MAP.setdefault(_key, [])
    if _code not in _COMMODITY_MAP[_key]:
        _COMMODITY_MAP[_key].append(_code)

# Freeze into sorted tuples
COMMODITY_MAP: dict[tuple[str, str], list[str]] = {
    k: sorted(v) for k, v in _COMMODITY_MAP.items()
}

# Flat sets for validation
VALID_PRODUCT_GROUPS: frozenset[str] = frozenset(itcl for _, itcl in COMMODITY_MAP)
VALID_PROCUREMENT_GROUPS: frozenset[str] = frozenset(prgp for prgp, _ in COMMODITY_MAP)


def get_commodity_code(
    procurement_group: str,
    product_group: str,
    commodity_override: str | None = None,
) -> tuple[str | None, list[str]]:
    """Return (selected_code, all_valid_codes) for a (prgp, itcl) pair.

    Returns:
        selected_code: commodity_override if provided and in the valid list,
                       else the first (lowest) code in the valid list,
                       else None if the pair is not in the map.
        all_valid_codes: all valid codes for this pair (for UI disambiguation).

    When len(all_valid_codes) > 1, the caller should prompt the engineer to
    confirm which commodity code applies (e.g. RES TH=11 vs RES SMD=12).
    """
    key = (procurement_group.upper(), product_group.upper())
    valid = COMMODITY_MAP.get(key, [])
    if not valid:
        return None, []
    if commodity_override is not None:
        override = commodity_override.upper().zfill(2)
        if override in valid:
            return override, valid
    return valid[0], valid
