# -*- coding: utf-8 -*-

# The MIT License (MIT)
#
# Copyright (c) 2016 Sergio Burdisso
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from datetime import datetime, tzinfo, timedelta, time
from threading import Thread, Event, Timer
from sqlite3 import connect as db_connect
from collections import defaultdict
from httplib import HTTPConnection
from RPi import GPIO as IO
from time import sleep
from os import system

import json


__version__ = "0.9.0"
__license__ = 'MIT'



class SolidTimer(Thread):
    __countup__= 0
    __stopped__= True
    __start_signal__= None
    
    __interval__= 0
    __function__= None
    __args__= None

    __stopped_during_sleep__= False
    
    def __init__(s, interval, function, args= []):
        s.__interval__= interval if interval > 0 else 1
        s.__function__= function
        s.__args__= args
        
        s.__start_signal__= Event()
        
        Thread.__init__(s)
        Thread.setDaemon(s, True)
        Thread.start(s)

    def run(s):
        while True:
            s.__start_signal__.wait()
            s.__stopped_during_sleep__= False
            sleep(1)
            s.__countup__= (s.__countup__ + 1) % s.__interval__

            # if it was stopped during sleep?
            if s.__stopped_during_sleep__:
                s.__countup__= 0
            elif s.__countup__ == 0:
                apply(s.__function__, s.__args__)

    def setInterval(s, interval):
        s.__interval__= interval

    def start(s):
        if s.__stopped__:
            s.__stopped__= False
            s.__start_signal__.set()

    def stop(s):
        if not s.__stopped__:
            s.__stopped__ = True
            s.__stopped_during_sleep__= True
            s.__start_signal__.clear()


