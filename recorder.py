import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter, sleep
from typing import Callable

import pyautogui
from pynput import keyboard, mouse

IMAGE_NOT_FOUND_ERRORS: tuple[type[BaseException], ...] = (pyautogui.ImageNotFoundException,)
try:
    from pyscreeze import ImageNotFoundException

    IMAGE_NOT_FOUND_ERRORS = (
        pyautogui.ImageNotFoundException,
        ImageNotFoundException,
    )
except ImportError:
    pass

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0

MACROS_DIR = Path(__file__).parent / "macros"
IMAGES_DIR = Path(__file__).parent / "images"
STOP_RECORD_KEY = keyboard.Key.f2
STOP_PLAYBACK_KEY = keyboard.Key.f2

STEP_TYPES = (
    "wait",
    "click",
    "drag",
    "click_image",
    "click_all",
    "loop",
    "while_image",
    "key_down",
    "key_up",
)

MIN_DRAG_DISTANCE = 10

CONDITION_TYPES = (
    "count",
    "image_visible",
    "image_absent",
    "until_key",
)

CONDITION_LABELS = {
    "count": "Repeat N times (for loop)",
    "image_visible": "While image is on screen",
    "image_absent": "While image is not on screen",
    "until_key": "Until key is pressed",
}

MIN_STEP_DELAY = 0.001


def is_skippable_step_error(exc: Exception) -> bool:
    """Only image-on-screen misses are skipped; interrupts and real failures stop."""
    if isinstance(exc, IMAGE_NOT_FOUND_ERRORS):
        return True
    if isinstance(exc, pyautogui.FailSafeException):
        return False
    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
        return False
    if isinstance(exc, RuntimeError):
        message = str(exc).lower()
        return "not found on screen" in message or "no matches found" in message
    return False


def _should_stop(stop_event: threading.Event | None) -> bool:
    return bool(stop_event and stop_event.is_set())


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


def format_condition(condition: dict) -> str:
    ctype = condition["type"]
    if ctype == "count":
        return f"{condition['times']} times"
    if ctype == "image_visible":
        return f"while {Path(condition['image']).name} is visible"
    if ctype == "image_absent":
        return f"while {Path(condition['image']).name} is absent"
    if ctype == "until_key":
        return f"until {condition['key']} is pressed"
    return ctype


def format_step(step: dict, indent: int = 0) -> str:
    prefix = "  " * indent
    step_type = step["type"]
    if step_type == "loop":
        body_count = len(step.get("steps", []))
        summary = format_condition(step["condition"])
        interval = float(step.get("interval", 0))
        interval_note = f", {interval}s between" if interval else ""
        return f"{prefix}Loop ({summary}{interval_note}, {body_count} steps)"
    if step_type == "wait":
        return f"{prefix}Wait {step['seconds']}s"
    if step_type == "click":
        button = step.get("button", "left")
        return f"{prefix}Click {button} at ({step['x']}, {step['y']})"
    if step_type == "drag":
        button = step.get("button", "left")
        duration = float(step.get("duration", 0.5))
        return (
            f"{prefix}Drag {button} "
            f"({step['start_x']}, {step['start_y']}) → ({step['end_x']}, {step['end_y']}) "
            f"in {duration}s"
        )
    if step_type == "click_image":
        return f"{prefix}Click image: {Path(step['image']).name}"
    if step_type == "click_all":
        interval = float(step.get("interval", 0.5))
        dedupe = float(step.get("dedupe_overlap", 0.5))
        confidence = step.get("confidence")
        confidence_note = f", confidence {confidence}" if confidence is not None else ""
        dedupe_note = f", dedupe {dedupe}" if dedupe > 0 else ", dedupe off"
        return (
            f"{prefix}Click all: {Path(step['image']).name} "
            f"({interval}s between clicks{confidence_note}{dedupe_note})"
        )
    if step_type == "while_image":
        interval = step.get("interval", 0.5)
        return f"{prefix}While image exists, click every {interval}s: {Path(step['image']).name}"
    if step_type == "key_down":
        return f"{prefix}Key down: {step['key']}"
    if step_type == "key_up":
        return f"{prefix}Key up: {step['key']}"
    return f"{prefix}{step}"


