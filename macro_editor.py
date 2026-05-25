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
        "click_image": "Click image",
        "while_image": "While image exists",
        "key_down": "Key down",
        "key_up": "Key up",
    }

    def __init__(
        self,
        parent: tk.Misc,
        step: dict | None = None,
        title: str = "Add step",
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.result: dict | None = None
        self._field_vars: dict[str, tk.Variable] = {}
        self._fields_frame: ttk.Frame | None = None

        body = ttk.Frame(self, padding=12)
        body.grid(row=0, column=0, sticky="nsew")

        ttk.Label(body, text="Step type").grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.type_var = tk.StringVar(value="wait")
        type_combo = ttk.Combobox(
            body,
            textvariable=self.type_var,
            values=[self.STEP_LABELS[t] for t in recorder.STEP_TYPES],
            state="readonly",
            width=28,
        )
        type_combo.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        type_combo.bind("<<ComboboxSelected>>", self._on_type_changed)

        self._fields_frame = ttk.Frame(body)
        self._fields_frame.grid(row=2, column=0, sticky="ew")

        buttons = ttk.Frame(body)
        buttons.grid(row=3, column=0, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(buttons, text="OK", command=self._on_ok).grid(row=0, column=1)

        if step:
            label = self.STEP_LABELS[step["type"]]
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
            ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))
        elif step_type in ("click_image", "while_image"):
            self._add_field(0, "Image path", "image", "")
            ttk.Button(
                self._fields_frame,
                text="Browse…",
                command=self._browse_image,
            ).grid(row=1, column=0, sticky="w", pady=(4, 0))
            self._add_field(2, "Confidence (optional)", "confidence", "")
            if step_type == "while_image":
                self._add_field(3, "Interval (seconds)", "interval", "0.5")
                self._add_field(4, "Max iterations (0 = unlimited)", "max_iterations", "0")
        elif step_type in ("key_down", "key_up"):
            self._add_field(0, "Key", "key", "a")
            self._add_field(1, "Delay before (seconds)", "delay", "0")

    def _populate_fields(self, step: dict) -> None:
        for name, var in self._field_vars.items():
            if name in step:
                var.set(str(step[name]))

    def _capture_position(self) -> None:
        self._capture_title = self.title()
        self._capture_remaining = 3
        self._tick_capture()

    def _tick_capture(self) -> None:
        if self._capture_remaining > 0:
            self.title(f"Capture position in {self._capture_remaining}…")
            self._capture_remaining -= 1
            self.after(1000, self._tick_capture)
            return
        x, y = pyautogui.position()
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
            return {
                "type": "click",
                "x": int(values["x"]),
                "y": int(values["y"]),
                "button": values.get("button") or "left",
            }

        if step_type == "click_image":
            if not values["image"]:
                raise ValueError("Choose an image path.")
            step = {"type": "click_image", "image": values["image"]}
            if values.get("confidence"):
                step["confidence"] = float(values["confidence"])
            return step

        if step_type == "while_image":
            if not values["image"]:
                raise ValueError("Choose an image path.")
            step = {
                "type": "while_image",
                "image": values["image"],
                "interval": float(values.get("interval") or 0.5),
                "max_iterations": int(values.get("max_iterations") or 0),
            }
            if values.get("confidence"):
                step["confidence"] = float(values["confidence"])
            return step

        if step_type in ("key_down", "key_up"):
            if not values["key"]:
                raise ValueError("Enter a key name.")
            step = {"type": step_type, "key": values["key"]}
            delay = values.get("delay")
            if delay:
                step["delay"] = float(delay)
            return step

        raise ValueError(f"Unsupported step type: {step_type}")


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
        self.geometry("520x420")
        self.minsize(480, 360)

        self._on_saved = on_saved
        self._steps = copy.deepcopy(steps or [])

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)

        top = ttk.Frame(body)
        top.pack(fill="x", pady=(0, 8))
        ttk.Label(top, text="Name").pack(side="left")
        self.name_var = tk.StringVar(value=macro_name)
        ttk.Entry(top, textvariable=self.name_var, width=30).pack(side="left", padx=(8, 0))

        list_frame = ttk.Frame(body)
        list_frame.pack(fill="both", expand=True)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        self.steps_list = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            height=12,
            activestyle="none",
        )
        self.steps_list.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.steps_list.yview)

        controls = ttk.Frame(body)
        controls.pack(fill="x", pady=(8, 0))

        ttk.Button(controls, text="Add", command=self._add_step).pack(side="left")
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
        for index, step in enumerate(self._steps, start=1):
            self.steps_list.insert(tk.END, f"{index}. {recorder.format_step(step)}")

    def _selected_index(self) -> int | None:
        selection = self.steps_list.curselection()
        if not selection:
            return None
        return int(selection[0])

    def _add_step(self) -> None:
        dialog = StepDialog(self, title="Add step")
        if dialog.result:
            self._steps.append(dialog.result)
            self._refresh_list()
            self.steps_list.selection_set(tk.END)

    def _edit_step(self) -> None:
        index = self._selected_index()
        if index is None:
            messagebox.showinfo("Select a step", "Choose a step to edit.", parent=self)
            return
        dialog = StepDialog(self, step=self._steps[index], title="Edit step")
        if dialog.result:
            self._steps[index] = dialog.result
            self._refresh_list()
            self.steps_list.selection_set(index)

    def _remove_step(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        del self._steps[index]
        self._refresh_list()

    def _move_step(self, direction: int) -> None:
        index = self._selected_index()
        if index is None:
            return
        new_index = index + direction
        if new_index < 0 or new_index >= len(self._steps):
            return
        self._steps[index], self._steps[new_index] = self._steps[new_index], self._steps[index]
        self._refresh_list()
        self.steps_list.selection_set(new_index)

    def _load_saved(self) -> None:
        names = recorder.list_macros()
        if not names:
            messagebox.showinfo("No macros", "No saved macros to load.", parent=self)
            return
        picker = tk.Toplevel(self)
        picker.title("Load macro")
        picker.transient(self)
        picker.grab_set()
        ttk.Label(picker, text="Macro", padding=8).grid(row=0, column=0, sticky="w")
        choice = tk.StringVar(value=names[0])
        ttk.Combobox(picker, textvariable=choice, values=names, state="readonly", width=28).grid(
            row=0, column=1, padx=8, pady=8
        )

        def load_selected() -> None:
            try:
                macro = recorder.load_macro(choice.get())
            except FileNotFoundError as exc:
                messagebox.showerror("Not found", str(exc), parent=picker)
                return
            self.name_var.set(macro.get("name", choice.get()))
            self._steps = macro.get("events", [])
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
