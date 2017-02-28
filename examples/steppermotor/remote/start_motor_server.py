#!/usr/bin/python
import SocketServer
import re

from solidraspi import StepperMotor, cleanup

__LOCALHOST_IP_NUMBER_ = "0.0.0.0"
__LOCALHOST_IP_PORT__ = 3313

class MyTCPHandler(SocketServer.BaseRequestHandler):
    def handle(self):
	self.data = self.request.recv(512)

	if not self.data: return

        r_search = re.search(r"x=([^&]+)&y=([^ ]+)&relative=(.)", self.data )

        h_degree = float(r_search.group(1))
	v_degree = float(r_search.group(2))
	relative = bool(int(r_search.group(3)))

        #print h_degree, v_degree, relative

	if relative:
	    motor_h.turn_async( h_degree*90, 0.2 )
	    motor_v.turn_async( v_degree*90, 0.2 )
	else:
	    motor_h.turn_to_angle_async( h_degree, (0.2/90)*h_degree )
	    motor_v.turn_to_angle_async( v_degree, (0.2/90)*v_degree )

if __name__ == "__main__":
    ADD,PORT = __LOCALHOST_IP_NUMBER_, __LOCALHOST_IP_PORT__

    print "Starting HTTP Motor server on", ADD,"[",PORT,"]"
    print "Waiting for requests..."

    server = SocketServer.TCPServer((ADD,PORT), MyTCPHandler)

    motor_v = StepperMotor(31, 33, 35, 37)
    motor_h = StepperMotor(15, 19, 21, 23)

    motor_v.limit_angles(-30, 100)
    motor_h.limit_angles(-90, 90)

    motor_v.setup(min_pulse_delay=0.008)

    try:
	server.serve_forever()
    except KeyboardInterrupt: pass

    server.shutdown()
    server.server_close()

    motor_v.turn_to_angle_async(0, 0.5)
    motor_h.turn_to_angle_async(0, 0.5)
    motor_v.wait_until_finish_turning()
    motor_h.wait_until_finish_turning()

    cleanup()


	
