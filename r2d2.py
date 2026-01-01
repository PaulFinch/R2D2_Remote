from __future__ import annotations

import asyncio
import os
import signal
import sys
import math
import logging
from dataclasses import dataclass
from typing import Optional
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame
from bleak import BleakClient, BleakScanner

TARGET_NAME: str = "R2D2"
UUID_CMD: str = "0000fff1-0000-1000-8000-00805f9b34fb"
UUID_NOTIFY: str = "0000fff2-0000-1000-8000-00805f9b34fb"

SCAN_TIMEOUT: float = 5.0
LOOP_PERIOD: float = 0.20
LOOP_COUNT: int = 10
AXIS_THRESHOLD: float = 0.7

BUTTON_SND_1: int = 0
BUTTON_SND_2: int = 1
BUTTON_SND_3: int = 2
BUTTON_SND_4: int = 3
BUTTON_HEAD_LEFT: int = 4
BUTTON_HEAD_RIGHT: int = 5
BUTTON_LED_BLUE: int = 6
BUTTON_LED_RED: int = 7

LED_SEQ = [0x00, 0x01, 0x02, 0x03]

P00: int = 0xB5
P12: int = 0x7C
P13: int = 0x6B
P14: int = 0x5A
P15: int = 0x49
P16: int = 0x38
P17: int = 0x27
P18: int = 0x16
P19: int = 0x05
NUL: int = 0x00

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("R2D2")

@dataclass
class ControlState:
    snd: int = 0x00         # SOUND
    mt1: int = 0x00         # MOTOR 1
    sp1: int = 0x00         # MOTOR 1 SPEED
    mt2: int = 0x00         # MOTOR 2
    sp2: int = 0x00         # MOTOR 2 SPEED
    hed: int = 0x14         # HEAD POSITION
    ldb: int = 0x00         # BLUE LED
    ldr: int = 0x00         # RED LED

    def reset(self) -> None:
        self.mt1 = self.mt2 = 0x00
        self.sp1 = self.sp2 = 0x03
        self.hed = 0x14
        self.snd = 0x00

    def to_payload(self) -> bytes:
        return bytes([
            P00,
            self.snd,
            NUL,
            int(self.mt1),
            int(self.sp1),
            int(self.mt2),
            int(self.sp2),
            self.hed,
            NUL,
            NUL,
            self.ldb,
            self.ldr,
            P12, P13, P14, P15, P16, P17, P18, P19,
        ])

async def find_device_by_name(name: str) -> Optional[str]:
    devices = await BleakScanner.discover(timeout=SCAN_TIMEOUT)
    for d in devices:
        if d.name == name:
            return d.address
    return None

async def send_payload(client: BleakClient, payload: bytes) -> None:
    await client.write_gatt_char(UUID_CMD, payload, response=False)

def map_head_axis(axis_value: float, gamma: float = 2.0, center: int = 0x14, left_min: int = 0x04, right_max: int = 0x24, deadzone: float = 0.05) -> int:
    axis_value = max(-1.0, min(1.0, axis_value))

    if abs(axis_value) < deadzone:
        return center

    sign = 1 if axis_value > 0 else -1
    shaped = sign * (abs(axis_value) ** gamma)

    if shaped < 0:
        span = center - left_min
    else:
        span = right_max - center

    return int(round(center + shaped * span))

def update_from_joystick(state: ControlState, joy: pygame.joystick.Joystick) -> None:
    state.reset()

    if joy.get_numaxes() > 1:
        x: float = joy.get_axis(0)
        y: float = joy.get_axis(1)

        if y < -AXIS_THRESHOLD:
            state.mt1 = state.mt2 = 0x01
        elif y > AXIS_THRESHOLD:
            state.mt1 = state.mt2 = 0x02
        elif x < -AXIS_THRESHOLD:
            state.mt1 = 0x02
            state.mt2 = 0x01
        elif x > AXIS_THRESHOLD:
            state.mt1 = 0x01
            state.mt2 = 0x02

    if joy.get_numaxes() > 3:
        state.hed = map_head_axis(joy.get_axis(3))

    buttons: int = joy.get_numbuttons()

    if buttons > BUTTON_SND_1:
        if joy.get_button(BUTTON_SND_1):
            state.snd = 0x0A
    
    if buttons > BUTTON_SND_2:
        if joy.get_button(BUTTON_SND_2):
            state.snd = 0x08
    
    if buttons > BUTTON_SND_3:
        if joy.get_button(BUTTON_SND_3):
            state.snd = 0x09

    if buttons > BUTTON_SND_4:
        if joy.get_button(BUTTON_SND_4):
            state.snd = 0x05

    if buttons > BUTTON_HEAD_LEFT:
        if joy.get_button(BUTTON_HEAD_LEFT):
            state.hed = 0x04

    if buttons > BUTTON_HEAD_RIGHT:
        if joy.get_button(BUTTON_HEAD_RIGHT):
            state.hed = 0x24

    if buttons > BUTTON_LED_BLUE:
        if joy.get_button(BUTTON_LED_BLUE):
            state.ldb = LED_SEQ[(LED_SEQ.index(state.ldb) + 1) % len(LED_SEQ)]

    if buttons > BUTTON_LED_RED:
        if joy.get_button(BUTTON_LED_RED):
            state.ldr = LED_SEQ[(LED_SEQ.index(state.ldr) + 1) % len(LED_SEQ)]

async def main() -> None:
    logger.info("[R2D2 CONTROLLER]")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, stop_event.set)

    pygame.init()
    pygame.joystick.init()

    logger.info("Searching for joypad...")
    if pygame.joystick.get_count() == 0:
        logger.error("No joypad detected")
        return

    joy = pygame.joystick.Joystick(0)
    joy.init()
    logger.info("Joypad detected: %s", joy.get_name())

    while not stop_event.is_set():
        try:
            logger.info("Scanning for: %s", TARGET_NAME)

            address = await find_device_by_name(TARGET_NAME)

            if address is None:
                await asyncio.sleep(2)
                continue

            logger.info("Found R2D2 at: %s", address)
            logger.info("Connecting...")

            disconnected = asyncio.Event()

            def on_disconnect(_: BleakClient):
                logger.info("BLE Disconnected")
                disconnected.set()

            client = BleakClient(address, disconnected_callback=on_disconnect)
            await client.connect()

            if not client.is_connected:
                logger.error("BLE connection failed")
                await asyncio.sleep(2)
                continue

            logger.info("Connected")

            state = ControlState()
            last_payload: bytes | None = None
            iterations_since_send = 0

            while not stop_event.is_set() and not disconnected.is_set():
                try:
                    pygame.event.pump()
                    update_from_joystick(state, joy)

                    payload = state.to_payload()
                    iterations_since_send += 1

                    if payload != last_payload or iterations_since_send >= LOOP_COUNT:
                        await send_payload(client, payload)
                        last_payload = payload
                        iterations_since_send = 0

                    await asyncio.sleep(LOOP_PERIOD)

                except asyncio.CancelledError:
                    logger.info("Cancelled")
                    raise

        except asyncio.CancelledError:
            logger.info("Cancelled")
            break

        except Exception as e:
            logger.error("Error %s: %s", type(e).__name__, e)

        finally:
            try:
                if 'client' in locals() and client.is_connected:
                    logger.info("Disconnecting...")
                    await asyncio.shield(client.disconnect())
            except Exception:
                pass

        await asyncio.sleep(1)

    logger.info("Bye.")

if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0)
