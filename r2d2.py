from __future__ import annotations

import asyncio
import os
import signal
import sys
from dataclasses import dataclass

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import pygame
from bleak import BleakClient, BleakScanner

TARGET_NAME: str = "R2D2"
UUID_CMD: str = "0000fff1-0000-1000-8000-00805f9b34fb"
UUID_NOTIFY: str = "0000fff2-0000-1000-8000-00805f9b34fb"

SCAN_TIMEOUT: float = 5.0
LOOP_PERIOD: float = 0.20
LOOP_COUNT: int = 10
AXIS_THRESHOLD: float = 0.5

BUTTON_SND_1: int = 0
BUTTON_SND_2: int = 1
BUTTON_SND_3: int = 2
BUTTON_SND_4: int = 3
BUTTON_HEAD_LEFT: int = 4
BUTTON_HEAD_RIGHT: int = 5
BUTTON_LED_BLUE: int = 6
BUTTON_LED_RED: int = 7

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

def update_from_joystick(state: ControlState, joy: pygame.joystick.Joystick) -> None:
    state.reset()

    if joy.get_numaxes() >= 2:
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
            state.ldb ^= 0x01

    if buttons > BUTTON_LED_RED:
        if joy.get_button(BUTTON_LED_RED):
            state.ldr ^= 0x01

async def main() -> None:
    print("[R2D2 CONTROLLER]")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, stop_event.set)

    pygame.init()
    pygame.joystick.init()

    print("- Searching for joypad...")
    if pygame.joystick.get_count() > 0:
        joy = pygame.joystick.Joystick(0)
        joy.init()
        print(f"- Joypad detected: {joy.get_name()}")
    else:
        print("ERROR: No joypad detected")
        return

    print(f"- Searching for {TARGET_NAME}...")
    address = await find_device_by_name(TARGET_NAME)
    if address is None:
        print("ERROR: R2D2 not found")
        return

    print(f"- R2D2 detected")
    print(f"- Connecting to {address}...")

    client = BleakClient(address)
    await client.connect()

    if not client.is_connected:
        print("ERROR: BLE connection failed")
        return

    print("- Connected")
    state = ControlState()

    last_payload: bytes | None = None
    iterations_since_send: int = 0

    try:
        while not stop_event.is_set():
            pygame.event.pump()
            update_from_joystick(state, joy)

            payload = state.to_payload()
            iterations_since_send += 1

            if payload != last_payload or iterations_since_send >= LOOP_COUNT:
                await send_payload(client, payload)
                last_payload = payload
                iterations_since_send = 0

            await asyncio.sleep(LOOP_PERIOD)
    finally:
        try:
            print()
            await asyncio.shield(client.disconnect())
        except (asyncio.CancelledError, EOFError):
            pass

    print("Bye.")
    return

if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0)
