import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter, sleep
from typing import Callable

import pyautogui
from pynput import keyboard, mouse

MACROS_DIR = Path(__file__).parent / "macros"
IMAGES_DIR = Path(__file__).parent / "images"
STOP_RECORD_KEY = keyboard.Key.f2

STEP_TYPES = (
    "wait",
    "click",
    "click_image",
    "while_image",
    "key_down",
    "key_up",
)


def key_to_str(key: keyboard.Key | keyboard.KeyCode) -> str:
    if isinstance(key, keyboard.KeyCode):
        if key.char is not None:
            return key.char
        if key.vk is not None:
            return f"vk_{key.vk}"
        return "unknown"
    return key.name


def str_to_key(key_str: str) -> keyboard.Key | keyboard.KeyCode:
    try:
        return keyboard.Key[key_str]
    except KeyError:
        pass
    if len(key_str) == 1:
        return keyboard.KeyCode.from_char(key_str)
    if key_str.startswith("vk_"):
        return keyboard.KeyCode.from_vk(int(key_str[3:]))
    raise ValueError(f"Unknown key: {key_str}")


def button_to_str(button: mouse.Button) -> str:
    if button == mouse.Button.left:
        return "left"
    if button == mouse.Button.right:
        return "right"
    if button == mouse.Button.middle:
        return "middle"
    return str(button)


def _sanitize_name(name: str) -> str:
    safe = re.sub(r"[^\w\- ]", "", name.strip())
    safe = re.sub(r"\s+", "_", safe)
    if not safe:
        raise ValueError("Macro name cannot be empty")
    return safe


def resolve_image_path(image: str) -> Path:
    path = Path(image)
    if path.is_file():
        return path.resolve()
    for base in (IMAGES_DIR, Path(__file__).parent):
        candidate = base / image
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(f"Image not found: {image}")


def relative_image_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    project_root = Path(__file__).parent.resolve()
    try:
        return str(resolved.relative_to(project_root))
    except ValueError:
        return str(resolved)


def format_step(step: dict) -> str:
    step_type = step["type"]
    if step_type == "wait":
        return f"Wait {step['seconds']}s"
    if step_type == "click":
        button = step.get("button", "left")
        return f"Click {button} at ({step['x']}, {step['y']})"
    if step_type == "click_image":
        return f"Click image: {Path(step['image']).name}"
    if step_type == "while_image":
        interval = step.get("interval", 0.5)
        return f"While image exists, click every {interval}s: {Path(step['image']).name}"
    if step_type == "key_down":
        delay = step.get("delay", 0)
        suffix = f" (after {delay:.2f}s)" if delay else ""
        return f"Key down: {step['key']}{suffix}"
    if step_type == "key_up":
        delay = step.get("delay", 0)
        suffix = f" (after {delay:.2f}s)" if delay else ""
        return f"Key up: {step['key']}{suffix}"
    return str(step)


def _interruptible_sleep(seconds: float, stop_event: threading.Event | None) -> bool:
    if seconds <= 0:
        return False
    if stop_event is None:
        sleep(seconds)
        return False
    return stop_event.wait(seconds)


def _locate_image(image_path: Path, step: dict):
    kwargs = {}
    if "confidence" in step:
        kwargs["confidence"] = float(step["confidence"])
    return pyautogui.locateOnScreen(str(image_path), **kwargs)


def _execute_step(step: dict, controller: keyboard.Controller) -> None:
    step_type = step["type"]
    if step_type == "wait":
        sleep(float(step["seconds"]))
    elif step_type == "click":
        pyautogui.click(
            int(step["x"]),
            int(step["y"]),
            button=step.get("button", "left"),
        )
    elif step_type == "click_image":
        image_path = resolve_image_path(step["image"])
        location = _locate_image(image_path, step)
        if location is None:
            raise RuntimeError(f"Image not found on screen: {step['image']}")
        pyautogui.click(pyautogui.center(location))
    elif step_type == "key_down":
        controller.press(str_to_key(step["key"]))
    elif step_type == "key_up":
        controller.release(str_to_key(step["key"]))
    else:
        raise ValueError(f"Unknown step type: {step_type}")


