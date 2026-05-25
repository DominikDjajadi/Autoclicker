import threading
import tkinter as tk
from tkinter import messagebox, ttk

import autoclicker
import recorder
from macro_editor import MacroEditor


class AutoclickerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Autoclicker")
        self.root.resizable(False, False)

        self._click_stop = threading.Event()
        self._click_thread: threading.Thread | None = None

        self._macro_recorder = recorder.MacroRecorder(on_stop=self._on_macro_record_stopped)
        self._recorded_events: list[dict] = []
        self._play_stop = threading.Event()
        self._play_thread: threading.Thread | None = None

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        padding = {"padx": 12, "pady": 6}

        main = ttk.Frame(self.root, padding=16)
        main.grid(row=0, column=0, sticky="nsew")

        ttk.Label(main, text="Click interval (seconds)").grid(
            row=0, column=0, columnspan=2, sticky="w", **padding
        )

        self.interval_var = tk.StringVar(value="1.0")
        interval_entry = ttk.Spinbox(
            main,
            from_=0.01,
            to=60.0,
            increment=0.1,
            textvariable=self.interval_var,
            width=10,
            format="%.2f",
        )
        interval_entry.grid(row=1, column=0, sticky="w", **padding)

        self.cps_label = ttk.Label(main, text="≈ 1.0 CPS")
        self.cps_label.grid(row=1, column=1, sticky="w", **padding)

        self.interval_var.trace_add("write", self._update_cps_label)

        click_row = ttk.Frame(main)
        click_row.grid(row=2, column=0, columnspan=2, **padding)

        self.start_btn = ttk.Button(
            click_row, text="Start", command=self.start_clicking, width=12
        )
        self.start_btn.grid(row=0, column=0, padx=(0, 6))

        self.stop_btn = ttk.Button(
            click_row, text="Stop", command=self.stop_clicking, width=12, state="disabled"
        )
        self.stop_btn.grid(row=0, column=1)

        self.status_var = tk.StringVar(value="Stopped")
        ttk.Label(main, textvariable=self.status_var).grid(
            row=3, column=0, columnspan=2, sticky="w", **padding
        )

        ttk.Separator(main, orient="horizontal").grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(4, 8)
        )

        ttk.Label(main, text="Macro", font=("Segoe UI", 10, "bold")).grid(
            row=5, column=0, columnspan=2, sticky="w", **padding
        )

        ttk.Label(main, text="Name").grid(row=6, column=0, sticky="w", **padding)
        self.macro_name_var = tk.StringVar(value="")
        self.macro_name_entry = ttk.Entry(main, textvariable=self.macro_name_var, width=28)
        self.macro_name_entry.grid(row=6, column=1, sticky="w", **padding)

        macro_record_row = ttk.Frame(main)
        macro_record_row.grid(row=7, column=0, columnspan=2, **padding)

        self.record_btn = ttk.Button(
            macro_record_row, text="Record", command=self.start_recording, width=12
        )
        self.record_btn.grid(row=0, column=0, padx=(0, 6))

        self.stop_record_btn = ttk.Button(
            macro_record_row,
            text="Stop Record",
            command=self.stop_recording,
            width=12,
            state="disabled",
        )
        self.stop_record_btn.grid(row=0, column=1, padx=(0, 6))

        self.save_macro_btn = ttk.Button(
            macro_record_row, text="Save", command=self.save_macro, width=8, state="disabled"
        )
        self.save_macro_btn.grid(row=0, column=2)

        ttk.Label(main, text="Saved macro").grid(row=8, column=0, sticky="w", **padding)
        self.macro_list_var = tk.StringVar()
        self.macro_combo = ttk.Combobox(
            main, textvariable=self.macro_list_var, state="readonly", width=26
        )
        self.macro_combo.grid(row=8, column=1, sticky="w", **padding)
        self.macro_combo.bind("<<ComboboxSelected>>", self._on_macro_selected)
        self._refresh_macro_list()

        macro_play_row = ttk.Frame(main)
        macro_play_row.grid(row=9, column=0, columnspan=2, **padding)

        self.play_macro_btn = ttk.Button(
            macro_play_row, text="Play", command=self.play_macro, width=12
        )
        self.play_macro_btn.grid(row=0, column=0, padx=(0, 6))

        self.stop_play_btn = ttk.Button(
            macro_play_row,
            text="Stop Play",
            command=self.stop_playing,
            width=12,
            state="disabled",
        )
        self.stop_play_btn.grid(row=0, column=1, padx=(0, 6))

        self.edit_macro_btn = ttk.Button(
            macro_play_row, text="Edit", command=self.open_macro_editor, width=8
        )
        self.edit_macro_btn.grid(row=0, column=2)

        self.macro_status_var = tk.StringVar(
            value="Enter a name, then Record. Press F2 to stop."
        )
        ttk.Label(main, textvariable=self.macro_status_var, wraplength=320).grid(
            row=10, column=0, columnspan=2, sticky="w", **padding
        )

        ttk.Separator(main, orient="horizontal").grid(
            row=11, column=0, columnspan=2, sticky="ew", pady=(4, 8)
        )

        ttk.Label(
            main,
            text="Move the mouse to any screen corner to trigger PyAutoGUI failsafe.",
            wraplength=320,
            foreground="gray",
        ).grid(row=12, column=0, columnspan=2, sticky="w", **padding)

    def _update_cps_label(self, *_args) -> None:
        try:
            interval = float(self.interval_var.get())
            if interval > 0:
                self.cps_label.config(text=f"≈ {1 / interval:.1f} CPS")
            else:
                self.cps_label.config(text="—")
        except ValueError:
            self.cps_label.config(text="—")

    def _parse_interval(self) -> float | None:
        try:
            interval = float(self.interval_var.get())
        except ValueError:
            self.status_var.set("Invalid interval")
            return None
        if interval <= 0:
            self.status_var.set("Interval must be greater than 0")
            return None
        return interval

    def _click_loop(self, interval: float) -> None:
        while not self._click_stop.is_set():
            autoclicker.click()
            if self._click_stop.wait(interval):
                break

    def start_clicking(self) -> None:
        if self._click_thread and self._click_thread.is_alive():
            return
        if self._macro_recorder.is_recording:
            messagebox.showwarning("Busy", "Stop macro recording before starting the clicker.")
            return
        if self._play_thread and self._play_thread.is_alive():
            messagebox.showwarning("Busy", "Stop macro playback before starting the clicker.")
            return

        interval = self._parse_interval()
        if interval is None:
            return

        self._click_stop.clear()
        self._click_thread = threading.Thread(
            target=self._click_loop, args=(interval,), daemon=True
        )
        self._click_thread.start()

        self.status_var.set(f"Running — every {interval:.2f}s")
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")

    def stop_clicking(self) -> None:
        self._click_stop.set()
        if self._click_thread:
            self._click_thread.join(timeout=2)
            self._click_thread = None

        self.status_var.set("Stopped")
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")

    def _refresh_macro_list(self) -> None:
        names = recorder.list_macros()
        self.macro_combo["values"] = names
        if names and not self.macro_list_var.get():
            self.macro_list_var.set(names[0])

    def _on_macro_selected(self, _event=None) -> None:
        name = self.macro_list_var.get()
        if name:
            self.macro_name_var.set(name)

    def _parse_macro_name(self) -> str | None:
        name = self.macro_name_var.get().strip()
        if not name:
            messagebox.showwarning(
                "Name required",
                "Enter a macro name in the Name field before recording.",
            )
            return None
        try:
            recorder._sanitize_name(name)
        except ValueError as exc:
            messagebox.showerror("Invalid name", str(exc))
            return None
        return name

    def _set_recording_ui(self, recording: bool) -> None:
        self.record_btn.config(state="disabled" if recording else "normal")
        self.stop_record_btn.config(state="normal" if recording else "disabled")
        self.play_macro_btn.config(state="disabled" if recording else "normal")
        self.start_btn.config(state="disabled" if recording else "normal")
        self.macro_name_entry.config(state="disabled" if recording else "normal")

    def start_recording(self) -> None:
        if self._macro_recorder.is_recording:
            return
        if self._click_thread and self._click_thread.is_alive():
            messagebox.showwarning("Busy", "Stop the clicker before recording a macro.")
            return
        if self._play_thread and self._play_thread.is_alive():
            messagebox.showwarning("Busy", "Stop macro playback before recording.")
            return
        if self._parse_macro_name() is None:
            self.macro_name_entry.focus_set()
            return

        self._recorded_events = []
        self.save_macro_btn.config(state="disabled")
        self._set_recording_ui(True)
        self.macro_status_var.set("Starting… window will minimize. Press F2 to stop.")
        self.root.update_idletasks()
        self.root.iconify()
        self.root.after(300, self._begin_recording)

    def _begin_recording(self) -> None:
        if self.root.state() != "iconic":
            self.root.iconify()
        self._macro_recorder.start()
        name = self.macro_name_var.get().strip()
        self.macro_status_var.set(f'Recording "{name}"… press F2 to stop.')

    def stop_recording(self) -> None:
        if not self._macro_recorder.is_recording:
            return
        self._recorded_events = self._macro_recorder.stop()
        self._finish_recording()

    def _restore_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _on_macro_record_stopped(self) -> None:
        self.root.after(0, self._handle_hotkey_stop)

    def _handle_hotkey_stop(self) -> None:
        if not self._macro_recorder.is_recording:
            self._recorded_events = self._macro_recorder.events
            self._finish_recording()

    def _finish_recording(self) -> None:
        self._restore_window()
        count = len(self._recorded_events)
        name = self.macro_name_var.get().strip()
        self._set_recording_ui(False)
        if count:
            self.save_macro_btn.config(state="normal")
            self.macro_status_var.set(
                f'Recorded {count} steps for "{name}". Save or play them.'
            )
        else:
            self.macro_status_var.set("No steps recorded.")

    def save_macro(self) -> None:
        if not self._recorded_events:
            messagebox.showinfo("Nothing to save", "Record a macro first.")
            return
        name = self.macro_name_var.get().strip()
        if not name:
            messagebox.showwarning("Name required", "Enter a macro name before saving.")
            return
        try:
            path = recorder.save_macro(name, self._recorded_events)
        except ValueError as exc:
            messagebox.showerror("Invalid name", str(exc))
            return
        self._refresh_macro_list()
        self.macro_list_var.set(path.stem)
        self.macro_status_var.set(f'Saved "{path.stem}" ({len(self._recorded_events)} events).')

    def _play_loop(self, events: list[dict]) -> None:
        try:
            recorder.play_macro(events, self._play_stop)
        finally:
            self.root.after(0, self._on_play_finished)

    def _on_play_finished(self) -> None:
        self._play_thread = None
        self.play_macro_btn.config(state="normal")
        self.stop_play_btn.config(state="disabled")
        if self._play_stop.is_set():
            self.macro_status_var.set("Playback stopped.")
        else:
            self.macro_status_var.set("Playback finished.")

    def play_macro(self) -> None:
        if self._play_thread and self._play_thread.is_alive():
            return
        if self._macro_recorder.is_recording:
            messagebox.showwarning("Busy", "Stop recording before playing a macro.")
            return
        if self._click_thread and self._click_thread.is_alive():
            messagebox.showwarning("Busy", "Stop the clicker before playing a macro.")
            return

        selected = self.macro_list_var.get()
        if selected:
            try:
                macro = recorder.load_macro(selected)
                events = macro["events"]
            except FileNotFoundError:
                messagebox.showerror("Not found", f'Macro "{selected}" was not found.')
                self._refresh_macro_list()
                return
        elif self._recorded_events:
            events = self._recorded_events
        else:
            messagebox.showinfo("No macro", "Select a saved macro or record one first.")
            return

        self._play_stop.clear()
        self._play_thread = threading.Thread(
            target=self._play_loop, args=(events,), daemon=True
        )
        self._play_thread.start()
        self.play_macro_btn.config(state="disabled")
        self.stop_play_btn.config(state="normal")
        self.macro_status_var.set("Playing macro…")

    def open_macro_editor(self) -> None:
        macro_name = self.macro_name_var.get().strip() or "my_macro"
        steps = list(self._recorded_events)

        selected = self.macro_list_var.get()
        if selected:
            try:
                macro = recorder.load_macro(selected)
                macro_name = macro.get("name", selected)
                steps = macro.get("events", [])
            except FileNotFoundError:
                messagebox.showerror("Not found", f'Macro "{selected}" was not found.')
                self._refresh_macro_list()
                return

        MacroEditor(
            self.root,
            macro_name=macro_name,
            steps=steps,
            on_saved=self._on_macro_edited,
        )

    def _on_macro_edited(self, name: str, steps: list[dict]) -> None:
        self.macro_name_var.set(name)
        self._recorded_events = steps
        self._refresh_macro_list()
        self.macro_list_var.set(name)
        self.save_macro_btn.config(state="normal")
        self.macro_status_var.set(f'Loaded editor changes for "{name}" ({len(steps)} steps).')

    def stop_playing(self) -> None:
        self._play_stop.set()
        if self._play_thread:
            self._play_thread.join(timeout=2)

    def _on_close(self) -> None:
        self.stop_clicking()
        if self._macro_recorder.is_recording:
            self._macro_recorder.stop()
        self.stop_playing()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    ttk.Style().theme_use("vista")
    AutoclickerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
