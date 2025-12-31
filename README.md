# Clementoni R2D2 Remote Controller
This is a controller for the Clementoni R2D2 Robot.

The robot is originally controlled by the Official App.
This script allows to control the robot with a physical gamepad.

# Requirements:
- Clementoni R2D2 Robot
- Joystick/Gamepad (Tested with a Buffalo SNES Gamepad)
- Bluetooth connectivity
- Python >= 3.7
- Pyton Modules: bleak, pygame

# Payload
This is the bluetooth payload I figured out:

|----|-------|--|--------|-------|--------|--------|------|--|--|-------- -|---------|------------------|
| b5 | SOUND |  | MOTOR1 | SPEED | MOTOR2 | SPEED2 | HEAD |  |  | BLUE LED | RED LED | 7c6b5a4938271605 |

# Button Assignments
| ID | ACTION          |
|:--:|:---------------:|
| 0  | SOUND 1         |
| 1  | SOUND 2         |
| 2  | SOUND 3         |
| 3  | SOUND 4         |
| 4  | TURN HEAD LEFT  |
| 5  | TURN HEAD RIGHT |
| 6  | TOGGLE BLUE LED |
| 7  | TOGGLE RED LED  |

# Use the script
```
pip install -r requirements.txt
python r2d2.py
```