class TaskScheduler:
    Date_synced= False
    GMT_offset= -3
    Use_http_server= True
    Sync_www_list= ["www.google.com", "www.facebook.com", "www.twitter.com", "www.tworld-ai.com"]

    __DB_conn__= None
    __Sync_timer__= None

    __db__= None
    __callback__= None
    __action_timer__= None
    __triggered__= None

    __cache_intervals__= None
    __cache_tasks__= None

    def __init__(s, action_callback):
        if not TaskScheduler.__Sync_timer__:
            TaskScheduler.__Sync_timer__= SolidTimer(60*60*6, TaskScheduler.Sync_gmttime_by_http)
            TaskScheduler.__Sync_timer__.start()

        try_sync_thread = Thread(target=TaskScheduler.__Try_sync_datetime__)
        try_sync_thread.setDaemon(True)
        try_sync_thread.start()

        s.__callback__ = action_callback
        s.__action_timer__ = SolidTimer(1, TaskScheduler.__check_tasks__, [s])
        s.__triggered__ = defaultdict(lambda: False)

        TaskScheduler.__DB_conn__ = db_connect('tasks.db')
        TaskScheduler.__DB_conn__.row_factory = s.__db_dict_factory__
        s.__db__ = TaskScheduler.__DB_conn__.cursor()

        try:
            s.__db__.executescript('''
                CREATE TABLE tasks (
                    id INTEGER NOT NULL PRIMARY KEY,
                    hour INTEGER NOT NULL,
                    minute INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    args TEXT,
                    enabled INTEGER NOT NULL
                );
                CREATE TABLE interval_tasks (
                    id_task_start INTEGER NOT NULL REFERENCES tasks(id),
                    id_task_end INTEGER NOT NULL REFERENCES tasks(id),

                    PRIMARY KEY(id_task_start, id_task_end)
                );
            ''')
            TaskScheduler.__DB_conn__.commit()
        except:pass

        s.__cache_intervals__ = s.get_interval_tasks()
        s.__cache_tasks__ = s.get_tasks()

        s.__action_timer__.start()

    def __db_dict_factory__(s, cursor, row):
        d = {}
        for idx, col in enumerate(cursor.description):
            d[col[0]] = row[idx]
        return d

    def __is_time_ok__(s, hour, minute):
        return (0 <= hour and hour < 24) and (0 <= minute and minute < 60)

    def __check_tasks__(s):
        if not TaskScheduler.Date_synced: return

        now = datetime.now().time()
        now = time(hour=now.hour, minute=now.minute)

        for task in s.__cache_intervals__:
            if task["start"]["enabled"] and task["end"]["enabled"]:
                id = (task["start"]["id"], task["end"]["id"])

                if task["start"]["time"] <= task["end"]["time"]:
                    trigger_action = (task["start"]["time"] <= now and now < task["end"]["time"])
                else:
                    trigger_action = (task["start"]["time"] <= now or now < task["end"]["time"])

                if trigger_action:
                    if not s.__triggered__[id]:
                        apply(s.__callback__, [task["start"]["action"], task["start"]["args"]])
                        s.__triggered__[id] = True
                else:
                    if s.__triggered__[id]:
                        apply(s.__callback__, [task["end"]["action"], task["end"]["args"]])
                        s.__triggered__[id] = False

        for task in s.__cache_tasks__:
            if not task["enabled"]:
                break

            id = task["id"]
            trigger_action = (task["time"] == now)

            if trigger_action:
                if not s.__triggered__[id]:
                    apply(s.__callback__, [task["action"], task["args"]])
                    s.__triggered__[id] = True
            else:
                s.__triggered__[id] = False

    def __end_interval_task__(s, id_start, id_end):
        for task in s.__cache_intervals__:
            id = (task["start"]["id"], task["end"]["id"])
            if id == (id_start, id_end) and s.__triggered__[id]:
                apply(s.__callback__, [task["end"]["action"], task["end"]["args"]])
                s.__triggered__[id] = False

    @staticmethod
    def __Try_sync_datetime__():
        while not TaskScheduler.Sync_gmttime_by_http():
            sleep(10)

    @staticmethod
    def Stop():
        TaskScheduler.__DB_conn__.close()

    @staticmethod
    def Set_datetime(iso_format_date, timespec="seconds"):
        system('sudo date -I%s -s "%s"'%(timespec, iso_format_date))
        TaskScheduler.Date_synced = True

    @staticmethod
    def Sync_gmttime_by_http():
        class GMTZone(tzinfo):
            def __init__(self, offset=0, isdst=False):
                self.offset = offset
                self.isdst = isdst
                self.name = "GMT%d"%offset
            def utcoffset(self, dt):
                return timedelta(hours=self.offset) + self.dst(dt)
            def dst(self, dt):
                    return timedelta(hours=1) if self.isdst else timedelta(0)
            def tzname(self,dt):
                 return self.name

        user_agent = {"user-agent":"Mozilla/5.0 (X11; Linux armv7l) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.91 Safari/537.36"}

        if TaskScheduler.Use_http_server:
            try:
                conn = HTTPConnection("www.worldtimeserver.com", timeout=20)
                conn.request("GET", "/handlers/GetData.ashx?action=GCTData", headers=user_agent)

                response = json.loads(conn.getresponse().read())

                TaskScheduler.Set_datetime(response["ThisTime"], "ns")
                return True
            except: pass

        GMT = GMTZone()
        GMT_3 = GMTZone(TaskScheduler.GMT_offset)
        for www in TaskScheduler.Sync_www_list:
            try:
                conn = HTTPConnection(www, timeout=20)
                conn.request("HEAD", "/", headers=user_agent)

                response = conn.getresponse().getheader("date")

                gmt_date = datetime.strptime(response, "%a, %d %b %Y %H:%M:%S GMT")
                gmt_3_date = gmt_date.replace(tzinfo=GMT).astimezone(GMT_3).isoformat()[:-6]

                TaskScheduler.Set_datetime(gmt_3_date)
                return True
            except: pass

        return False

    def add_task(s, hour, minute, action, args= None, enabled=True):
        if not s.__is_time_ok__(hour, minute): return False

        action = action if type(action) == str else action.__name__
        args = args if args == None or type(args) == str else str(args)

        id = s.__db__.execute("INSERT INTO tasks (hour, minute, action, args, enabled) VALUES (?, ?, ?, ?, ?)", (hour, minute, action, args, 1 if enabled else 0)).lastrowid
        TaskScheduler.__DB_conn__.commit()

        s.__cache_tasks__ = s.get_tasks()
        return id

    def add_interval_task(s, s_hour, s_minute, s_action, s_args, e_hour, e_minute, e_action, e_args, enabled=True):
        if not s.__is_time_ok__(s_hour, s_minute) or not s.__is_time_ok__(e_hour, e_minute):
            return False

        id_start = s.add_task(s_hour, s_minute, s_action, s_args, enabled)
        id_end = s.add_task(e_hour, e_minute, e_action, e_args, enabled)

        id = s.__db__.execute("INSERT INTO interval_tasks VALUES (?, ?)", (id_start, id_end,)).lastrowid
        TaskScheduler.__DB_conn__.commit()

        s.__cache_intervals__ = s.get_interval_tasks()

        return id

    def update_task(s, id, hour, minute, action= None, args= None):
        if not s.__is_time_ok__(hour, minute): return False

        action = action if action == None or type(action) == str else action.__name__
        args = args if args == None or type(args) == str else str(arg)

        s.__db__.execute(
            "UPDATE tasks SET hour=%d, minute=%d%s WHERE id=%d"
            %
            (hour, minute, '%s%s'%(', %s'%action if action else '', ', %s'%args if args else ''), id)
        )
        TaskScheduler.__DB_conn__.commit()

        s.__cache_tasks__ = s.get_tasks()

    def update_interval_task(s, s_id, e_id, s_hour, s_minute, e_hour, e_minute):
        s.__end_interval_task__(s_id, e_id)

        s.update_task(s_id, s_hour, s_minute)
        s.update_task(e_id, e_hour, e_minute)

        s.__cache_intervals__ = s.get_interval_tasks()

    def set_enable_task(s, id, enabled):
        s.__db__.execute("UPDATE tasks SET enabled=? WHERE id=?", (1 if enabled else 0, id,))
        TaskScheduler.__DB_conn__.commit()
        s.__cache_tasks__ = s.get_tasks()

    def set_enable_interval_task(s, id_start, id_end, enabled):
        s.set_enable_task(id_start, enabled)
        s.set_enable_task(id_end, enabled)
        if not enabled:
            s.__end_interval_task__(id_start, id_end)

        s.__cache_intervals__ = s.get_interval_tasks()

    def delete_task(s, id):
        s.__db__.execute("DELETE FROM tasks WHERE id = ?", (id,))
        TaskScheduler.__DB_conn__.commit()
        s.__cache_tasks__ = s.get_tasks()

    def delete_interval_task(s, id_start, id_end):
        s.__db__.execute("DELETE FROM interval_tasks WHERE id_task_start = ? AND id_task_end = ?", (id_start, id_end,))

        s.delete_task(id_start)
        s.delete_task(id_end)

        TaskScheduler.__DB_conn__.commit()

        s.__end_interval_task__(id_start, id_end)
        s.__cache_intervals__ = s.get_interval_tasks()

    def get_interval_tasks(s):
        return s.get_interval_tasks_where()

    def get_interval_tasks_where(s, action=None, args=None):
        interval_tasks = []
        for row in s.__db__.execute("SELECT * FROM interval_tasks").fetchall():
            task = {}

            task["start"] =  s.__db__.execute("SELECT * FROM tasks WHERE id=?", (row[ "id_task_start" ],)).fetchone()
            task["end"] =  s.__db__.execute("SELECT * FROM tasks WHERE id=?", (row[ "id_task_end" ],)).fetchone()

            task["start"]["time"] = time(hour=task["start"]["hour"], minute=task["start"]["minute"])
            task["end"]["time"] = time(hour=task["end"]["hour"], minute=task["end"]["minute"])

            if  (
                    not action or (int(task["start"]["action"]) == action or int(task["end"]["action"]) == action)
                ) and (
                    not args or (int(task["start"]["args"]) == args or int(task["end"]["args"]) == args)
                ):
                interval_tasks.append(task)

        return interval_tasks

    def get_tasks(s, use_time_object= True):
        query = "SELECT * FROM tasks WHERE id NOT IN (SELECT id_task_start FROM interval_tasks UNION SELECT id_task_end FROM interval_tasks)"
        tasks = []
        for task in s.__db__.execute(query).fetchall():
            if use_time_object:
                task["time"] = time(hour=task["hour"], minute=task["minute"])
                del task["hour"], task["minute"]
            tasks.append(task)

        return tasks


