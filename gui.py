#!/usr/bin/env venv/bin/python3
"""Tkinter GUI for Cycle Sync — double-click to open, no terminal needed."""

import os
import subprocess
import threading
import tkinter as tk
import traceback
from datetime import date, timedelta

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.dialogs import Messagebox, Querybox

from google_auth_oauthlib.flow import InstalledAppFlow

from cycle_sync import (
    SCOPES,
    TOKEN_PATH,
    CREDENTIALS_PATH,
    SCRIPT_DIR,
    load_config,
    load_history,
    save_history,
    calculate_cycle_lengths,
    get_median_cycle_length,
    get_calendar_service,
    get_or_create_cycle_calendar,
    adjust_previous_luteal,
    delete_cycle_events,
    create_phase_events,
    calculate_phases,
)

# Soft rose/pink palette
ACCENT = "#dc3c50"
ACCENT_HOVER = "#c4293d"
ACCENT_LIGHT = "#f5e6e8"
CARD_BG = "#ffffff"
TEXT = "#3d2b2f"
TEXT_MUTED = "#8c7075"
DELETE_X = "#c47a7a"
DELETE_X_HOVER = "#dc3c50"
SUCCESS = "#5cb85c"
ERROR = "#d9534f"


class CycleTrackerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Cycle Tracker")
        self.root.resizable(False, False)
        self._busy = False

        self._setup_styles()

        if os.path.exists(TOKEN_PATH):
            self._build_main_ui()
        else:
            self._build_setup_ui()

    def _setup_styles(self):
        style = ttk.Style()
        style.configure(
            "Custom.Treeview",
            background=CARD_BG,
            foreground=TEXT,
            fieldbackground=CARD_BG,
            rowheight=36,
            font=("Helvetica", 12),
            borderwidth=0,
        )
        style.configure(
            "Custom.Treeview.Heading",
            background=ACCENT_LIGHT,
            foreground=TEXT,
            font=("Helvetica", 11, "bold"),
            relief="flat",
        )
        # Disable selection highlight completely — we don't need it anymore
        style.map(
            "Custom.Treeview",
            background=[("selected", CARD_BG)],
            foreground=[("selected", TEXT)],
        )

    # ── Setup screen (first launch) ─────────────────────────────────

    def _build_setup_ui(self):
        self._clear_root()
        self.root.geometry("440x280")

        outer = ttk.Frame(self.root, padding=20)
        outer.pack(expand=True, fill="both")

        card = ttk.Frame(outer, padding=30, bootstyle="default")
        card.pack(expand=True, fill="both")

        if not os.path.exists(CREDENTIALS_PATH):
            ttk.Label(
                card, text="\u2764", font=("Helvetica", 32), foreground=ACCENT,
            ).pack(pady=(0, 8))
            ttk.Label(
                card,
                text="credentials.json not found",
                font=("Helvetica", 15, "bold"),
                foreground=TEXT,
            ).pack(pady=(0, 6))
            ttk.Label(
                card,
                text="Place your credentials.json file\nin the app folder, then relaunch.",
                justify="center",
                foreground=TEXT_MUTED,
                font=("Helvetica", 12),
            ).pack(pady=(0, 18))
            ttk.Button(
                card,
                text="Open App Folder",
                command=self._open_app_folder,
                bootstyle="outline",
            ).pack()
        else:
            ttk.Label(
                card, text="\u2764", font=("Helvetica", 32), foreground=ACCENT,
            ).pack(pady=(0, 8))
            ttk.Label(
                card,
                text="Welcome!",
                font=("Helvetica", 15, "bold"),
                foreground=TEXT,
            ).pack(pady=(0, 6))
            ttk.Label(
                card,
                text="Click below to connect your\nGoogle Calendar account.",
                justify="center",
                foreground=TEXT_MUTED,
                font=("Helvetica", 12),
            ).pack(pady=(0, 18))
            self._auth_btn = ttk.Button(
                card,
                text="Authenticate",
                command=self._run_auth,
                bootstyle="danger",
            )
            self._auth_btn.pack(ipadx=20, ipady=4)
            self._setup_status = ttk.Label(
                card, text="", foreground=TEXT_MUTED, font=("Helvetica", 11),
            )
            self._setup_status.pack(pady=(14, 0))

    def _open_app_folder(self):
        subprocess.Popen(["open", SCRIPT_DIR])

    def _run_auth(self):
        if self._busy:
            return
        self._busy = True
        self._auth_btn.config(state="disabled")
        self._setup_status.config(text="Waiting for browser login...")
        threading.Thread(target=self._auth_thread, daemon=True).start()

    def _auth_thread(self):
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_PATH, SCOPES
            )
            creds = flow.run_local_server(port=0)
            with open(TOKEN_PATH, "w") as f:
                f.write(creds.to_json())
            self.root.after(0, self._auth_success)
        except Exception as e:
            self.root.after(0, lambda: self._auth_fail(str(e)))

    def _auth_success(self):
        self._busy = False
        self._build_main_ui()

    def _auth_fail(self, msg):
        self._busy = False
        self._auth_btn.config(state="normal")
        self._setup_status.config(text=f"Error: {msg}", foreground=ERROR)

    # ── Main tracker UI ─────────────────────────────────────────────

    def _build_main_ui(self):
        self._clear_root()
        self.root.geometry("540x520")

        container = ttk.Frame(self.root, padding=16)
        container.pack(expand=True, fill="both")

        # ── Header ──
        header = ttk.Frame(container)
        header.pack(fill="x", pady=(0, 12))

        title_frame = ttk.Frame(header)
        title_frame.pack(side="left")
        ttk.Label(
            title_frame, text="\u2764", font=("Helvetica", 20), foreground=ACCENT,
        ).pack(side="left", padx=(0, 8))
        ttk.Label(
            title_frame,
            text="Cycle Tracker",
            font=("Helvetica", 18, "bold"),
            foreground=TEXT,
        ).pack(side="left")

        self._median_label = ttk.Label(
            header, text="", font=("Helvetica", 12), foreground=TEXT_MUTED,
        )
        self._median_label.pack(side="right")

        # Accent line
        accent_bar = ttk.Frame(container, height=2)
        accent_bar.pack(fill="x", pady=(0, 12))
        accent_bar.configure(style="danger.TFrame")

        # ── Table ──
        table_frame = ttk.Frame(container)
        table_frame.pack(fill="both", expand=True, pady=(0, 16))

        cols = ("delete", "start_date", "cycle_length")
        self.tree = ttk.Treeview(
            table_frame,
            columns=cols,
            show="headings",
            selectmode="none",
            style="Custom.Treeview",
            height=8,
        )
        self.tree.heading("delete", text="", anchor="center")
        self.tree.heading("start_date", text="Start Date", anchor="center")
        self.tree.heading("cycle_length", text="Cycle Length", anchor="center")
        self.tree.column("delete", width=40, anchor="center", stretch=False)
        self.tree.column("start_date", width=225, anchor="center")
        self.tree.column("cycle_length", width=225, anchor="center")

        scrollbar = ttk.Scrollbar(
            table_frame, orient="vertical", command=self.tree.yview, bootstyle="round"
        )
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Row tags
        self.tree.tag_configure("even", background=ACCENT_LIGHT)
        self.tree.tag_configure("odd", background=CARD_BG)

        # Bind click on the delete column
        self.tree.bind("<ButtonRelease-1>", self._on_tree_click)

        # ── Bottom bar: [+ Add Date]  (big round today button)  status ──
        bottom = ttk.Frame(container)
        bottom.pack(fill="x")

        # Status (left)
        status_frame = ttk.Frame(bottom)
        status_frame.pack(side="left", anchor="s")
        self._status_dot = ttk.Label(
            status_frame, text="\u25cf", font=("Helvetica", 10), foreground=SUCCESS,
        )
        self._status_dot.pack(side="left", padx=(0, 5))
        self._status = ttk.Label(
            status_frame, text="Ready", font=("Helvetica", 11), foreground=TEXT_MUTED,
        )
        self._status.pack(side="left")

        # Add custom date button (right)
        self._add_date_btn = ttk.Button(
            bottom,
            text="+  Add Date",
            command=self._on_add_custom_date,
            bootstyle="outline-secondary",
        )
        self._add_date_btn.pack(side="right", anchor="s")

        # Big round "today" button (center)
        btn_size = 56
        self._today_canvas = tk.Canvas(
            bottom,
            width=btn_size,
            height=btn_size,
            highlightthickness=0,
            bd=0,
            bg=self.root.cget("bg"),
        )
        self._today_canvas.pack(anchor="s", pady=(0, 0))
        pad = 2
        self._circle_id = self._today_canvas.create_oval(
            pad, pad, btn_size - pad, btn_size - pad,
            fill=ACCENT, outline="", width=0,
        )
        self._plus_id = self._today_canvas.create_text(
            btn_size // 2, btn_size // 2,
            text="\u2795", font=("Helvetica", 18), fill="white",
        )
        self._today_canvas.bind("<Enter>", self._on_today_hover)
        self._today_canvas.bind("<Leave>", self._on_today_leave)
        self._today_canvas.bind("<ButtonRelease-1>", lambda e: self._on_add_today())

        self._refresh_table()

    # ── Table helpers ────────────────────────────────────────────────

    def _refresh_table(self):
        history = load_history()
        config = load_config()
        lengths = calculate_cycle_lengths(history)
        median = get_median_cycle_length(history, config["cycle_length_days"])

        self._median_label.config(text=f"median: {median}d")

        self.tree.delete(*self.tree.get_children())
        for i, start_str in enumerate(history):
            length_str = f"{lengths[i]} days" if i < len(lengths) else "\u2014"
            tag = "even" if i % 2 == 0 else "odd"
            self.tree.insert(
                "", "end", iid=start_str,
                values=("\u2715", start_str, length_str),
                tags=(tag,),
            )

    def _on_tree_click(self, event):
        """Handle click — if it's on the X column, trigger delete."""
        if self._busy:
            return
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)
        # #1 is the first column (delete)
        if col != "#1":
            return
        row_id = self.tree.identify_row(event.y)
        if row_id:
            self._on_delete(row_id)

    # ── Add today ───────────────────────────────────────────────────

    def _on_today_hover(self, _event):
        self._today_canvas.itemconfig(self._circle_id, fill=ACCENT_HOVER)

    def _on_today_leave(self, _event):
        self._today_canvas.itemconfig(self._circle_id, fill=ACCENT)

    def _on_add_today(self):
        if self._busy:
            return
        self._add_and_sync(date.today())

    # ── Add custom date ─────────────────────────────────────────────

    def _on_add_custom_date(self):
        if self._busy:
            return
        raw = Querybox.get_string(
            prompt="Enter period start date:",
            title="Add Date",
            initialvalue=date.today().isoformat(),
            parent=self.root,
        )
        if not raw:
            return
        raw = raw.strip()
        try:
            start_date = date.fromisoformat(raw)
        except ValueError:
            self._set_status("Invalid date \u2014 use YYYY-MM-DD", error=True)
            return
        self._add_and_sync(start_date)

    # ── Shared add & sync ───────────────────────────────────────────

    def _add_and_sync(self, start_date):
        self._busy = True
        self._set_buttons(False)
        self._set_status("Syncing...", working=True)
        threading.Thread(
            target=self._add_sync_thread, args=(start_date,), daemon=True
        ).start()

    def _add_sync_thread(self, start_date):
        try:
            config = load_config()
            history = load_history()

            start_str = start_date.isoformat()
            if start_str not in history:
                history.append(start_str)
                history.sort()
            save_history(history)

            service = get_calendar_service()
            calendar_id = get_or_create_cycle_calendar(service)
            cycle_length = get_median_cycle_length(
                history, config["cycle_length_days"]
            )

            adjust_previous_luteal(service, calendar_id, start_date)
            delete_cycle_events(service, calendar_id, from_date=start_date)
            phases = calculate_phases(
                start_date,
                cycle_length=cycle_length,
                period_length=config["period_length_days"],
                months_ahead=config["months_ahead"],
            )
            create_phase_events(service, calendar_id, phases)

            self.root.after(0, lambda: self._finish("Done!"))
        except BaseException as e:
            detail = traceback.format_exc()
            msg = str(e) or "Unknown error"
            self.root.after(0, lambda m=msg, d=detail: self._finish(m, error=True, detail=d))

    # ── Delete (per-row) ────────────────────────────────────────────

    def _on_delete(self, remove_str):
        if self._busy:
            return
        if Messagebox.yesno(
            f"Remove {remove_str} and its calendar events?",
            title="Confirm Delete",
            parent=self.root,
        ) != "Yes":
            return

        self._busy = True
        self._set_buttons(False)
        self._set_status(f"Deleting {remove_str}...", working=True)

        do_resync = Messagebox.yesno(
            "Also resync all calendar events?\n(Recommended if you removed a date in the middle.)",
            title="Resync?",
            parent=self.root,
        ) == "Yes"

        threading.Thread(
            target=self._delete_thread,
            args=(remove_str, do_resync),
            daemon=True,
        ).start()

    def _delete_thread(self, remove_str, do_resync):
        try:
            history = load_history()
            remove_date = date.fromisoformat(remove_str)

            if remove_str not in history:
                self.root.after(
                    0, lambda: self._finish(f"{remove_str} not in history", error=True)
                )
                return

            idx = history.index(remove_str)
            next_date = (
                date.fromisoformat(history[idx + 1])
                if idx + 1 < len(history)
                else None
            )

            service = get_calendar_service()
            calendar_id = get_or_create_cycle_calendar(service)

            delete_cycle_events(
                service, calendar_id, from_date=remove_date, to_date=next_date
            )

            if idx > 0 and next_date:
                adjust_previous_luteal(service, calendar_id, next_date)

            history.remove(remove_str)
            save_history(history)

            if do_resync and history:
                self.root.after(0, lambda: self._set_status("Resyncing...", working=True))
                self._resync_logic(service, calendar_id, history)

            self.root.after(0, lambda: self._finish("Done!"))
        except BaseException as e:
            detail = traceback.format_exc()
            msg = str(e) or "Unknown error"
            self.root.after(0, lambda m=msg, d=detail: self._finish(m, error=True, detail=d))

    # ── Resync (shared logic) ───────────────────────────────────────

    def _resync_logic(self, service, calendar_id, history):
        config = load_config()
        cycle_length = get_median_cycle_length(history, config["cycle_length_days"])
        first_date = date.fromisoformat(history[0])

        delete_cycle_events(service, calendar_id, from_date=first_date)

        all_phases = []
        for i, start_str in enumerate(history):
            start = date.fromisoformat(start_str)
            if i + 1 < len(history):
                actual_length = (date.fromisoformat(history[i + 1]) - start).days
            else:
                actual_length = cycle_length

            ovulation_day = actual_length // 2
            period_length = config["period_length_days"]

            period_end = start + timedelta(days=period_length - 1)
            follicular_start = period_end + timedelta(days=1)
            follicular_end = start + timedelta(days=ovulation_day - 2)
            ovulation_start = start + timedelta(days=ovulation_day - 1)
            ovulation_end = ovulation_start + timedelta(days=2)
            luteal_start = ovulation_end + timedelta(days=1)
            luteal_end = start + timedelta(days=actual_length - 1)

            all_phases.append(("Period", start, period_end))
            if follicular_start <= follicular_end:
                all_phases.append(("Follicular", follicular_start, follicular_end))
            all_phases.append(("Ovulation", ovulation_start, ovulation_end))
            if luteal_start <= luteal_end:
                all_phases.append(("Luteal", luteal_start, luteal_end))

        last_start = date.fromisoformat(history[-1])
        future_start = last_start + timedelta(days=cycle_length)
        future_phases = calculate_phases(
            future_start,
            cycle_length=cycle_length,
            period_length=config["period_length_days"],
            months_ahead=config["months_ahead"],
        )
        all_phases.extend(future_phases)
        create_phase_events(service, calendar_id, all_phases)

    # ── UI helpers ──────────────────────────────────────────────────

    def _clear_root(self):
        for w in self.root.winfo_children():
            w.destroy()

    def _set_status(self, text, error=False, working=False):
        text = text if text is not None else ""
        if error:
            color = ERROR
            dot = "\u25cf"
        elif working:
            color = ACCENT
            dot = "\u25cb"
        else:
            color = SUCCESS
            dot = "\u25cf"
        self._status_dot.config(text=dot, foreground=color)
        self._status.config(text=text)

    def _set_buttons(self, enabled):
        state = "normal" if enabled else "disabled"
        self._add_date_btn.config(state=state)
        canvas_state = "normal" if enabled else "hidden"
        self._today_canvas.itemconfig(self._circle_id, state=canvas_state)
        self._today_canvas.itemconfig(self._plus_id, state=canvas_state)

    def _finish(self, msg, error=False, detail=None):
        self._busy = False
        self._set_buttons(True)
        self._set_status(msg, error=error)
        self._refresh_table()
        if error and detail:
            self._show_error_detail(msg, detail)

    def _show_error_detail(self, msg, detail):
        win = tk.Toplevel(self.root)
        win.title("Error Details")
        win.geometry("560x320")
        win.resizable(True, True)

        frame = ttk.Frame(win, padding=12)
        frame.pack(expand=True, fill="both")

        ttk.Label(
            frame, text=msg, foreground=ERROR, font=("Helvetica", 12, "bold"),
            wraplength=520,
        ).pack(anchor="w", pady=(0, 8))

        txt = tk.Text(
            frame, wrap="word", font=("Courier", 10),
            background="#fff5f5", relief="flat", borderwidth=0,
        )
        txt.pack(expand=True, fill="both")
        txt.insert("1.0", detail)
        txt.config(state="disabled")

        ttk.Button(
            frame, text="Close", command=win.destroy, bootstyle="danger",
        ).pack(pady=(10, 0))


def main():
    root = ttk.Window(
        title="Cycle Tracker",
        themename="cosmo",
        resizable=(False, False),
    )
    CycleTrackerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
