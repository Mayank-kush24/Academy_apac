#!/usr/bin/env python3
"""
Company Name Mapper — desktop app for mapping raw company names to BOB list.

Input CSV columns (flexible headers):
  - email
  - raw company (organization, company name, etc.)

Output CSV columns:
  - email
  - raw company
  - mapped company  (unchanged when no BOB match)

Requirements:
  - Python 3.10+
  - pip install rapidfuzz pandas openpyxl
  - data/company_index.pkl.gz (run: python scripts/build_company_index.py)

Usage:
  python scripts/company_mapper_app.py

Windows: double-click run_company_mapper.bat
"""
from __future__ import annotations

import csv
import os
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

DEFAULT_INDEX = _ROOT / "data" / "company_index.pkl.gz"

EMAIL_ALIASES = frozenset({"email", "e-mail", "e mail", "mail", "email address", "emailaddress"})
COMPANY_ALIASES = frozenset({
    "company", "company name", "raw company", "organization", "organization_name",
    "org", "org name", "college/school/company/startup name",
})


def _norm_header(value: str) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())


def _detect_columns(fieldnames: list[str]) -> tuple[str | None, str | None]:
    email_col = company_col = None
    for name in fieldnames:
        norm = _norm_header(name)
        if norm in EMAIL_ALIASES and email_col is None:
            email_col = name
        if norm in COMPANY_ALIASES and company_col is None:
            company_col = name
    if email_col is None:
        for name in fieldnames:
            if "email" in _norm_header(name):
                email_col = name
                break
    if company_col is None:
        for name in fieldnames:
            norm = _norm_header(name)
            if "company" in norm or "organization" in norm or norm == "org":
                company_col = name
                break
    return email_col, company_col


def _default_output_path(input_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return input_path.with_name(f"{input_path.stem}_companies_mapped_{stamp}.csv")


def _read_input_csv(path: Path) -> tuple[list[str], list[dict[str, str]], str, str]:
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("The CSV file has no header row.")
        email_col, company_col = _detect_columns(list(reader.fieldnames))
        if not company_col:
            raise ValueError(
                "Could not find a company column. Expected a header like: "
                "organization, company name, or organization_name"
            )
        rows = list(reader)
    return list(reader.fieldnames), rows, email_col or "", company_col


def _process_file(input_path: Path, output_path: Path, progress_cb, done_cb, error_cb):
    try:
        from server.utils.company_map import get_bob_company, map_company

        _, rows, email_col, company_col = _read_input_csv(input_path)
        total = len(rows)
        if total == 0:
            raise ValueError("The input CSV has no data rows.")

        matched = 0
        output_rows: list[dict[str, str]] = []
        for i, row in enumerate(rows, start=1):
            email = (row.get(email_col) or "").strip() if email_col else ""
            raw_company = (row.get(company_col) or "").strip()
            mapped = map_company(raw_company)
            if raw_company and get_bob_company(raw_company):
                matched += 1
            output_rows.append({
                "email": email,
                "raw company": raw_company,
                "mapped company": mapped,
            })
            if i % 25 == 0 or i == total:
                progress_cb(i, total)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["email", "raw company", "mapped company"],
            )
            writer.writeheader()
            writer.writerows(output_rows)

        done_cb({
            "total": total,
            "matched": matched,
            "unchanged": total - matched,
            "output": output_path,
        })
    except Exception as exc:
        error_cb(str(exc))


class CompanyMapperApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Company Name Mapper")
        self.geometry("720x620")
        self.minsize(640, 560)
        self.configure(bg="#f4f6f8")

        self.input_path: Path | None = None
        self.output_path: Path | None = None
        self._worker: threading.Thread | None = None

        self._build_styles()
        self._build_ui()
        self._check_index()

    def _build_styles(self):
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Header.TLabel", font=("Segoe UI", 20, "bold"), background="#f4f6f8")
        style.configure("Sub.TLabel", font=("Segoe UI", 10), background="#f4f6f8", foreground="#555")
        style.configure("Card.TLabelframe", padding=16)
        style.configure("Card.TLabelframe.Label", font=("Segoe UI", 11, "bold"))
        style.configure("Primary.TButton", font=("Segoe UI", 11, "bold"), padding=(16, 10))
        style.configure("Secondary.TButton", font=("Segoe UI", 10), padding=(12, 8))

    def _build_ui(self):
        container = ttk.Frame(self, padding=24)
        container.pack(fill=tk.BOTH, expand=True)

        ttk.Label(container, text="Company Name Mapper", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            container,
            text="Upload a CSV with email and company columns. "
                 "Download a mapped file where each company is matched to the "
                 "Book of Business list, or left unchanged when no match is found.",
            style="Sub.TLabel",
            wraplength=660,
        ).pack(anchor="w", pady=(4, 18))

        steps = ttk.LabelFrame(container, text="How it works", style="Card.TLabelframe")
        steps.pack(fill=tk.X, pady=(0, 16))
        for text in [
            "1. Choose your input CSV (email + raw company / organization).",
            "2. Click Map Companies — fuzzy matching uses the BOB reference list.",
            "3. Open the output CSV; unmatched names stay exactly as entered.",
        ]:
            ttk.Label(steps, text=text, wraplength=640).pack(anchor="w", pady=2)

        input_card = ttk.LabelFrame(container, text="Input file", style="Card.TLabelframe")
        input_card.pack(fill=tk.X, pady=(0, 12))
        self.input_var = tk.StringVar(value="No file selected")
        ttk.Label(input_card, textvariable=self.input_var, wraplength=600).pack(
            anchor="w", pady=(0, 10)
        )
        ttk.Button(
            input_card, text="Browse CSV…", style="Secondary.TButton", command=self._pick_input
        ).pack(anchor="w")

        output_card = ttk.LabelFrame(container, text="Output file", style="Card.TLabelframe")
        output_card.pack(fill=tk.X, pady=(0, 16))
        self.output_var = tk.StringVar(value="Auto-generated next to input file")
        ttk.Label(output_card, textvariable=self.output_var, wraplength=600).pack(
            anchor="w", pady=(0, 10)
        )
        ttk.Button(
            output_card, text="Choose save location…", style="Secondary.TButton",
            command=self._pick_output,
        ).pack(anchor="w")

        self.process_btn = ttk.Button(
            container, text="Map Companies", style="Primary.TButton", command=self._start_processing
        )
        self.process_btn.pack(fill=tk.X, pady=(0, 12))

        self.progress = ttk.Progressbar(container, mode="determinate", maximum=100)
        self.progress.pack(fill=tk.X, pady=(0, 8))

        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(container, textvariable=self.status_var, wraplength=660).pack(anchor="w")

        result_card = ttk.LabelFrame(container, text="Results", style="Card.TLabelframe")
        result_card.pack(fill=tk.BOTH, expand=True, pady=(16, 0))
        self.result_var = tk.StringVar(value="No run yet.")
        ttk.Label(result_card, textvariable=self.result_var, wraplength=620).pack(
            anchor="w", pady=(0, 10)
        )
        btn_row = ttk.Frame(result_card)
        btn_row.pack(anchor="w")
        self.open_file_btn = ttk.Button(
            btn_row, text="Open output CSV", style="Secondary.TButton",
            command=self._open_output_file, state=tk.DISABLED,
        )
        self.open_file_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.open_folder_btn = ttk.Button(
            btn_row, text="Open folder", style="Secondary.TButton",
            command=self._open_output_folder, state=tk.DISABLED,
        )
        self.open_folder_btn.pack(side=tk.LEFT)

    def _check_index(self):
        if not DEFAULT_INDEX.is_file():
            messagebox.showwarning(
                "Company index missing",
                "The BOB company reference index was not found.\n\n"
                f"Expected:\n{DEFAULT_INDEX}\n\n"
                "Ask your admin to run:\n"
                "python scripts/build_company_index.py",
            )

    def _pick_input(self):
        path = filedialog.askopenfilename(
            title="Select input CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        self.input_path = Path(path)
        self.input_var.set(str(self.input_path))
        if self.output_path is None:
            self.output_var.set(str(_default_output_path(self.input_path)))

    def _pick_output(self):
        initial = str(
            self.output_path
            or (self.input_path and _default_output_path(self.input_path))
            or _ROOT
        )
        path = filedialog.asksaveasfilename(
            title="Save mapped CSV as",
            defaultextension=".csv",
            initialfile=Path(initial).name,
            initialdir=str(Path(initial).parent),
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        self.output_path = Path(path)
        self.output_var.set(str(self.output_path))

    def _resolve_output_path(self) -> Path:
        if self.output_path:
            return self.output_path
        if self.input_path:
            return _default_output_path(self.input_path)
        raise ValueError("No output path selected.")

    def _start_processing(self):
        if self._worker and self._worker.is_alive():
            return
        if not self.input_path or not self.input_path.is_file():
            messagebox.showerror("Missing input", "Please choose an input CSV file first.")
            return
        if not DEFAULT_INDEX.is_file():
            messagebox.showerror(
                "Company index missing",
                "Cannot map companies without the BOB reference index.\n"
                "Run: python scripts/build_company_index.py",
            )
            return

        try:
            output_path = self._resolve_output_path()
        except ValueError as exc:
            messagebox.showerror("Missing output", str(exc))
            return

        self.process_btn.config(state=tk.DISABLED)
        self.open_file_btn.config(state=tk.DISABLED)
        self.open_folder_btn.config(state=tk.DISABLED)
        self.progress["value"] = 0
        self.status_var.set("Processing…")
        self.result_var.set("Working…")

        def progress_cb(current, total):
            pct = int(current * 100 / total) if total else 0
            self.after(0, lambda: self._update_progress(pct, f"Mapped {current:,} of {total:,} rows…"))

        def done_cb(stats):
            self.after(0, lambda: self._on_done(stats))

        def error_cb(message):
            self.after(0, lambda: self._on_error(message))

        self._worker = threading.Thread(
            target=_process_file,
            args=(self.input_path, output_path, progress_cb, done_cb, error_cb),
            daemon=True,
        )
        self._worker.start()

    def _update_progress(self, pct: int, status: str):
        self.progress["value"] = pct
        self.status_var.set(status)

    def _on_done(self, stats: dict):
        self.output_path = stats["output"]
        self.output_var.set(str(self.output_path))
        self.progress["value"] = 100
        self.status_var.set("Done.")
        self.result_var.set(
            f"Processed {stats['total']:,} rows.\n"
            f"Matched to BOB: {stats['matched']:,}\n"
            f"Left unchanged: {stats['unchanged']:,}\n"
            f"Saved to:\n{self.output_path}"
        )
        self.process_btn.config(state=tk.NORMAL)
        self.open_file_btn.config(state=tk.NORMAL)
        self.open_folder_btn.config(state=tk.NORMAL)
        messagebox.showinfo("Complete", f"Mapping finished.\n\nOutput saved to:\n{self.output_path}")

    def _on_error(self, message: str):
        self.progress["value"] = 0
        self.status_var.set("Failed.")
        self.result_var.set(message)
        self.process_btn.config(state=tk.NORMAL)
        messagebox.showerror("Error", message)

    def _open_output_file(self):
        if self.output_path and self.output_path.is_file():
            os.startfile(self.output_path)  # noqa: S606

    def _open_output_folder(self):
        if self.output_path and self.output_path.parent.is_dir():
            os.startfile(self.output_path.parent)  # noqa: S606


def main():
    app = CompanyMapperApp()
    app.mainloop()


if __name__ == "__main__":
    main()
