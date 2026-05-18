"""
OSKAR — Scanfil APAC Part Number Commodity Code Table

Maps (procurement_group, product_group) → default 2-digit commodity code, plus
the full set of valid codes for that pair when multiple exist.

Scanfil APAC item number format for new items created via OSKAR:
    LF + {2-char CUNO} + {2-digit commodity} + {4-digit zero-padded seq}
    Example: LFAA120023  (customer AA, RESISTOR SMD, seq 23)

'LF' is the company prefix (legacy Startronics/Scanfil APAC identifier). It does NOT
encode lead-free status — the Lead Free Code field (BBB=Non-RoHS / PBF=RoHS) is a
separate MITMAS field, not part of the item number.

Source: Engineering Team's ecn_item_upload_v13 template (engineers meeting 2026-04-29).
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

# ── Template description names from Engineering Team's ecn_item_upload_v13 (2026-04-29) ──
#
# (prgp, itcl, commodity_code) → list[str]  (all template names for that code)
# All names are pre-validated ≤30 chars — the Movex hard limit.
# Engineers start from these and append specifics (e.g. "RESISTOR SMD 10K 1%").
# When a code maps to multiple names the UI shows them as a pick-list.
#
# Source: ecn xxxx_item_upload_v13_ecn_item_upload.csv, column "Item Name".
# Names that exceed 30 chars in the CSV are truncated here (marked with †).
_DESCRIPTION_RAW: list[tuple[str, str, str, str]] = [
    # prgp   itcl     code  template_name (≤30 chars)
    ("PCA",  "PCBA",  "05", "PRODUCT STOCK CODE"),
    ("CSP",  "CSP",   "XX", "CUSTOMER SUPPLIED PART"),
    ("PCB",  "RIGID", "10", "PCB RIGID"),
    ("PCB",  "FLEXI", "10", "PCB FLEX"),
    ("PAS",  "RES",   "11", "RESISTOR TH / THERMISTOR"),
    ("PAS",  "RES",   "12", "RESISTOR SMD"),
    ("PAS",  "RES",   "13", "RESNET / RESISTOR NETWORK"),     # † truncated from "RESNET, RESISTOR NETWORK / ARRAY"
    ("PAS",  "RES",   "14", "VARISTOR / TRIMPOT"),
    ("PAS",  "CAPS",  "20", "CAPACITOR TH"),
    ("PAS",  "CAPS",  "21", "CAPACITOR SMD"),
    ("PAS",  "CAPS",  "22", "VARIABLE CAPACITOR"),
    ("ACT",  "DIODE", "24", "DIODE TH"),
    ("ACT",  "DIODE", "25", "DIODE SMD"),
    ("ACT",  "LED",   "26", "LED"),
    ("EM",   "DISP",  "26", "LCD / DISPLAY / MONITOR"),
    ("PAS",  "XTAL",  "27", "CRYSTAL / OSCILLATOR"),
    ("ACT",  "XSTOR", "30", "TRANSISTOR, MOSFET, TH"),
    ("ACT",  "XSTOR", "31", "TRANSISTOR, MOSFET, SMD"),
    ("ACT",  "XSTOR", "32", "THYRISTOR / DIAC / TRIAC"),
    ("EM",   "CONNT", "35", "CONNECTOR TH"),
    ("EM",   "CONNT", "36", "CONNECTOR SMD"),
    ("EM",   "CONNT", "37", "CONNECTOR OTHER"),
    ("EM",   "CONNT", "38", "SOCKET"),
    ("ACT",  "IC",    "40", "IC TH"),
    ("ACT",  "IC",    "41", "IC SMD"),
    ("EM",   "SWTCH", "44", "SWITCH/BUTTON TH"),
    ("EM",   "SWTCH", "45", "SWITCH/BUTTON SMD"),
    ("ACT",  "IC",    "49", "OPTO-ELECTRONIC"),
    ("ACT",  "IC",    "51", "SENSOR"),
    ("MAG",  "RELAY", "52", "RELAY"),
    ("EM",   "TRFMR", "53", "TRANSFORMER"),
    ("EM",   "TRFMR", "53", "CONVERTER"),
    ("MAG",  "INDTR", "54", "INDUCTOR / CHOKE"),
    ("MAG",  "FUSE",  "55", "FUSE / POLYSWITCH"),
    ("HWR",  "ACCES", "55", "FUSE HOLDER"),
    ("MAG",  "INDTR", "55", "FILTER / SUPPRESSOR"),
    ("MAG",  "INDTR", "56", "FERRITE"),
    ("EM",   "RFDVC", "56", "ANTENNA"),
    ("EM",   "RFDVC", "57", "BUZZER"),
    ("EM",   "RFDVC", "57", "SPEAKER"),
    ("EM",   "RFDVC", "57", "MICROPHONE"),
    ("EM",   "BATT",  "58", "BATTERY"),
    ("EM",   "PSU",   "59", "POWER SUPPLY / ADAPTOR"),
    ("HWR",  "WIRES", "61", "WIRE"),
    ("EM",   "CBASY", "62", "CABLE ASSEMBLY / LOOM"),        # † truncated from "CABLE ASSEMBLY / LOOM / HARNESS"
    ("MET",  "DCAST", "64", "METAL PART (DIECAST)"),
    ("MET",  "MCHNG", "64", "METAL PART (MACHINING)"),
    ("MET",  "STAMP", "64", "METAL PART (METAL STAMPING)"),
    ("PLA",  "INJEC", "65", "PLASTIC PART INJECTION MOULD"),  # † truncated from "PLASTIC PART INJECTION MOULDING"
    ("PLA",  "PLAMC", "65", "PLASTIC PART MACHINING"),
    ("CUT",  "D-CUT", "65", "PLASTIC TEXTPLATES"),            # † truncated from "PLASTIC TEXTPLATES, NAMEPLATES, OVERLAYS"
    ("TEM",  "TEMP",  "66", "METAL / MECHANICAL COMPONENT"),
    ("MET",  "SPRNG", "66", "SPRING"),
    ("PLA",  "INJEC", "67", "PLASTIC COMPONENT OFF SHELF"),   # † truncated from "PLASTIC COMPONENT (OFF THE SHELF)"
    ("PLA",  "PLAMC", "67", "CABLE TIE"),
    ("PKG",  "INNBX", "68", "PACKAGING CARTON BOX PRINTED"),
    ("PKG",  "OUTBX", "68", "PACKAGING CARTON BOX SHIPPING"),
    ("PKG",  "RTAIL", "68", "PAPER PULP / VACUUM FORM TRAY"), # † truncated
    ("PKG",  "CFOAM", "68", "FOAM CUSTOM CUT/GASKET/PAD"),    # † truncated from "FOAM CUSTOM CUT/GASKET/PAD WITH ADHESIVE"
    ("PKG",  "BAG",   "68", "PACKAGING BAG"),
    ("HWR",  "HARDW", "69", "SCREW"),
    ("HWR",  "HARDW", "69", "WASHER"),
    ("HWR",  "HARDW", "69", "NUT"),
    ("HWR",  "HARDW", "69", "CRIMP / RIVET / SPACER"),        # † truncated from "CRIMP / RIVET / SPACER / STANDOFF / CIRCLIP"
    ("PKG",  "LABEL", "70", "LABEL"),
    ("PKG",  "PAPER", "70", "PRINTED MATERIAL / USER MAN"),   # † truncated from "PRINTED MATERIAL / USER MANUAL / ..."
    ("TEM",  "TEMP",  "76", "ELECTRICAL COMPONENT"),
    ("TEM",  "TEMP",  "81", "SOFTWARE / FIRMWARE"),
    ("PKG",  "TAPE",  "90", "TAPE"),
    ("RUB",  "RUBOT", "90", "RUBBER / GASKET / O-RING"),      # † truncated from "RUBBER / GASKET / O-RING / HEATSHRINK"
    ("RUB",  "RUBMD", "90", "RUBBER / GASKET / O-RING"),
    ("TEM",  "TEMP",  "90", "MISCELLANEOUS"),
    ("IDM",  "ADHES", "91", "ADHESIVE / GLUE / EPOXY"),
    ("IDM",  "CHEM",  "91", "CHEMICAL / FLUX / IPA"),         # † truncated from "CHEMICAL / FLUX / IPA / CONSUMABLE"
    ("IDM",  "SOLDR", "91", "SOLDER BAR / PASTE"),
]

# Validate at import time — catch truncation errors before runtime
for _p, _i, _c, _name in _DESCRIPTION_RAW:
    if len(_name) > 30:
        raise ValueError(
            f"DESCRIPTION_RAW entry exceeds 30 chars (Movex limit): "
            f"({_p}, {_i}, {_c}) → {_name!r} ({len(_name)} chars)"
        )

# (prgp, itcl, code) → [template_name, ...]
DESCRIPTION_TEMPLATES: dict[tuple[str, str, str], list[str]] = {}
for _p, _i, _c, _name in _DESCRIPTION_RAW:
    _key = (_p.upper(), _i.upper(), _c.upper())
    DESCRIPTION_TEMPLATES.setdefault(_key, [])
    if _name not in DESCRIPTION_TEMPLATES[_key]:
        DESCRIPTION_TEMPLATES[_key].append(_name)

MOVEX_DESCRIPTION_MAX_LEN: int = 30


def get_description_templates(
    procurement_group: str,
    product_group: str,
    commodity_code: str,
) -> list[str]:
    """Return canonical template names for a given (prgp, itcl, code) triple.

    Returns an empty list when the triple is not in the map — callers should
    fall back to free-text entry. All returned names are guaranteed ≤30 chars.
    """
    key = (procurement_group.upper(), product_group.upper(), commodity_code.upper())
    return DESCRIPTION_TEMPLATES.get(key, [])


# Characters illegal in Movex MITMAS.MMITDS (fixed-width, tab-delimited upload).
# Tab and pipe break record parsing; control chars and null corrupt records.
_ILLEGAL_CHARS: frozenset[str] = frozenset({"\t", "|", "\x00", "\n", "\r"})
_ILLEGAL_CONTROL_RANGE = range(0x01, 0x20)  # \x01–\x1f excluding space (0x20)


def validate_description(name: str) -> tuple[bool, str, list[str]]:
    """Validate a Movex MITMAS.MMITDS description string for Scanfil APAC.

    Checks:
      1. Length ≤ 30 characters (Movex hard limit — upload silently rejected otherwise)
      2. No illegal characters: tab, pipe, null byte, or ASCII control chars \\x01–\\x1f

    Returns:
        (is_valid, truncated, issues)
        is_valid  — True only when all checks pass.
        truncated — name truncated to 30 chars (identity when len ≤ 30).
        issues    — list of human-readable problem descriptions (empty when valid).
    """
    issues: list[str] = []
    truncated = name[:MOVEX_DESCRIPTION_MAX_LEN]

    if len(name) > MOVEX_DESCRIPTION_MAX_LEN:
        issues.append(
            f"Exceeds Movex 30-character limit ({len(name)} chars). "
            f"Truncated suggestion: {truncated!r}"
        )

    illegal_found: list[str] = []
    for ch in name:
        if ch in _ILLEGAL_CHARS or ord(ch) in _ILLEGAL_CONTROL_RANGE:
            label = repr(ch) if ch not in {"\t", "|", "\n", "\r"} else repr(ch)
            if label not in illegal_found:
                illegal_found.append(label)

    if illegal_found:
        issues.append(
            f"Illegal character(s) for Movex MITMAS field: {', '.join(illegal_found)}. "
            "Tab, pipe (|), newline, carriage return, and ASCII control chars are not allowed."
        )

    return len(issues) == 0, truncated, issues


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
