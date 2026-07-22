#!/usr/bin/env python3
"""
Job Title Mapper — desktop app for client CSV title mapping.

Input CSV columns (flexible headers):
  - email
  - raw job title (title, designation, job title, etc.)

Output CSV columns:
  - email
  - raw title
  - matched title
  - broad category

Requirements:
  - Python 3.10+
  - pip install rapidfuzz pandas
  - data/title_index.pkl.gz (run: python scripts/build_title_index.py)

Usage:
  python scripts/title_mapper_app.py

Windows: double-click run_title_mapper.bat
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

DEFAULT_INDEX = _ROOT / "data" / "title_index.pkl.gz"

EMAIL_ALIASES = frozenset({"email", "e-mail", "e mail", "mail", "email address", "emailaddress"})
TITLE_ALIASES = frozenset({
    "title", "job title", "raw title", "raw job title", "designation",
    "job_title", "jobtitle", "role", "position", "raw designation",
})


def _norm_header(value: str) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())


def _detect_columns(fieldnames: list[str]) -> tuple[str | None, str | None]:
    email_col = title_col = None
    for name in fieldnames:
        norm = _norm_header(name)
        if norm in EMAIL_ALIASES and email_col is None:
            email_col = name
        if norm in TITLE_ALIASES and title_col is None:
            title_col = name
    if email_col is None:
        for name in fieldnames:
            if "email" in _norm_header(name):
                email_col = name
                break
    if title_col is None:
        for name in fieldnames:
            norm = _norm_header(name)
            if "title" in norm or "designation" in norm or norm in {"role", "position"}:
                title_col = name
                break
    return email_col, title_col


def _default_output_path(input_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return input_path.with_name(f"{input_path.stem}_mapped_{stamp}.csv")


def _map_title(raw_title: str) -> tuple[str, str]:
    from server.utils.title_map import get_title_categories

    sub, broad = get_title_categories(raw_title)
    return sub or "", broad or ""


def _read_input_csv(path: Path) -> tuple[list[str], list[dict[str, str]], str, str]:
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("The CSV file has no header row.")
        email_col, title_col = _detect_columns(list(reader.fieldnames))
        if not email_col:
            raise ValueError(
                "Could not find an email column. Expected a header like: email"
            )
        if not title_col:
            raise ValueError(
                "Could not find a job title column. Expected a header like: "
                "raw job title, title, or designation"
            )
        rows = list(reader)
    return list(reader.fieldnames), rows, email_col, title_col


def _process_file(input_path: Path, output_path: Path, progress_cb, done_cb, error_cb):
    try:
        _, rows, email_col, title_col = _read_input_csv(input_path)
        total = len(rows)
        if total == 0:
            raise ValueError("The input CSV has no data rows.")

        matched = 0
        output_rows: list[dict[str, str]] = []
        for i, row in enumerate(rows, start=1):
            email = (row.get(email_col) or "").strip()
            raw_title = (row.get(title_col) or "").strip()
            matched_title, broad = _map_title(raw_title)
            if matched_title and broad:
                matched += 1
            output_rows.append({
                "email": email,
                "raw title": raw_title,
                "matched title": matched_title,
                "broad category": broad,
            })
            if i % 25 == 0 or i == total:
                progress_cb(i, total)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["email", "raw title", "matched title", "broad category"],
            )
            writer.writeheader()
            writer.writerows(output_rows)

        done_cb({
            "total": total,
            "matched": matched,
            "unmatched": total - matched,
            "output": output_path,
        })
    except Exception as exc:
        error_cb(str(exc))


class TitleMapperApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Job Title Mapper")
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

        ttk.Label(container, text="Job Title Mapper", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            container,
            text="Upload a CSV with email and job title columns. "
                 "Download a mapped file with matched title and broad category.",
            style="Sub.TLabel",
            wraplength=660,
        ).pack(anchor="w", pady=(4, 18))

        steps = ttk.LabelFrame(container, text="How it works", style="Card.TLabelframe")
        steps.pack(fill=tk.X, pady=(0, 16))
        for i, text in enumerate([
            "1. Choose your input CSV (email + raw job title).",
            "2. Click Map Titles — fuzzy matching uses the client title reference list.",
            "3. Open the output CSV with four columns ready to share.",
        ], start=1):
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
            container, text="Map Titles", style="Primary.TButton", command=self._start_processing
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
                "Title index missing",
                "The title reference index was not found.\n\n"
                f"Expected:\n{DEFAULT_INDEX}\n\n"
                "Ask your admin to run:\n"
                "python scripts/build_title_index.py",
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
            suggested = _default_output_path(self.input_path)
            self.output_var.set(str(suggested))

    def _pick_output(self):
        initial = str(self.output_path or (self.input_path and _default_output_path(self.input_path)) or _ROOT)
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
                "Title index missing",
                "Cannot map titles without the reference index.\n"
                "Run: python scripts/build_title_index.py",
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
            f"Matched: {stats['matched']:,}\n"
            f"Unmatched / excluded: {stats['unmatched']:,}\n"
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
            os.startfile(self.output_path)  # noqa: S606 — Windows convenience for client tool

    def _open_output_folder(self):
        if self.output_path and self.output_path.parent.is_dir():
            os.startfile(self.output_path.parent)  # noqa: S606


def main():
    app = TitleMapperApp()
    app.mainloop()


if __name__ == "__main__":
    main()
