import pyautogui
import time
import random
import typing
import threading

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0
HOTKEY = "F1"

def click():
    pyautogui.click()

def drag(start_x, start_y, end_x, end_y, duration=0.5):
    pyautogui.moveTo(start_x, start_y)
    pyautogui.dragTo(end_x, end_y, duration=duration)

def click_at_intervals(interval=1, randomness=0):
    while True:
        click()
        time.sleep(interval + random.uniform(-randomness, randomness))

def start_autoclicker(interval=1):
    thread = threading.Thread(target=click_at_intervals, args=(interval,))
    thread.start()
    return thread

def click_at_image(image_path, interval=1, randomness=0):
    image = pyautogui.locateOnScreen(image_path)
    if image:
        click_at_intervals(interval, randomness)
    else:
        print(f"Image {image_path} not found")

def main():
    thread = start_autoclicker(1)
    thread.join()

if __name__ == "__main__":
    main()