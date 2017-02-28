#!/usr/bin/python
import curses
from solidraspi import StepperMotor, cleanup

stdscr = curses.initscr()
curses.noecho()
curses.cbreak()
stdscr.keypad(True)

stdscr.addstr(1,0,"Presionar las flechas para controlarlo")
stdscr.addstr(2,0,"Presionar 'q' para terminar")
stdscr.refresh()

motor_v = StepperMotor(31, 33, 35, 37)
motor_h = StepperMotor(15, 19, 21, 23)

motor_v.limit_angles(-30, 100)
motor_h.limit_angles(-90, 90)

motor_v.setup(min_pulse_delay=0.008)

key = ''
while key != ord('q'):
    key = stdscr.getch()
    if key == curses.KEY_UP:
        motor_v.turn_async(4, 0)
    elif key == curses.KEY_DOWN:
        motor_v.turn_async(-4, 0)
    elif key == curses.KEY_LEFT:
        motor_h.turn_async(-4, 0)
    elif key == curses.KEY_RIGHT:
        motor_h.turn_async(4, 0) 

motor_v.turn_to_angle_async(0, 0.5)
motor_h.turn_to_angle_async(0, 0.5)
motor_v.wait_until_finish_turning()
motor_h.wait_until_finish_turning()

cleanup()

curses.nocbreak()
stdscr.keypad(False)
curses.echo()
curses.endwin()
