#!/usr/bin/python
from time import sleep
from solidraspi import StepperMotor, cleanup
from math import sin, radians

if __name__ == "__main__":

    motor_v = StepperMotor(31, 33, 35, 37)
    motor_h = StepperMotor(15, 19, 21, 23)

    motor_v.limit_angles(-30, 100)
    motor_h.limit_angles(-90, 90)

    motor_v.setup(min_pulse_delay=0.008)

    try:

        while True:
            for i in xrange(0, 360, 1):
                #print "step %d degree %f"%(i, sin(radians(i))*90)
                motor_v.turn_to_angle_async( 40+sin(radians(i))*65, 0.01 )
                motor_h.turn_to_angle_async( sin(radians(i)*2)*90, 0.01 )
                sleep(0.01)


    except KeyboardInterrupt: pass
    
    motor_v.turn_to_angle_async(0, 0.5)
    motor_h.turn_to_angle_async(0, 0.5)
    motor_v.wait_until_finish_turning()
    motor_h.wait_until_finish_turning()

    cleanup()