def expand_step_delays(steps: list[dict]) -> list[dict]:
    expanded: list[dict] = []
    for step in steps:
        delay = float(step.get("delay", 0))
        clean = {key: value for key, value in step.items() if key != "delay"}
        if clean.get("type") == "loop":
            clean["steps"] = expand_step_delays(clean.get("steps", []))
        if delay >= MIN_STEP_DELAY:
            expanded.append({"type": "wait", "seconds": round(delay, 3)})
        expanded.append(clean)
    return expanded


def flatten_steps_for_display(steps: list[dict], indent: int = 0) -> list[str]:
    lines: list[str] = []
    counter = 1
    prefix_indent = "  " * indent

    for step in steps:
        delay = float(step.get("delay", 0))
        if delay >= MIN_STEP_DELAY:
            lines.append(f"{counter}. {prefix_indent}Wait {delay:.2f}s")
            counter += 1
        lines.append(f"{counter}. {format_step(step, indent)}")
        counter += 1
        if step.get("type") == "loop":
            for subline in flatten_steps_for_display(step.get("steps", []), indent + 1):
                lines.append(subline)
    return lines


def _interruptible_sleep(seconds: float, stop_event: threading.Event | None) -> bool:
    if seconds <= 0:
        return False
    deadline = perf_counter() + seconds
    while perf_counter() < deadline:
        if stop_event and stop_event.is_set():
            return True
        if pyautogui.FAILSAFE:
            pyautogui.failSafeCheck()
        remaining = deadline - perf_counter()
        if remaining <= 0:
            break
        sleep(min(0.05, remaining))
    return False


class GlobalHotkeyListener:
    def __init__(
        self,
        hotkey: keyboard.Key,
        on_press: Callable[[], None],
    ) -> None:
        self._hotkey = hotkey
        self._on_press = on_press
        self._listener: keyboard.Listener | None = None

    def start(self) -> None:
        if self._listener:
            return

        def handle_press(key: keyboard.Key | keyboard.KeyCode) -> None:
            if key == self._hotkey:
                self._on_press()

        self._listener = keyboard.Listener(on_press=handle_press)
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None


def _image_locate_kwargs(step: dict) -> dict:
    kwargs = {}
    if "confidence" in step:
        kwargs["confidence"] = float(step["confidence"])
    return kwargs


def _locate_image(image_path: Path, step: dict):
    try:
        return pyautogui.locateOnScreen(str(image_path), **_image_locate_kwargs(step))
    except IMAGE_NOT_FOUND_ERRORS:
        return None


def _box_iou(box_a, box_b) -> float:
    x1 = max(box_a.left, box_b.left)
    y1 = max(box_a.top, box_b.top)
    x2 = min(box_a.left + box_a.width, box_b.left + box_b.width)
    y2 = min(box_a.top + box_a.height, box_b.top + box_b.height)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    intersection = (x2 - x1) * (y2 - y1)
    union = box_a.width * box_a.height + box_b.width * box_b.height - intersection
    if union <= 0:
        return 0.0
    return intersection / union


def _dedupe_overlapping_locations(
    locations: list,
    overlap_threshold: float = 0.5,
) -> list:
    """Merge duplicate detections of the same on-screen object (overlapping boxes)."""
    if overlap_threshold <= 0 or len(locations) <= 1:
        return list(locations)

    ordered = sorted(locations, key=lambda box: (box.top, box.left, box.width, box.height))
    kept: list = []
    for box in ordered:
        if any(_box_iou(box, other) >= overlap_threshold for other in kept):
            continue
        kept.append(box)
    return kept


def _locate_all_images(image_path: Path, step: dict) -> list:
    try:
        locations = list(
            pyautogui.locateAllOnScreen(str(image_path), **_image_locate_kwargs(step))
        )
    except IMAGE_NOT_FOUND_ERRORS:
        return []
    overlap_threshold = float(step.get("dedupe_overlap", 0.5))
    locations = _dedupe_overlapping_locations(locations, overlap_threshold)
    return sorted(locations, key=lambda box: (box.top, box.left))


