#!/usr/bin/env python3
"""
This script allow you to record a audio stream from any application
and try to cut it on every song, based on the title of a window
(changing when song changes) and detecting a gap in the audio stream.
This script heavily relies on some Linux dependencies, like PulseAudio
or LAME.
It's first intended to work with Deezer, feel free to adapt it to your
needs!
"""

import os
import re
import queue
import logging
import argparse
import threading
import subprocess

from pulseaudiomanager import PulseAudioManager
from appinspector import AppInspector
from streamloader import StreamLoader
from songwriter import SongWriter
import encoder

def get_x_win_id():
    """ Ask the user to click on the window to record and returns its X id """
    print("Click on the player window...")
    xwininfo_process = subprocess.Popen(
        ["/usr/bin/xwininfo"],
        stdout=subprocess.PIPE
    )
    for line in xwininfo_process.stdout:
        line = line.decode()
        winid_matching = re.search("Window id: (0x[0-9a-f]*)", line, re.U)
        if winid_matching:
            return winid_matching.group(1)

def main():
    """ Main function, creating interprocess ressources, threads, and launching everything """
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument(
        "--id",
        help="X Window ID of the windows to record audio from",
        dest="winid"
    )
    arg_parser.add_argument(
        "--regex",
        default=r"(?P<title>.+) - (?P<artist>.+) - .*",
        help="Regex to extract artist and title from window title (default: %(default)s)",
    )
    arg_parser.add_argument(
        "--debug", "-d",
        help="Show debug info",
        action="store_const",
        default=logging.INFO,
        const=logging.DEBUG
    )
    options = arg_parser.parse_args()
    title_regex = re.compile(options.regex)
    if not options.winid:
        options.winid = get_x_win_id()

    logging.basicConfig(
        level=options.debug,
        format="## %(levelname)s ## %(threadName)s ## %(message)s"
    )
    logging.info("Options parsed")
    logging.debug("Debug output activated")

    # Create shared ressources
    parec_pipe_read_end, parec_pipe_write_end = os.pipe() # create a pipe
    parec_pipe_read_end = os.fdopen(parec_pipe_read_end, 'rb')
    parec_pipe_write_end = os.fdopen(parec_pipe_write_end, 'wb')
    start_barrier = threading.Barrier(3) # A barrier to synchronize thread
    end_event = threading.Event() # Event set when all data are processed
    task_queue = queue.Queue() # Thread safe queue for interprocess communication
    raw_data = list() # Container of the raw data ...
    raw_data_lock = threading.Lock() # ... and its lock
    audio_encoder = encoder.Mp3LameEncoder()
    logging.info("Shared ressources initialized")

    # Create threads
    browser_recorder = PulseAudioManager(
        {
            'start': start_barrier,
            'end': end_event
        },
        parec_pipe_write_end)

    browser_inspector = AppInspector(
        {
            'start': start_barrier,
            'tasks': task_queue,
            'end': end_event
        }, {
            'raw_data' : raw_data,
            'lock': raw_data_lock
        }, {
            'win_id': options.winid,
            'title_regex': title_regex
        })

    stream_loader = StreamLoader(
        {
            'start': start_barrier,
            'end': end_event
        },
        parec_pipe_read_end,
        {
            'raw_data' : raw_data,
            'lock': raw_data_lock
        })

    song_writer = SongWriter(
        {
            'start': start_barrier,
            'tasks': task_queue,
            'end': end_event
        }, {
            'raw_data' : raw_data,
            'lock': raw_data_lock
        },
        audio_encoder
        )

    logging.info("Threads initialized. Ready for launching")

    browser_recorder.start()
    browser_inspector.start()
    stream_loader.start()
    song_writer.start()

    stream_loader.join()
    logging.info("%s joined", stream_loader)
    browser_inspector.join()
    logging.info("%s joined", browser_inspector)
    browser_recorder.join()
    logging.info("%s joined", browser_recorder)
    song_writer.join()
    logging.info("%s joined", song_writer)
    logging.info("Exit")

if __name__ == "__main__":
    main()