def run_steps(
    steps: list[dict],
    stop_event: threading.Event | None = None,
) -> None:
    controller = keyboard.Controller()
    for step in steps:
        if stop_event and stop_event.is_set():
            break
        delay = float(step.get("delay", 0))
        if _interruptible_sleep(delay, stop_event):
            break
        if stop_event and stop_event.is_set():
            break
        if step["type"] == "while_image":
            _run_while_image(step, stop_event)
        else:
            _execute_step(step, controller)


def _run_while_image(step: dict, stop_event: threading.Event | None) -> None:
    image_path = resolve_image_path(step["image"])
    interval = float(step.get("interval", 0.5))
    max_iterations = int(step.get("max_iterations", 0))
    iterations = 0
    while not (stop_event and stop_event.is_set()):
        location = _locate_image(image_path, step)
        if location is None:
            break
        pyautogui.click(pyautogui.center(location))
        iterations += 1
        if max_iterations > 0 and iterations >= max_iterations:
            break
        if _interruptible_sleep(interval, stop_event):
            break


class MacroRecorder:
    def __init__(self, on_stop: Callable[[], None] | None = None) -> None:
        self._on_stop = on_stop
        self._events: list[dict] = []
        self._keyboard_listener: keyboard.Listener | None = None
        self._mouse_listener: mouse.Listener | None = None
        self._recording = False
        self._last_time = 0.0
        self._ignored_keys: set[str] = set()

    @property
    def events(self) -> list[dict]:
        return list(self._events)

    @property
    def is_recording(self) -> bool:
        return self._recording

    def start(self) -> None:
        if self._recording:
            return
        self._events = []
        self._last_time = perf_counter()
        self._recording = True
        self._ignored_keys = set()
        self._keyboard_listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._mouse_listener = mouse.Listener(on_click=self._on_click)
        self._keyboard_listener.start()
        self._mouse_listener.start()

    def stop(self) -> list[dict]:
        if not self._recording:
            return self.events
        self._recording = False
        if self._keyboard_listener:
            self._keyboard_listener.stop()
            self._keyboard_listener = None
        if self._mouse_listener:
            self._mouse_listener.stop()
            self._mouse_listener = None
        return self.events

    def _should_stop(self, key: keyboard.Key | keyboard.KeyCode) -> bool:
        return key == STOP_RECORD_KEY

    def _is_ignored(self, key: keyboard.Key | keyboard.KeyCode) -> bool:
        return key_to_str(key) in self._ignored_keys

    def _append_step(self, step: dict) -> None:
        now = perf_counter()
        step["delay"] = now - self._last_time
        self._events.append(step)
        self._last_time = now

    def _on_click(
        self,
        x: int,
        y: int,
        button: mouse.Button,
        pressed: bool,
    ) -> None:
        if not self._recording or not pressed:
            return
        self._append_step(
            {
                "type": "click",
                "x": x,
                "y": y,
                "button": button_to_str(button),
            }
        )

    def _on_press(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        if self._should_stop(key):
            self._ignored_keys.add(key_to_str(key))
            self.stop()
            if self._on_stop:
                self._on_stop()
            return
        if not self._recording or self._is_ignored(key):
            return
        self._append_step({"type": "key_down", "key": key_to_str(key)})

    def _on_release(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        if not self._recording or self._is_ignored(key):
            return
        self._append_step({"type": "key_up", "key": key_to_str(key)})


def save_macro(name: str, steps: list[dict]) -> Path:
    MACROS_DIR.mkdir(exist_ok=True)
    safe_name = _sanitize_name(name)
    path = MACROS_DIR / f"{safe_name}.json"
    data = {
        "name": name.strip(),
        "created": datetime.now(timezone.utc).isoformat(),
        "events": steps,
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def load_macro(name_or_path: str | Path) -> dict:
    path = Path(name_or_path)
    if not path.suffix:
        path = MACROS_DIR / f"{_sanitize_name(str(name_or_path))}.json"
    if not path.exists():
        raise FileNotFoundError(f"Macro not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_macros() -> list[str]:
    if not MACROS_DIR.exists():
        return []
    return sorted(path.stem for path in MACROS_DIR.glob("*.json"))


def play_macro(
    steps: list[dict],
    stop_event: threading.Event | None = None,
) -> None:
    run_steps(steps, stop_event)