def _click_region_center(location, button: str = "left") -> None:
    center = pyautogui.center(location)
    pyautogui.click(int(center.x), int(center.y), button=button)


class _KeyPressWatcher:
    def __init__(self, key_str: str) -> None:
        self._key_str = key_str
        self._pressed = threading.Event()
        self._listener: keyboard.Listener | None = None

    def start(self) -> None:
        def on_press(key: keyboard.Key | keyboard.KeyCode) -> None:
            if key_to_str(key) == self._key_str:
                self._pressed.set()

        self._listener = keyboard.Listener(on_press=on_press)
        self._listener.start()

    def was_pressed(self) -> bool:
        return self._pressed.is_set()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None


def _condition_continues(
    condition: dict,
    iteration: int,
    stop_event: threading.Event | None,
    key_watcher: _KeyPressWatcher | None,
) -> bool:
    if stop_event and stop_event.is_set():
        return False

    ctype = condition["type"]
    if ctype == "count":
        return iteration < int(condition["times"])
    if ctype == "image_visible":
        image_path = resolve_image_path(condition["image"])
        return _locate_image(image_path, condition) is not None
    if ctype == "image_absent":
        image_path = resolve_image_path(condition["image"])
        return _locate_image(image_path, condition) is None
    if ctype == "until_key":
        return not (key_watcher and key_watcher.was_pressed())
    raise ValueError(f"Unknown loop condition: {ctype}")


def _run_loop(
    step: dict,
    stop_event: threading.Event | None,
    on_error: Callable[[dict, Exception], None] | None = None,
) -> None:
    condition = step["condition"]
    interval = float(step.get("interval", 0))
    body = step.get("steps", [])

    key_watcher: _KeyPressWatcher | None = None
    if condition["type"] == "until_key":
        key_watcher = _KeyPressWatcher(condition["key"])
        key_watcher.start()

    try:
        iteration = 0
        while _condition_continues(condition, iteration, stop_event, key_watcher):
            run_steps(body, stop_event, on_error)
            if _should_stop(stop_event):
                break
            iteration += 1
            if _interruptible_sleep(interval, stop_event):
                break
    finally:
        if key_watcher:
            key_watcher.stop()


def _execute_step(
    step: dict,
    controller: keyboard.Controller,
    stop_event: threading.Event | None = None,
) -> None:
    step_type = step["type"]
    if step_type == "wait":
        _interruptible_sleep(float(step["seconds"]), stop_event)
        return
    elif step_type == "click":
        pyautogui.click(
            int(step["x"]),
            int(step["y"]),
            button=step.get("button", "left"),
        )
    elif step_type == "drag":
        if _should_stop(stop_event):
            return
        start_x = int(step["start_x"])
        start_y = int(step["start_y"])
        end_x = int(step["end_x"])
        end_y = int(step["end_y"])
        duration = max(0.0, float(step.get("duration", 0.5)))
        button = step.get("button", "left")
        pyautogui.moveTo(start_x, start_y)
        if duration > 0:
            pyautogui.dragTo(end_x, end_y, duration=duration, button=button)
        else:
            pyautogui.dragTo(end_x, end_y, button=button)
    elif step_type == "click_image":
        if _should_stop(stop_event):
            return
        image_path = resolve_image_path(step["image"])
        location = _locate_image(image_path, step)
        if _should_stop(stop_event):
            return
        if location is None:
            raise RuntimeError(f"Image not found on screen: {step['image']}")
        _click_region_center(location)
    elif step_type == "key_down":
        controller.press(str_to_key(step["key"]))
    elif step_type == "key_up":
        controller.release(str_to_key(step["key"]))
    else:
        raise ValueError(f"Unknown step type: {step_type}")


