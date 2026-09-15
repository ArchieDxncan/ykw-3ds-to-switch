#!/usr/bin/env python3
"""Small desktop interface for the YKW 3DS to Switch converter."""

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ykw_3ds_to_switch import DEFAULT_TEMPLATE, SaveError, atomic_write, convert


class ConverterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("YKW 3DS to Switch")
        self.geometry("590x280")
        self.minsize(520, 260)
        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.status = tk.StringVar(value="Select a Yo-kai Watch 1 3DS .yw save.")

        root = ttk.Frame(self, padding=24)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="Yo-kai Watch 1 Save Converter", font=("TkDefaultFont", 16, "bold")).pack(anchor="w")
        ttk.Label(root, text="3DS → Nintendo Switch", foreground="#555").pack(anchor="w", pady=(2, 20))

        row = ttk.Frame(root)
        row.pack(fill="x")
        ttk.Entry(row, textvariable=self.input_path).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Choose 3DS save…", command=self.choose_input).pack(side="left", padx=(8, 0))

        ttk.Button(root, text="Convert and save…", command=self.run_conversion).pack(anchor="w", pady=18)
        ttk.Separator(root).pack(fill="x", pady=(2, 12))
        ttk.Label(root, textvariable=self.status, wraplength=530).pack(anchor="w")
        ttk.Label(root, text="Always keep backups of both original saves.", foreground="#8a4b00").pack(anchor="w", pady=(10, 0))

    def choose_input(self):
        path = filedialog.askopenfilename(title="Select 3DS save", filetypes=(("Yo-kai Watch save", "*.yw"), ("All files", "*.*")))
        if path:
            self.input_path.set(path)

    def run_conversion(self):
        source = Path(self.input_path.get())
        if not source.is_file():
            messagebox.showerror("Missing save", "Choose a valid 3DS .yw save first.")
            return
        suggested = f"{source.stem}-switch.yw"
        output = filedialog.asksaveasfilename(title="Save converted file", defaultextension=".yw", initialfile=suggested,
                                              filetypes=(("Yo-kai Watch save", "*.yw"), ("All files", "*.*")))
        if not output:
            return
        try:
            result = convert(source.read_bytes(), DEFAULT_TEMPLATE.read_bytes())
            atomic_write(Path(output), result, force=True)
        except (OSError, SaveError) as exc:
            self.status.set(f"Conversion failed: {exc}")
            messagebox.showerror("Conversion failed", str(exc))
            return
        self.status.set(f"Created {output} ({len(result):,} bytes).")
        messagebox.showinfo("Conversion complete", "The converted Switch save was created successfully.")


if __name__ == "__main__":
    ConverterApp().mainloop()
