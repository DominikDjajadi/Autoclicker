import copy
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

import pyautogui

import recorder


class StepDialog(tk.Toplevel):
    STEP_LABELS = {
        "wait": "Wait",
        "click": "Click position",
        "drag": "Drag",
        "click_image": "Click image",
        "click_all": "Click all matching",
        "key_down": "Key down",
        "key_up": "Key up",
    }
    STEP_TYPES = tuple(STEP_LABELS.keys())

    def __init__(
        self,
        parent: tk.Misc,
        step: dict | None = None,
        title: str = "Add step",
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.geometry("460x400")
        self.minsize(400, 340)
        self.resizable(True, True)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.transient(parent)
        self.grab_set()

        self.result: dict | None = None
        self._field_vars: dict[str, tk.Variable] = {}
        self._fields_frame: ttk.Frame | None = None

        body = ttk.Frame(self, padding=12)
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)

        ttk.Label(body, text="Step type").grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.type_var = tk.StringVar(value="wait")
        type_combo = ttk.Combobox(
            body,
            textvariable=self.type_var,
            values=[self.STEP_LABELS[t] for t in self.STEP_TYPES],
            state="readonly",
            width=28,
        )
        type_combo.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        type_combo.bind("<<ComboboxSelected>>", self._on_type_changed)

        self._fields_frame = ttk.Frame(body)
        self._fields_frame.grid(row=2, column=0, sticky="nsew")
        self._fields_frame.columnconfigure(1, weight=1)

        buttons = ttk.Frame(body)
        buttons.grid(row=3, column=0, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(buttons, text="OK", command=self._on_ok).grid(row=0, column=1)

        if step:
            label = self.STEP_LABELS.get(step["type"])
            if label:
                self.type_var.set(label)
        self._build_fields()
        if step:
            self._populate_fields(step)

        self.wait_window(self)

    def _label_to_type(self) -> str:
        label = self.type_var.get()
        for step_type, step_label in self.STEP_LABELS.items():
            if step_label == label:
                return step_type
        return "wait"

    def _on_type_changed(self, _event=None) -> None:
        self._build_fields()

    def _clear_fields(self) -> None:
        for child in self._fields_frame.winfo_children():
            child.destroy()
        self._field_vars = {}

    def _add_field(self, row: int, label: str, name: str, default: str = "") -> ttk.Entry:
        ttk.Label(self._fields_frame, text=label).grid(row=row, column=0, sticky="w", pady=2)
        var = tk.StringVar(value=default)
        entry = ttk.Entry(self._fields_frame, textvariable=var, width=32)
        entry.grid(row=row, column=1, sticky="ew", pady=2, padx=(8, 0))
        self._field_vars[name] = var
        return entry

    def _build_fields(self) -> None:
        self._clear_fields()
        step_type = self._label_to_type()

        if step_type == "wait":
            self._add_field(0, "Seconds", "seconds", "1.0")
        elif step_type == "click":
            self._add_field(0, "X", "x", "0")
            self._add_field(1, "Y", "y", "0")
            ttk.Label(self._fields_frame, text="Button").grid(row=2, column=0, sticky="w", pady=2)
            self._field_vars["button"] = tk.StringVar(value="left")
            ttk.Combobox(
                self._fields_frame,
                textvariable=self._field_vars["button"],
                values=["left", "right", "middle"],
                state="readonly",
                width=30,
            ).grid(row=2, column=1, sticky="ew", pady=2, padx=(8, 0))
            ttk.Button(
                self._fields_frame,
                text="Capture in 3s",
                command=self._capture_position,
            ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))
            self._add_field(5, "Wait before (seconds)", "delay", "0")
        elif step_type == "drag":
            self._add_field(0, "Start X", "start_x", "0")
            self._add_field(1, "Start Y", "start_y", "0")
            self._add_field(2, "End X", "end_x", "0")
            self._add_field(3, "End Y", "end_y", "0")
            self._add_field(4, "Duration (seconds)", "duration", "0.5")
            ttk.Label(self._fields_frame, text="Button").grid(row=5, column=0, sticky="w", pady=2)
            self._field_vars["button"] = tk.StringVar(value="left")
            ttk.Combobox(
                self._fields_frame,
                textvariable=self._field_vars["button"],
                values=["left", "right", "middle"],
                state="readonly",
                width=30,
            ).grid(row=5, column=1, sticky="ew", pady=2, padx=(8, 0))
            capture_row = ttk.Frame(self._fields_frame)
            capture_row.grid(row=6, column=0, columnspan=2, sticky="w", pady=(6, 0))
            ttk.Button(
                capture_row,
                text="Capture start in 3s",
                command=lambda: self._capture_position("start"),
            ).grid(row=0, column=0, padx=(0, 6))
            ttk.Button(
                capture_row,
                text="Capture end in 3s",
                command=lambda: self._capture_position("end"),
            ).grid(row=0, column=1)
            self._add_field(7, "Wait before (seconds)", "delay", "0")
        elif step_type in ("click_image",):
            self._add_field(0, "Image path", "image", "")
            ttk.Button(
                self._fields_frame,
                text="Browse…",
                command=self._browse_image,
            ).grid(row=1, column=0, sticky="w", pady=(4, 0))
            self._add_field(2, "Confidence (optional)", "confidence", "")
            self._add_field(3, "Wait before (seconds)", "delay", "0")
        elif step_type == "click_all":
            self._add_field(0, "Image path", "image", "")
            ttk.Button(
                self._fields_frame,
                text="Browse…",
                command=self._browse_image,
            ).grid(row=1, column=0, sticky="w", pady=(4, 0))
            self._add_field(2, "Confidence (optional)", "confidence", "")
            self._add_field(3, "Time between clicks (seconds)", "interval", "0.5")
            self._add_field(4, "Dedupe overlap (0-1, 0=off)", "dedupe_overlap", "0.5")
            self._add_field(5, "Wait before (seconds)", "delay", "0")
        elif step_type in ("key_down", "key_up"):
            self._add_field(0, "Key", "key", "a")
            self._add_field(1, "Wait before (seconds)", "delay", "0")

    def _populate_fields(self, step: dict) -> None:
        for name, var in self._field_vars.items():
            if name in step:
                var.set(str(step[name]))

    @staticmethod
    def _apply_wait_before(step: dict, values: dict) -> dict:
        delay = values.get("delay", "").strip()
        if delay and float(delay) >= recorder.MIN_STEP_DELAY:
            step["delay"] = float(delay)
        return step

    def _capture_position(self, target: str = "click") -> None:
        self._capture_title = self.title()
        self._capture_target = target
        self._capture_remaining = 3
        self._tick_capture()

    def _tick_capture(self) -> None:
        if self._capture_remaining > 0:
            label = "position"
            if self._capture_target == "start":
                label = "start"
            elif self._capture_target == "end":
                label = "end"
            self.title(f"Capture {label} in {self._capture_remaining}…")
            self._capture_remaining -= 1
            self.after(1000, self._tick_capture)
            return
        x, y = pyautogui.position()
        if self._capture_target == "start":
            if "start_x" in self._field_vars:
                self._field_vars["start_x"].set(str(x))
            if "start_y" in self._field_vars:
                self._field_vars["start_y"].set(str(y))
        elif self._capture_target == "end":
            if "end_x" in self._field_vars:
                self._field_vars["end_x"].set(str(x))
            if "end_y" in self._field_vars:
                self._field_vars["end_y"].set(str(y))
        else:
            if "x" in self._field_vars:
                self._field_vars["x"].set(str(x))
            if "y" in self._field_vars:
                self._field_vars["y"].set(str(y))
        self.title(getattr(self, "_capture_title", "Add step"))

    def _browse_image(self) -> None:
        IMAGES_DIR = recorder.IMAGES_DIR
        IMAGES_DIR.mkdir(exist_ok=True)
        path = filedialog.askopenfilename(
            parent=self,
            title="Select image",
            initialdir=IMAGES_DIR,
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif"), ("All files", "*.*")],
        )
        if path:
            self._field_vars["image"].set(recorder.relative_image_path(path))

    def _on_ok(self) -> None:
        try:
            self.result = self._build_step()
        except ValueError as exc:
            messagebox.showerror("Invalid step", str(exc), parent=self)
            return
        self.destroy()

    def _build_step(self) -> dict:
        step_type = self._label_to_type()
        values = {name: var.get().strip() for name, var in self._field_vars.items()}

        if step_type == "wait":
            seconds = float(values["seconds"])
            if seconds < 0:
                raise ValueError("Seconds must be 0 or greater.")
            return {"type": "wait", "seconds": seconds}

        if step_type == "click":
            step = {
                "type": "click",
                "x": int(values["x"]),
                "y": int(values["y"]),
                "button": values.get("button") or "left",
            }
            return self._apply_wait_before(step, values)

        if step_type == "drag":
            duration = float(values.get("duration") or 0.5)
            if duration < 0:
                raise ValueError("Duration must be 0 or greater.")
            step = {
                "type": "drag",
                "start_x": int(values["start_x"]),
                "start_y": int(values["start_y"]),
                "end_x": int(values["end_x"]),
                "end_y": int(values["end_y"]),
                "duration": duration,
                "button": values.get("button") or "left",
            }
            return self._apply_wait_before(step, values)

        if step_type == "click_image":
            if not values["image"]:
                raise ValueError("Choose an image path.")
            step = {"type": "click_image", "image": values["image"]}
            if values.get("confidence"):
                step["confidence"] = float(values["confidence"])
            return self._apply_wait_before(step, values)

        if step_type == "click_all":
            if not values["image"]:
                raise ValueError("Choose an image path.")
            interval = float(values.get("interval") or 0.5)
            if interval < 0:
                raise ValueError("Time between clicks must be 0 or greater.")
            step = {"type": "click_all", "image": values["image"], "interval": interval}
            if values.get("confidence"):
                step["confidence"] = float(values["confidence"])
            dedupe = values.get("dedupe_overlap", "").strip()
            if dedupe:
                step["dedupe_overlap"] = float(dedupe)
            return self._apply_wait_before(step, values)

        if step_type in ("key_down", "key_up"):
            if not values["key"]:
                raise ValueError("Enter a key name.")
            step = {"type": step_type, "key": values["key"]}
            return self._apply_wait_before(step, values)

        raise ValueError(f"Unsupported step type: {step_type}")


class LoopDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        loop_step: dict | None = None,
        title: str = "Add loop",
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.geometry("680x560")
        self.minsize(560, 480)
        self.resizable(True, True)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.transient(parent)
        self.grab_set()

        self.result: dict | None = None
        self._body_steps = copy.deepcopy(loop_step.get("steps", [])) if loop_step else []
        self._condition_vars: dict[str, tk.Variable] = {}
        self._condition_fields: ttk.Frame | None = None

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)

        ttk.Label(body, text="Loop condition", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.condition_var = tk.StringVar(
            value=recorder.CONDITION_LABELS.get(
                loop_step.get("condition", {}).get("type", "count") if loop_step else "count",
                recorder.CONDITION_LABELS["count"],
            )
        )
        ttk.Combobox(
            body,
            textvariable=self.condition_var,
            values=[recorder.CONDITION_LABELS[t] for t in recorder.CONDITION_TYPES],
            state="readonly",
            width=40,
        ).pack(anchor="w", pady=(4, 8))
        self.condition_var.trace_add("write", lambda *_: self._build_condition_fields())

        self._condition_fields = ttk.Frame(body)
        self._condition_fields.pack(fill="x", pady=(0, 8))
        self._condition_fields.columnconfigure(1, weight=1)
        self._build_condition_fields()

        interval_default = str(loop_step.get("interval", 0)) if loop_step else "0"
        interval_row = ttk.Frame(body)
        interval_row.pack(fill="x", pady=(0, 8))
        ttk.Label(interval_row, text="Pause between iterations (seconds)").pack(side="left")
        self.interval_var = tk.StringVar(value=interval_default)
        ttk.Entry(interval_row, textvariable=self.interval_var, width=8).pack(side="left", padx=(8, 0))

        ttk.Label(body, text="Steps inside loop", font=("Segoe UI", 9, "bold")).pack(anchor="w")

        list_frame = ttk.Frame(body)
        list_frame.pack(fill="both", expand=True, pady=(4, 8))

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        self.body_list = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            activestyle="none",
        )
        self.body_list.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.body_list.yview)

        body_controls = ttk.Frame(body)
        body_controls.pack(fill="x")
        ttk.Button(body_controls, text="Add step", command=self._add_body_step).pack(side="left")
        ttk.Button(body_controls, text="Add loop", command=self._add_body_loop).pack(side="left", padx=(6, 0))
        ttk.Button(body_controls, text="Edit", command=self._edit_body_step).pack(side="left", padx=(6, 0))
        ttk.Button(body_controls, text="Remove", command=self._remove_body_step).pack(side="left", padx=(6, 0))
        ttk.Button(body_controls, text="Up", command=lambda: self._move_body_step(-1)).pack(side="left", padx=(6, 0))
        ttk.Button(body_controls, text="Down", command=lambda: self._move_body_step(1)).pack(side="left", padx=(6, 0))

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="OK", command=self._on_ok).pack(side="right", padx=(0, 6))

        if loop_step:
            self._populate_condition(loop_step.get("condition", {}))

        self._refresh_body_list()
        self.wait_window(self)

    def _label_to_condition_type(self) -> str:
        label = self.condition_var.get()
        for ctype, clabel in recorder.CONDITION_LABELS.items():
            if clabel == label:
                return ctype
        return "count"

    def _clear_condition_fields(self) -> None:
        for child in self._condition_fields.winfo_children():
            child.destroy()
        self._condition_vars = {}

    def _add_condition_field(self, row: int, label: str, name: str, default: str = "") -> None:
        ttk.Label(self._condition_fields, text=label).grid(row=row, column=0, sticky="w", pady=2)
        var = tk.StringVar(value=default)
        ttk.Entry(self._condition_fields, textvariable=var, width=34).grid(
            row=row, column=1, sticky="ew", pady=2, padx=(8, 0)
        )
        self._condition_vars[name] = var

    def _build_condition_fields(self) -> None:
        self._clear_condition_fields()
        ctype = self._label_to_condition_type()
        if ctype == "count":
            self._add_condition_field(0, "Repeat count", "times", "5")
        elif ctype in ("image_visible", "image_absent"):
            self._add_condition_field(0, "Image path", "image", "")
            ttk.Button(
                self._condition_fields,
                text="Browse…",
                command=self._browse_condition_image,
            ).grid(row=1, column=0, sticky="w", pady=(4, 0))
            self._add_condition_field(2, "Confidence (optional)", "confidence", "")
        elif ctype == "until_key":
            self._add_condition_field(0, "Key", "key", "f3")
            ttk.Label(
                self._condition_fields,
                text="Loop runs until this key is pressed once.",
                foreground="gray",
            ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

    def _populate_condition(self, condition: dict) -> None:
        label = recorder.CONDITION_LABELS.get(condition.get("type", "count"))
        if label:
            self.condition_var.set(label)
        self._build_condition_fields()
        for name, var in self._condition_vars.items():
            if name in condition:
                var.set(str(condition[name]))

    def _browse_condition_image(self) -> None:
        recorder.IMAGES_DIR.mkdir(exist_ok=True)
        path = filedialog.askopenfilename(
            parent=self,
            title="Select image",
            initialdir=recorder.IMAGES_DIR,
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif"), ("All files", "*.*")],
        )
        if path and "image" in self._condition_vars:
            self._condition_vars["image"].set(recorder.relative_image_path(path))

    def _refresh_body_list(self) -> None:
        self.body_list.delete(0, tk.END)
        for line in recorder.flatten_steps_for_display(self._body_steps):
            self.body_list.insert(tk.END, line)

    def _selected_body_index(self) -> int | None:
        selection = self.body_list.curselection()
        if not selection:
            return None
        return int(selection[0])

    def _resolve_body_index(self, list_index: int) -> int | None:
        current = 0
        for index, step in enumerate(self._body_steps):
            if current == list_index:
                return index
            current += 1
            if step.get("type") == "loop":
                nested_count = len(recorder.flatten_steps_for_display(step.get("steps", [])))
                if list_index <= current + nested_count - 1:
                    return None
                current += nested_count
        return None

    def _add_body_step(self) -> None:
        dialog = StepDialog(self, title="Add step")
        if dialog.result:
            self._body_steps.append(dialog.result)
            self._refresh_body_list()

    def _add_body_loop(self) -> None:
        dialog = LoopDialog(self, title="Add nested loop")
        if dialog.result:
            self._body_steps.append(dialog.result)
            self._refresh_body_list()

    def _edit_body_step(self) -> None:
        index = self._selected_body_index()
        if index is None:
            messagebox.showinfo("Select a step", "Choose a step to edit.", parent=self)
            return
        step_index = self._resolve_body_index(index)
        if step_index is None:
            messagebox.showinfo(
                "Nested step",
                "Edit nested steps by selecting the loop step itself.",
                parent=self,
            )
            return
        step = self._body_steps[step_index]
        if step.get("type") == "loop":
            dialog = LoopDialog(self, loop_step=step, title="Edit loop")
            if dialog.result:
                self._body_steps[step_index] = dialog.result
        else:
            dialog = StepDialog(self, step=step, title="Edit step")
            if dialog.result:
                self._body_steps[step_index] = dialog.result
        self._refresh_body_list()

    def _remove_body_step(self) -> None:
        index = self._selected_body_index()
        if index is None:
            return
        step_index = self._resolve_body_index(index)
        if step_index is None:
            return
        del self._body_steps[step_index]
        self._refresh_body_list()

    def _move_body_step(self, direction: int) -> None:
        index = self._selected_body_index()
        if index is None:
            return
        step_index = self._resolve_body_index(index)
        if step_index is None:
            return
        new_index = step_index + direction
        if new_index < 0 or new_index >= len(self._body_steps):
            return
        self._body_steps[step_index], self._body_steps[new_index] = (
            self._body_steps[new_index],
            self._body_steps[step_index],
        )
        self._refresh_body_list()
        self.body_list.selection_set(index + direction)

    def _build_condition(self) -> dict:
        ctype = self._label_to_condition_type()
        values = {name: var.get().strip() for name, var in self._condition_vars.items()}

        if ctype == "count":
            times = int(values.get("times") or 0)
            if times <= 0:
                raise ValueError("Repeat count must be greater than 0.")
            return {"type": "count", "times": times}

        if ctype in ("image_visible", "image_absent"):
            if not values.get("image"):
                raise ValueError("Choose an image path.")
            condition = {"type": ctype, "image": values["image"]}
            if values.get("confidence"):
                condition["confidence"] = float(values["confidence"])
            return condition

        if ctype == "until_key":
            if not values.get("key"):
                raise ValueError("Enter a key name.")
            return {"type": "until_key", "key": values["key"]}

        raise ValueError(f"Unsupported condition: {ctype}")

    def _on_ok(self) -> None:
        try:
            condition = self._build_condition()
            interval = float(self.interval_var.get() or 0)
            if interval < 0:
                raise ValueError("Interval must be 0 or greater.")
            if not self._body_steps:
                raise ValueError("Add at least one step inside the loop.")
            self.result = {
                "type": "loop",
                "condition": condition,
                "interval": interval,
                "steps": copy.deepcopy(self._body_steps),
            }
        except ValueError as exc:
            messagebox.showerror("Invalid loop", str(exc), parent=self)
            return
        self.destroy()


class MacroEditor(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        macro_name: str = "my_macro",
        steps: list[dict] | None = None,
        on_saved: Callable[[str, list[dict]], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("Macro Editor")
        self.geometry("720x580")
        self.minsize(560, 440)
        self.resizable(True, True)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._on_saved = on_saved
        self._steps = recorder.expand_step_delays(copy.deepcopy(steps or []))

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)

        top = ttk.Frame(body)
        top.pack(fill="x", pady=(0, 8))
        ttk.Label(top, text="Name").pack(side="left")
        self.name_var = tk.StringVar(value=macro_name)
        name_entry = ttk.Entry(top, textvariable=self.name_var, width=30)
        name_entry.pack(side="left", fill="x", expand=True, padx=(8, 0))

        list_frame = ttk.Frame(body)
        list_frame.pack(fill="both", expand=True)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        self.steps_list = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            activestyle="none",
        )
        self.steps_list.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.steps_list.yview)

        controls = ttk.Frame(body)
        controls.pack(fill="x", pady=(8, 0))

        ttk.Button(controls, text="Add", command=self._add_step).pack(side="left")
        ttk.Button(controls, text="Add loop", command=self._add_loop).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Edit", command=self._edit_step).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Remove", command=self._remove_step).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Up", command=lambda: self._move_step(-1)).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Down", command=lambda: self._move_step(1)).pack(side="left", padx=(6, 0))

        bottom = ttk.Frame(body)
        bottom.pack(fill="x", pady=(12, 0))
        ttk.Button(bottom, text="Load saved…", command=self._load_saved).pack(side="left")
        ttk.Button(bottom, text="Save", command=self._save).pack(side="right")
        ttk.Button(bottom, text="Close", command=self.destroy).pack(side="right", padx=(0, 6))

        self._refresh_list()

    def get_steps(self) -> list[dict]:
        return copy.deepcopy(self._steps)

    def _refresh_list(self) -> None:
        self.steps_list.delete(0, tk.END)
        for line in recorder.flatten_steps_for_display(self._steps):
            self.steps_list.insert(tk.END, line)

    def _resolve_step_index(self, list_index: int) -> int | None:
        current = 0
        for index, step in enumerate(self._steps):
            if current == list_index:
                return index
            current += 1
            if step.get("type") == "loop":
                nested_count = len(recorder.flatten_steps_for_display(step.get("steps", [])))
                if list_index <= current + nested_count - 1:
                    return None
                current += nested_count
        return None

    def _selected_index(self) -> int | None:
        selection = self.steps_list.curselection()
        if not selection:
            return None
        return int(selection[0])

    def _selected_step_index(self) -> int | None:
        list_index = self._selected_index()
        if list_index is None:
            return None
        return self._resolve_step_index(list_index)

    def _add_step(self) -> None:
        dialog = StepDialog(self, title="Add step")
        if dialog.result:
            self._steps.append(dialog.result)
            self._refresh_list()
            self.steps_list.selection_set(tk.END)

    def _add_loop(self) -> None:
        dialog = LoopDialog(self, title="Add loop")
        if dialog.result:
            self._steps.append(dialog.result)
            self._refresh_list()
            self.steps_list.selection_set(tk.END)

    def _edit_step(self) -> None:
        step_index = self._selected_step_index()
        if step_index is None:
            list_index = self._selected_index()
            if list_index is None:
                messagebox.showinfo("Select a step", "Choose a step to edit.", parent=self)
            else:
                messagebox.showinfo(
                    "Nested step",
                    "Edit nested steps by selecting the loop step itself.",
                    parent=self,
                )
            return
        step = self._steps[step_index]
        if step.get("type") == "loop":
            dialog = LoopDialog(self, loop_step=step, title="Edit loop")
            if dialog.result:
                self._steps[step_index] = dialog.result
        else:
            dialog = StepDialog(self, step=step, title="Edit step")
            if dialog.result:
                self._steps[step_index] = dialog.result
        self._refresh_list()
        if self._selected_index() is not None:
            self.steps_list.selection_set(self._selected_index())

    def _remove_step(self) -> None:
        step_index = self._selected_step_index()
        if step_index is None:
            return
        del self._steps[step_index]
        self._refresh_list()

    def _move_step(self, direction: int) -> None:
        step_index = self._selected_step_index()
        if step_index is None:
            return
        new_index = step_index + direction
        if new_index < 0 or new_index >= len(self._steps):
            return
        self._steps[step_index], self._steps[new_index] = self._steps[new_index], self._steps[step_index]
        self._refresh_list()
        list_index = self._selected_index()
        if list_index is not None:
            self.steps_list.selection_set(list_index + direction)

    def _load_saved(self) -> None:
        names = recorder.list_macros()
        if not names:
            messagebox.showinfo("No macros", "No saved macros to load.", parent=self)
            return
        picker = tk.Toplevel(self)
        picker.title("Load macro")
        picker.geometry("360x120")
        picker.minsize(320, 100)
        picker.resizable(True, True)
        picker.transient(self)
        picker.grab_set()
        picker.columnconfigure(1, weight=1)
        ttk.Label(picker, text="Macro", padding=8).grid(row=0, column=0, sticky="w")
        choice = tk.StringVar(value=names[0])
        ttk.Combobox(picker, textvariable=choice, values=names, state="readonly", width=28).grid(
            row=0, column=1, padx=8, pady=8, sticky="ew"
        )

        def load_selected() -> None:
            try:
                macro = recorder.load_macro(choice.get())
            except FileNotFoundError as exc:
                messagebox.showerror("Not found", str(exc), parent=picker)
                return
            self.name_var.set(macro.get("name", choice.get()))
            self._steps = recorder.expand_step_delays(macro.get("events", []))
            self._refresh_list()
            picker.destroy()

        ttk.Button(picker, text="Load", command=load_selected).grid(row=1, column=1, sticky="e", padx=8, pady=(0, 8))

    def _save(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Name required", "Enter a macro name.", parent=self)
            return
        if not self._steps:
            messagebox.showwarning("Empty macro", "Add at least one step.", parent=self)
            return
        try:
            path = recorder.save_macro(name, self._steps)
        except ValueError as exc:
            messagebox.showerror("Invalid name", str(exc), parent=self)
            return
        if self._on_saved:
            self._on_saved(path.stem, self.get_steps())
        messagebox.showinfo("Saved", f'Macro saved as "{path.stem}".', parent=self)