def _run_single_step(
    step: dict,
    controller: keyboard.Controller,
    stop_event: threading.Event | None,
    on_error: Callable[[dict, Exception], None] | None,
) -> None:
    step_type = step["type"]
    if step_type == "loop":
        _run_loop(step, stop_event, on_error)
    elif step_type == "while_image":
        _run_while_image(step, stop_event)
    elif step_type == "click_all":
        _run_click_all(step, stop_event, on_error)
    else:
        _execute_step(step, controller, stop_event)


def run_steps(
    steps: list[dict],
    stop_event: threading.Event | None = None,
    on_error: Callable[[dict, Exception], None] | None = None,
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
        try:
            _run_single_step(step, controller, stop_event, on_error)
        except pyautogui.FailSafeException:
            if stop_event:
                stop_event.set()
            break
        except Exception as exc:
            if is_skippable_step_error(exc):
                if on_error:
                    on_error(step, exc)
            else:
                if stop_event:
                    stop_event.set()
                break


def _run_click_all(
    step: dict,
    stop_event: threading.Event | None,
    on_error: Callable[[dict, Exception], None] | None = None,
) -> None:
    if _should_stop(stop_event):
        return
    image_path = resolve_image_path(step["image"])
    interval = float(step.get("interval", 0.5))
    locations = _locate_all_images(image_path, step)
    if _should_stop(stop_event):
        return
    if not locations:
        if on_error:
            on_error(
                step,
                RuntimeError(f"No matches found for image: {step['image']}"),
            )
        return

    for index, location in enumerate(locations):
        if _should_stop(stop_event):
            break
        _click_region_center(location)
        if _should_stop(stop_event):
            break
        if index < len(locations) - 1 and interval > 0:
            if _interruptible_sleep(interval, stop_event):
                break


def _run_while_image(step: dict, stop_event: threading.Event | None) -> None:
    image_path = resolve_image_path(step["image"])
    interval = float(step.get("interval", 0.5))
    max_iterations = int(step.get("max_iterations", 0))
    iterations = 0
    while not _should_stop(stop_event):
        location = _locate_image(image_path, step)
        if location is None:
            break
        _click_region_center(location)
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
        self._drag_active = False
        self._drag_start: tuple[int, int, str] | None = None
        self._drag_last: tuple[int, int] | None = None
        self._drag_press_time = 0.0

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
        self._drag_active = False
        self._drag_start = None
        self._drag_last = None
        self._keyboard_listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._mouse_listener = mouse.Listener(
            on_move=self._on_move,
            on_click=self._on_click,
        )
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

    def _on_move(self, x: int, y: int) -> None:
        if self._recording and self._drag_active:
            self._drag_last = (x, y)

    def _on_click(
        self,
        x: int,
        y: int,
        button: mouse.Button,
        pressed: bool,
    ) -> None:
        if not self._recording:
            return

        if pressed:
            self._drag_start = (x, y, button_to_str(button))
            self._drag_last = (x, y)
            self._drag_press_time = perf_counter()
            self._drag_active = True
            return

        if not self._drag_active or self._drag_start is None:
            return

        start_x, start_y, btn = self._drag_start
        end_x, end_y = self._drag_last if self._drag_last else (x, y)
        duration = max(0.05, perf_counter() - self._drag_press_time)
        distance = ((end_x - start_x) ** 2 + (end_y - start_y) ** 2) ** 0.5

        if distance >= MIN_DRAG_DISTANCE:
            self._append_step(
                {
                    "type": "drag",
                    "start_x": start_x,
                    "start_y": start_y,
                    "end_x": end_x,
                    "end_y": end_y,
                    "duration": round(duration, 3),
                    "button": btn,
                }
            )
        else:
            self._append_step(
                {
                    "type": "click",
                    "x": start_x,
                    "y": start_y,
                    "button": btn,
                }
            )

        self._drag_active = False
        self._drag_start = None
        self._drag_last = None

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
        "events": expand_step_delays(steps),
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
    on_error: Callable[[dict, Exception], None] | None = None,
) -> None:
    run_steps(steps, stop_event, on_error)