class Led:
    __pin__= 0

    def __init__(s, pin):
        s.__pin__ = pin

        IO.setmode(IO.BOARD)
        IO.setup(pin, IO.OUT)

    def on(s, delay=0):
        IO.output(s.__pin__, IO.HIGH)

    def off(s, delay=0):
        IO.utput(s.__pin__, IO.LOW)

    def blink(s, times=1, interval=1, delay=0):
        for i in xrange(times):
            s.on(delay)
            sleep(interval)
            s.off(delay)
            sleep(interval)


class RGBLed:
    __r__= 0
    __g__= 0
    __b__= 0

    def __init__(s, pin_r, pin_g, pin_b):
        s.__r__ = Led(pin_r)
        s.__g__ = Led(pin_g)
        s.__b__ = Led(pin_b)

    def on(s, delay=0):
        s.__r__.on(delay)
        s.__g__.on(delay)
        s.__b__.on(delay)

    def off(s, delay=0):
        s.__r__.off(delay)
        s.__g__.off(delay)
        s.__b__.off(delay)
        
    def blink(s, times=1, interval=1, delay=.5):
        s.__r__.blink(times, interval, delay)
        s.__g__.blink(times, interval, delay)
        s.__b__.blink(times, interval, delay)


class Relay:
    __pin__ = 0
    __normally_open__ = None
    __is_on__ = None

    __on_callback__ = None
    __off_callback__ = None
    __timeout_callback__ = None

    __on_off_timer__ = None
    __on_off_ticker__ = None
    __on_off_time__ = 0

    def __init__(s, pin, normally_open= True, start_on= False):
        s.__normally_open__ = normally_open
        s.__pin__ = pin

        IO.setmode(IO.BOARD)
        IO.setup(pin, IO.OUT)

        if start_on:
            s.__is_on__ = False
            s.on()
        else:
            s.__is_on__ = True
            s.off()

    def __tick__(s):
        s.__on_off_time__ -= 1
        if s.__on_off_time__ <= 0:
            s.__on_off_time__ = 0
            s.__on_off_ticker__.stop()

    def __timeout__(s):
        s.off()
        if s.__timeout_callback__: s.__timeout_callback__(s)

    def on(s):
        if not s.is_on():
            IO.output(s.__pin__, IO.HIGH if s.__normally_open__ else IO.LOW)
            s.__is_on__ = True
            if s.__on_callback__: s.__on_callback__()

    def off(s):
        if s.__on_off_timer__ != None:
            s.__on_off_timer__.cancel()
            s.__on_off_timer__ = None
            s.__on_off_time__ = 0

        if s.is_on():
            IO.output(s.__pin__, IO.LOW if s.__normally_open__ else IO.HIGH)
            s.__is_on__ = False
            if s.__off_callback__: s.__off_callback__()

    def is_on(s):
        return s.__is_on__

    def set_on_callback(s, func):
        s.__on_callback__ = func

    def set_off_callback(s, func):
        s.__off_callback__ = func

    def set_timeout_callback(s, func):
        s.__timeout_callback__ = func

    def on_off_timer(s, seconds):
        s.on()

        if s.__on_off_timer__ != None:
            s.__on_off_timer__.cancel()

        if s.__on_off_ticker__ == None:
            s.__on_off_ticker__ = SolidTimer(1, s.__tick__)

        s.__on_off_timer__ = Timer(seconds, s.__timeout__)
        s.__on_off_time__ = seconds

        s.__on_off_timer__.start()
        s.__on_off_ticker__.start()

    def get_countdown(s): return s.__on_off_time__

    def get_pin(s): return s.__pin__

