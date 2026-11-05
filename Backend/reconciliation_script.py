#!/usr/bin/env python3
"""
Payout reconciliation: system payout report vs CUB bank Payout Transactions Report.
Match: system "Order ID" == bank "Merchant Ref"  (bank "RV<OrderID>" reversal rows -> original order)
Compare: Status, Amount
Usage: python3 main.py <system.csv> <bank.csv> -o out.xlsx
"""
import argparse, csv, re, sys
from pathlib import Path
import pandas as pd

def read_csv_any(path):
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as fh:
        rows = list(csv.reader(fh))
    hdr_idx = 0
    for i, row in enumerate(rows):
        cells = [c.strip().lower() for c in row]
        if any(c in ("merchant ref", "order id", "orderid", "merchant_ref") for c in cells):
            hdr_idx = i; break
    header = [c.strip() for c in rows[hdr_idx]]
    data = [r for r in rows[hdr_idx + 1:] if any(c.strip() for c in r)]
    data = [r + [""] * (len(header) - len(r)) if len(r) < len(header) else r[:len(header)] for r in data]
    return pd.DataFrame(data, columns=header).apply(lambda s: s.str.strip())

def pick(df, *cands):
    low = {c.lower(): c for c in df.columns}
    for c in cands:
        if c.lower() in low: return low[c.lower()]
    sys.exit(f"[error] none of {cands} found in columns {list(df.columns)}")

def norm_key(v): return re.sub(r"\s+", "", str(v)).upper()
def norm_amt(v):
    s = re.sub(r"[^\d.\-]", "", str(v))
    try: return round(float(s), 2)
    except: return None

