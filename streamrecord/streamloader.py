#!/usr/bin/env python3
"""
Implementation of the thread loading the pipe content in script
"""

import threading
import logging

class StreamLoader(threading.Thread):
    """ Thread that load the data from the pipe. It one of the most important one to avoid data
    leaks. """
    def __init__(self, thread_synchronization, bin_stream_input, raw_data):
        """
        thread_synchronization: Dictionnary with start and end object for synchronization
        bin_stream_input: Reading end of the pipe where parec writes
        raw_data: Dictionnary with list and its lock
        """
        super(StreamLoader, self).__init__(name="Stream Loader")
        self.thread_start = thread_synchronization['start']
        self.thread_end = thread_synchronization['end']
        self.bin_stream_input = bin_stream_input
        self.raw_data = raw_data['raw_data']
        self.raw_data_lock = raw_data['lock']
        logging.debug(self)

    def __str__(self):
        me = {}
        me["thread_start"] = repr(self.thread_start)
        me["thread_end"] = repr(self.thread_end)
        me["stream_input"] = repr(self.bin_stream_input)
        me["raw_data"] = repr(self.raw_data)
        me["raw_data_lock"] = repr(self.raw_data_lock)
        import json
        return "{}({}){}".format(self.name, self.ident, json.dumps(me))

    def run(self):
        bytes_to_read = int((44100/10) * 2 * 2)
        logging.info("Start barrier reached")
        self.thread_start.wait()
        while not self.thread_end.is_set():
            data = self.bin_stream_input.read(bytes_to_read)
            with self.raw_data_lock:
                self.raw_data.extend(data)
        self.thread_end.wait()
        logging.info("End event set")
        logging.info("Exit")