class AutoRelay:
    __relay__= None
    __on_count__= 0
    __timer__= None
    __delay__= 0

    def __init__(s, pin, normally_open= True, start_on= False):
        s.__on_count__= 0
        s.__timer__= None
        s.__relay__= Relay(pin, normally_open, start_on)

    def __auto_on__(s):
        s.__on_count__ += 1

        if s.__timer__ != None:
            s.__timer__.cancel()
        s.__timer__ = Timer(s.__delay__, s.__relay__.on)
        s.__timer__.start()

    def __auto_off__(s):
        s.__on_count__ -= 1

        if s.__on_count__ == 0:
            if s.__timer__ != None:
                s.__timer__.cancel()
                s.__timer__ = None
            s.__relay__.off()

    def add_dependencies(s, relays, delay):
        s.__delay__ = delay
        for r in relays:
            r.set_on_callback(s.__auto_on__)
            r.set_off_callback(s.__auto_off__)


class StepperMotor:
    __PIN_A__ = None #L0 (RED)
    __PIN_B__ = None #L1 (ORANGE)
    __PIN_C__ = None #L2 (WHITE)
    __PIN_D__ = None #L3 (BLUE)

    __MIN_DELAY__= 0.005        #seconds
    __DEGREE_PER_STEP__ = 3.75  #degrees  
    __MIN_CURRENT_ANGLE__= 0    #degrees
    __MAX_CURRENT_ANGLE__= 0    #degrees
    __AUTOSTOP_INTERVAL__= 5    #seconds

    __STEPS__ = [
        [1,0,0,0],
        [1,1,0,0],
        [0,1,0,0],
        [0,1,1,0],
        [0,0,1,0],
        [0,0,1,1],
        [0,0,0,1],
        [1,0,0,1]
    ]
    __STOP_OUTPUT__= [0,0,0,0]

    __istep__= 0
    __current_angle__= 0

    __worker_thread__= None
    __work_signal_start__= None
    __work_signal_finish__= None
    
    __work_update_flag__= False
    __work_arg_degree__= 0
    __work_arg_time__= 0

    __stopped__ = False
    __stop_timer__= None
    

    def __init__(s, pin_a, pin_b, pin_c, pin_d, auto_stop= True):
        s.__PIN_A__= pin_a
        s.__PIN_B__= pin_b
        s.__PIN_C__= pin_c
        s.__PIN_D__= pin_d

        s.__worker_thread__= Thread(target=StepperMotor.__thread_work__, args=(s,))
        s.__work_signal_start__= Event()
        s.__work_signal_finish__= Event()

        s.__stop_timer__ = SolidTimer(s.__AUTOSTOP_INTERVAL__, StepperMotor.stop, args=[s]) if auto_stop else None

        s.__worker_thread__.setDaemon(True)
        s.__worker_thread__.start()

        IO.setmode(IO.BOARD)
        IO.setup(s.__PIN_A__, IO.OUT)
        IO.setup(s.__PIN_B__, IO.OUT)
        IO.setup(s.__PIN_C__, IO.OUT)
        IO.setup(s.__PIN_D__, IO.OUT)

        s.stop()

    def __setOutput__(s, step, delay):
        IO.output(s.__PIN_A__, step[0])
        IO.output(s.__PIN_B__, step[1])
        IO.output(s.__PIN_C__, step[2])
        IO.output(s.__PIN_D__, step[3])
        sleep(delay)

    def __thread_work__(s):
        istep= 0
        inc=0
        nsteps=0
        delay=0

        while True:
            s.__work_signal_start__.wait()

            s.start()
 
            while istep < nsteps or s.__work_update_flag__:
                if s.__work_update_flag__:
                    s.__work_update_flag__ = False
                    istep= 0

                    inc= 1 if s.__work_arg_degree__ >= 0 else -1
                    nsteps= abs(int(s.__work_arg_degree__/s.__DEGREE_PER_STEP__))
                    delay= max(s.__work_arg_time__/float(nsteps), s.__MIN_DELAY__) if nsteps else s.__MIN_DELAY__

                if nsteps:
                    s.__current_angle__+= inc*s.__DEGREE_PER_STEP__
                    if (not s.__MIN_CURRENT_ANGLE__ and not s.__MIN_CURRENT_ANGLE__) or (s.__MIN_CURRENT_ANGLE__ <= s.__current_angle__ and s.__current_angle__ <= s.__MAX_CURRENT_ANGLE__):
                        s.__current_angle__= s.__current_angle__%360 if s.__current_angle__ >= 0 else -(-s.__current_angle__%360)
                        s.__istep__= (s.__istep__+inc)%8
                        s.__setOutput__( s.__STEPS__[s.__istep__], delay )
                        istep+= 1
                    else:
                        s.__current_angle__-= inc*s.__DEGREE_PER_STEP__
                        s.__current_angle__= s.__current_angle__%360 if s.__current_angle__ >= 0 else -(-s.__current_angle__%360)
                        istep= nsteps

                    #print s.__current_angle__
                
            s.__work_signal_start__.clear()
            s.__work_signal_finish__.set()

            if s.__stop_timer__: s.__stop_timer__.start()
   
    def setup(s, steps_per_cycle=96, min_pulse_delay= 0.005):
        s.__DEGREE_PER_STEP__ = 360.0/steps_per_cycle
        s.__MIN_DELAY__ = min_pulse_delay

    def stop(s):
        if not s.__stopped__:
            s.__stopped__= True

            IO.setwarnings(False)
            s.__setOutput__(s.__STOP_OUTPUT__,0)
            IO.setwarnings(True)

            if s.__stop_timer__: s.__stop_timer__.stop()

    def start(s):
        if s.__stop_timer__: s.__stop_timer__.stop()
        if s.__stopped__:
            s.__stopped__= False

    def isStopped(s): return s.__stopped__

    def limit_angles(s, lower_limit, upper_limit):
        s.__MIN_CURRENT_ANGLE__ = lower_limit
        s.__MAX_CURRENT_ANGLE__ = upper_limit

    def turn(s, degree, time):
        inc= 1 if degree >= 0 else -1
        nsteps= abs(int(degree/s.__DEGREE_PER_STEP__))
        if not nsteps: return
        delay= max(time/float(nsteps), s.__MIN_DELAY__)

        s.start()

        for _ in xrange(0, nsteps):
            s.__current_angle__+= inc*s.__DEGREE_PER_STEP__
            if (not s.__MIN_CURRENT_ANGLE__ and not s.__MIN_CURRENT_ANGLE__) or (s.__MIN_CURRENT_ANGLE__ <= s.__current_angle__ and s.__current_angle__ <= s.__MAX_CURRENT_ANGLE__):
                s.__current_angle__= s.__current_angle__%360 if s.__current_angle__ >= 0 else -(-s.__current_angle__%360)
                s.__istep__= (s.__istep__+inc)%8
                s.__setOutput__( s.__STEPS__[s.__istep__], delay )
            else:
                s.__current_angle__-= inc*s.__DEGREE_PER_STEP__
                s.__current_angle__= s.__current_angle__%360 if s.__current_angle__ >= 0 else -(-s.__current_angle__%360)
                break
        
        if s.__stop_timer__: s.__stop_timer__.start()
        

    def turn_to_angle(s, angle, time): s.turn( (angle%360 if angle >= 0 else -(-angle%360)) - s.__current_angle__, time)

    def turn_async(s, degree, time):
        s.__work_arg_degree__= degree
        s.__work_arg_time__= time
        s.__work_update_flag__= True

        s.__work_signal_finish__.clear()
        if not s.__work_signal_start__.is_set():
            s.__work_signal_start__.set()

    def turn_to_angle_async(s, angle, time): s.turn_async( (angle%360 if angle >= 0 else -(-angle%360)) - s.__current_angle__, time)

    def wait_until_finish_turning(s): s.__work_signal_finish__.wait()


def cleanup():
    IO.cleanup()