STATUS_EQUIV = {
    "FAILED":     {"failed"},
    "FAILURE":    {"failed"},
    "REVERSED":   {"failed", "refunded"},
    "REVERSAL":   {"failed", "refunded"},
    "SUCCESS":    {"success", "successful", "completed", "processed"},
    "SUCCESSFUL": {"success", "successful", "completed", "processed"},
    "COMPLETED":  {"success", "successful", "completed", "processed"},
    "PROCESSED":  {"success", "successful", "completed", "processed"},
    "SETTLED":    {"success", "successful", "completed", "processed"},
    "PENDING":    {"pending", "processing", "initiated"},
    "PROCESSING": {"pending", "processing", "initiated"},
    "INITIATED":  {"pending", "processing", "initiated"},
    "REFUNDED":   {"refunded"},
}
def status_ok(bank_status, sys_status):
    b = str(bank_status).strip().upper(); s = str(sys_status).strip().lower()
    return s in STATUS_EQUIV.get(b, {b.lower()})

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("system_file"); ap.add_argument("bank_file")
    ap.add_argument("-o", "--output", default=None)
    ap.add_argument("--tolerance", type=float, default=0.01)
    a = ap.parse_args()

    sysdf, bankdf = read_csv_any(a.system_file), read_csv_any(a.bank_file)
    S_ID, S_ST, S_AMT = pick(sysdf, "Order ID"), pick(sysdf, "Status"), pick(sysdf, "Amount")
    S_UTR = "UTR" if "UTR" in sysdf.columns else None
    B_ID, B_ST, B_AMT = pick(bankdf, "Merchant Ref"), pick(bankdf, "Status"), pick(bankdf, "Amount")

    sysdf["_key"] = sysdf[S_ID].map(norm_key)
    sys_dups = sysdf[sysdf.duplicated("_key", keep=False) & (sysdf["_key"] != "")].sort_values("_key")
    sys_lookup = sysdf.drop_duplicates("_key", keep="first").set_index("_key")

    def resolve(mref):
        return mref[2:] if (mref.startswith("RV") and mref[2:] in sys_lookup.index and mref not in sys_lookup.index) else mref

    # bank -> system
    out, matched_keys = [], set()
    for _, b in bankdf.iterrows():
        mref = norm_key(b[B_ID]); key = resolve(mref)
        row = {"Txn Date": b.get("Txn Date", ""), "Bank Txn ID": b.get("Transaction ID", ""),
               "Merchant Ref": b[B_ID], "Ledger": b.get("Ledger", ""), "Matched Order ID": "",
               "Bank Status": b[B_ST], "System Status": "", "Status Match": "",
               "Bank Amount": norm_amt(b[B_AMT]), "System Amount": None, "Amount Match": "", "Amount Diff": None,
               "Bank UTR": b.get("Ref Id (UTR)", ""), "System UTR": "", "Bene Name": "", "Vendor": "",
               "Note": "reversal row -> matched to original order" if key != mref else "", "Result": ""}
        if key not in sys_lookup.index:
            row["Result"] = "NOT FOUND IN SYSTEM"; out.append(row); continue
        s = sys_lookup.loc[key]; matched_keys.add(key)
        sa, ba = norm_amt(s[S_AMT]), row["Bank Amount"]
        s_ok = status_ok(b[B_ST], s[S_ST])
        a_ok = sa is not None and ba is not None and abs(sa - ba) <= a.tolerance
        row.update({"Matched Order ID": s[S_ID], "System Status": s[S_ST], "Status Match": "Y" if s_ok else "N",
                    "System Amount": sa, "Amount Match": "Y" if a_ok else "N",
                    "Amount Diff": round(ba - sa, 2) if (sa is not None and ba is not None) else None,
                    "System UTR": s[S_UTR] if S_UTR else "", "Bene Name": s.get("Bene Name", ""), "Vendor": s.get("Vendor", ""),
                    "Result": "MATCHED" if s_ok and a_ok else "STATUS + AMOUNT MISMATCH" if not s_ok and not a_ok
                              else "STATUS MISMATCH" if not s_ok else "AMOUNT MISMATCH"})
        out.append(row)
    recon = pd.DataFrame(out)

    sys_only = sysdf[~sysdf["_key"].isin(matched_keys)].drop(columns="_key")
    keep = [c for c in ["Date Time", "Order ID", "Request ID", "Amount", "Status", "UTR", "Bene Name",
                        "Bank Name", "Account Number", "IFSC Code", "Vendor", "User Info"] if c in sys_only.columns]
    sys_only = sys_only[keep]

    # FULL sheet
    bank_by_key = {}
    for _, b in bankdf.iterrows():
        bank_by_key.setdefault(resolve(norm_key(b[B_ID])), []).append(b)
    def sys_cols(s):
        g = (lambda c: s.get(c, "")) if s is not None else (lambda c: "")
        return {"Order ID": s[S_ID] if s is not None else "", "System Date": g("Date Time"), "Request ID": g("Request ID"),
                "System Status": s[S_ST] if s is not None else "", "System Amount": norm_amt(s[S_AMT]) if s is not None else None,
                "System UTR": (s[S_UTR] if S_UTR else "") if s is not None else "", "Bene Name": g("Bene Name"),
                "Account Number": g("Account Number"), "IFSC Code": g("IFSC Code"), "Vendor": g("Vendor"), "User Info": g("User Info")}
    def bank_cols(b):
        g = (lambda c: b.get(c, "")) if b is not None else (lambda c: "")
        return {"Merchant Ref": b[B_ID] if b is not None else "", "Bank Txn Date": g("Txn Date"), "Bank Txn ID": g("Transaction ID"),
                "Ledger": g("Ledger"), "Bank Status": b[B_ST] if b is not None else "",
                "Bank Amount": norm_amt(b[B_AMT]) if b is not None else None, "Bank Fees": g("Fees"), "Bank GST": g("GST"),
                "Bank UTR": g("Ref Id (UTR)")}
    full = []
    for _, s in sysdf.drop_duplicates("_key", keep="first").iterrows():
        blist = bank_by_key.get(s["_key"])
        if not blist:
            full.append({**sys_cols(s), **bank_cols(None), "Status Match": "", "Amount Match": "", "Amount Diff": None,
                         "Result": "API PANEL (no vendor record)"}); continue
        for b in blist:
            sa, ba = norm_amt(s[S_AMT]), norm_amt(b[B_AMT])
            s_ok = status_ok(b[B_ST], s[S_ST])
            a_ok = sa is not None and ba is not None and abs(sa - ba) <= a.tolerance
            full.append({**sys_cols(s), **bank_cols(b), "Status Match": "Y" if s_ok else "N", "Amount Match": "Y" if a_ok else "N",
                         "Amount Diff": round(ba - sa, 2) if sa is not None and ba is not None else None,
                         "Result": "MATCHED" if s_ok and a_ok else "STATUS + AMOUNT MISMATCH" if not s_ok and not a_ok
                                   else "STATUS MISMATCH" if not s_ok else "AMOUNT MISMATCH"})
    for key, blist in bank_by_key.items():
        if key not in sys_lookup.index:
            for b in blist:
                full.append({**sys_cols(None), **bank_cols(b), "Status Match": "", "Amount Match": "", "Amount Diff": None,
                             "Result": "VENDOR ONLY (not in api panel)"})
    full = pd.DataFrame(full)
    order = {"STATUS + AMOUNT MISMATCH": 0, "STATUS MISMATCH": 1, "AMOUNT MISMATCH": 2,
             "VENDOR ONLY (not in api panel)": 3, "MATCHED": 4, "API PANEL (no vendor record)": 5}
    full["_o"] = full["Result"].map(order)
    full = full.sort_values(["_o", "System Date", "Bank Txn Date"]).drop(columns="_o").reset_index(drop=True)

    summ = full["Result"].value_counts().rename_axis("Result").reset_index(name="Count")
    summ = pd.concat([summ, pd.DataFrame([["Bank rows total", len(bankdf)], ["System rows total", len(sysdf)],
                      ["Duplicate Order IDs in system file", len(sys_dups)]], columns=["Result", "Count"])], ignore_index=True)
    sys_status_counts = sys_only["Status"].value_counts().rename_axis("System status (no vendor record)").reset_index(name="Count")

    out_path = Path(a.output or f"payout_recon_{Path(a.bank_file).stem[-10:]}.xlsx")
    with pd.ExcelWriter(out_path, engine="openpyxl") as xw:
        summ.to_excel(xw, sheet_name="Summary", index=False)
        sys_status_counts.to_excel(xw, sheet_name="Summary", index=False, startrow=len(summ) + 3)
        full.to_excel(xw, sheet_name="Full Recon", index=False)
        full[full["Result"].str.contains("MISMATCH|BANK ONLY")].to_excel(xw, sheet_name="Exceptions", index=False)
        recon.to_excel(xw, sheet_name="Vendor vs Api Panel", index=False)
        sys_only.to_excel(xw, sheet_name="Vendor not in Api Panel", index=False)
        if len(sys_dups):
            sys_dups.drop(columns="_key")[keep].to_excel(xw, sheet_name="Api Panel Duplicates", index=False)

        from openpyxl.styles import PatternFill, Font
        from openpyxl.utils import get_column_letter
        green, red, amber, grey = (PatternFill("solid", fgColor=c) for c in ("C6EFCE", "FFC7CE", "FFEB9C", "EDEDED"))
        for ws in xw.book.worksheets:
            for cell in ws[1]: cell.font = Font(bold=True)
            ws.freeze_panes = "A2"
            for i, col in enumerate(ws.columns, 1):
                w = max((len(str(c.value)) for c in col[:200] if c.value is not None), default=8)
                ws.column_dimensions[get_column_letter(i)].width = min(w + 2, 45)
            if ws.title in ("Bank vs System", "Exceptions", "Full Recon"):
                cols = list(recon.columns) if ws.title == "Bank vs System" else list(full.columns)
                rc = cols.index("Result") + 1
                for r in range(2, ws.max_row + 1):
                    v = str(ws.cell(r, rc).value or "")
                    ws.cell(r, rc).fill = (green if v == "MATCHED" else grey if v.startswith("SYSTEM ONLY")
                                           else amber if ("ONLY" in v or "NOT FOUND" in v) else red)
                ws.auto_filter.ref = ws.dimensions
                for name in ("Status Match", "Amount Match"):
                    c = cols.index(name) + 1
                    for r in range(2, ws.max_row + 1):
                        v = ws.cell(r, c).value
                        if v == "Y": ws.cell(r, c).fill = green
                        elif v == "N": ws.cell(r, c).fill = red

    print(summ.to_string(index=False))
    print(f"\nwritten -> {out_path.resolve()}")

if __name__ == "__main__":
    main()
