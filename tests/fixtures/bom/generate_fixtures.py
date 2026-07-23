"""Regenerates the fixtures that are impractical to hand-author (Slice 0, ADR-012).

Run manually whenever these two fixtures need to change:
    python tests/fixtures/bom/generate_fixtures.py

- large_500.json: single-level BOM (B-1 shape) with 500 lines, for Slice B/D
  performance assertions (B-2 <2s live gate, Slice D 500-line <100ms unit assertion).
- customer_bom.xlsx: same rows as customer_bom.csv, with a blank title row above
  the header row (PLM's upload flow lets the user pick which row is the header;
  this fixture exercises that row is not always row 1).
"""

from __future__ import annotations

import json
from pathlib import Path

from openpyxl import Workbook

FIXTURES_DIR = Path(__file__).parent


def generate_large_500() -> None:
    records = []
    for i in range(500):
        seq = (i + 1) * 10
        records.append(
            {
                "MSEQ": seq,
                "MTNO": f"LF9{i:05d}",
                "ITDS": f"Generated Component {i}",
                "OPNO": 10 if i % 3 == 0 else 20,
                "CNQT": float((i % 10) + 1),
                "PEUN": "EA",
                "FDAT": 20240101,
                "TDAT": 99999999,
                "ITTY": "3",
                "STAT": "20",
            }
        )
    payload = {
        "data": {
            "head": {"PRNO": "LF900001", "STRT": "001", "FACI": "D", "ITDS": "Generated 500-Line Assembly"},
            "records": records,
        }
    }
    (FIXTURES_DIR / "large_500.json").write_text(json.dumps(payload, indent=2) + "\n")


def generate_customer_bom_xlsx() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "BOM Export"
    ws.append(["Customer BOM Export — generated 2026-07-22"])  # title row, not the header
    ws.append(["IPN", "CPN", "MFR1", "MPN1", "MFR2", "MPN2", "Designator", "Description", "Quantity", "Footprint"])
    ws.append(["LF200010", "CPN-1001", "STMicroelectronics", "STM32F103C8T6", "", "", "U1", "MCU 32-bit", 1, "LQFP48"])
    ws.append(["LF200011", "CPN-1002", "Murata", "GRM188R71H104KA93D", "Kemet", "C0603C104K5RACTU", "C1,C2,C3,C4", "Capacitor 100nF", 4, "0603"])
    ws.append(["LF200012", "CPN-1003", "Texas Instruments", "LM358", "", "", "U2", "Op-Amp Dual", 1, "SOIC8"])
    ws.append(["LF200013", "", "JST", "B4B-PH-K-S", "", "", "J1", "Connector 4-pin", 1, "PH"])
    ws.append(["LF200014", "CPN-1005", "", "", "", "", "", "PCB Bare Board", 1, "N/A"])
    ws.append(["LF200010", "CPN-1001", "STMicroelectronics", "STM32F103C8T6", "", "", "U5", "MCU 32-bit", "N/A", "LQFP48"])
    wb.save(FIXTURES_DIR / "customer_bom.xlsx")


if __name__ == "__main__":
    generate_large_500()
    generate_customer_bom_xlsx()
    print("Generated large_500.json and customer_bom.xlsx")
