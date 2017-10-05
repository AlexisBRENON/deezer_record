#!/usr/bin/env python3
"""
Implementation of the class watching the playing application
"""

import time
import select
import logging
import threading
import subprocess

import Xlib.display
import Xlib.X
import Xlib.Xatom

class AppInspector(threading.Thread):
    """ Inspect the Application title to detect song change """
    def __init__(self, synchronization, data, x_info, continuous=False):
        super(AppInspector, self).__init__(name="Application Inspector")
        self.thread_start = synchronization['start']
        self.thread_end = synchronization['end']
        self.task_queue = synchronization['tasks']
        self.data = data
        self.browser_x_winid = x_info['win_id']
        if isinstance(self.browser_x_winid, str):
            self.browser_x_winid = int(
                self.browser_x_winid,
                16)
        self.title_regex = x_info['title_regex']
        self.continuous = continuous

    def get_x_win_title(self):
        """ Get the title of the application's window """
        xwininfo_process = subprocess.Popen(
            ["/usr/bin/xprop",
            "-f", "WM_NAME", "0u",
            "-id", "0x{:X}".format(self.browser_x_winid),
            "WM_NAME"],
            stdout=subprocess.PIPE
            )
        return xwininfo_process.communicate()[0].decode().split(" = ")[1].strip(" \n\"")

    def detect_changes(self, previous_name, previous_time):
        raise NotImplementedError()

    def run(self):
        logging.info("Start barrier reached")
        self.thread_start.wait()

        previous_time = time.time()
        initial_name = self.get_x_win_title()
        previous_name = initial_name
        recording_initial = False
        initial_fully_recorded = False

        if not self.continuous:
            logging.info("Recording until '%s' plays another time", initial_name)
        else:
            logging.info("Recording infinitely")

        time.sleep(1)

        while ((self.continuous and not self.thread_end.is_set()) or
                (not self.continuous and (
                    not (initial_fully_recorded or self.thread_end.is_set())
                ))
            ):

            current_name, new_time = self.detect_changes(previous_name, previous_time)
            logging.info("Song changed => '%s'", current_name)

            # We're back to the first song. Let's record it from the beginning
            if not recording_initial and current_name == initial_name:
                logging.debug("Re-recording initial song")
                recording_initial = True
            # Initial track has been fully measured, break the loop
            if recording_initial and current_name != initial_name:
                logging.debug("Initial song recorded. Quit the loop")
                initial_fully_recorded = True

            matching = self.title_regex.match(previous_name)
            self.launch_task({
                'id': new_time,
                'length': new_time-previous_time,
                'infos': {
                    'title': matching.group('title'),
                    'artist': matching.group('artist')
                }
            })
            previous_time = new_time
            previous_name = current_name

        # Stop all threads
        logging.info("Set end event")
        self.thread_end.set()
        self.task_queue.join()
        logging.debug("%s joined", self.task_queue)
        logging.info("Exit")

    def launch_task(self, task):
        logging.debug("Adding a 'writing' task")
        self.task_queue.put(task)


class PollAppInspector(AppInspector):
    """ Detect title changes using a polling technique """

    def detect_changes(self, previous_name, previous_time):
        while True:
            current_name = self.get_x_win_title()
            # Song has changed
            if previous_name != current_name and self.title_regex.match(current_name):
                return current_name, time.time()
            else:
                time.sleep(1)

class NotifyAppInspector(AppInspector):
    """ Detect title changes subscribing to XServer events notification. """

    def __init__(self, *args, **kargs):
        super().__init__(*args, **kargs)
        self.display = Xlib.display.Display()
        self.window = self.display.create_resource_object(
            'window',
            self.browser_x_winid
        )

    def detect_changes(self, previous_name, previous_time):
        self.window.change_attributes(event_mask=Xlib.X.PropertyChangeMask)
        while True:
            event = self.display.next_event()
            if event.atom == Xlib.Xatom.WM_NAME:
                new_time = time.time()
                new_name = self.get_x_win_title()
                if new_name != previous_name:
                    self.window.change_attributes(event_mask=Xlib.X.NoEventMask)
                    return new_name, new_time
