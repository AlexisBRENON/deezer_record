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

from .pulseaudiomanager import PulseAudioManager
from .appinspector import PollAppInspector, NotifyAppInspector
from .streamloader import StreamLoader
from .songwriter import SongWriter
from .encoder import Mp3LameEncoder, FlacEncoder

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
        "--encoder",
        help="Choose which encoder to use. (Activate FLAC encoder for the moment...)",
        action="store_const",
        default=Mp3LameEncoder,
        const=FlacEncoder
    )
    arg_parser.add_argument(
        "--poll",
        help="Use polling for window title change detection",
        action="store_const",
        default=NotifyAppInspector,
        const=PollAppInspector,
        dest="app_inspector"
    )
    arg_parser.add_argument(
        "--debug", "-d",
        help="Show debug info",
        action="store_const",
        default=logging.INFO,
        const=logging.DEBUG
    )
    arg_parser.add_argument(
        "--continuous", "-c",
        help="Record infinitely",
        action="store_true"
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
    start_barrier = threading.Barrier(4) # A barrier to synchronize thread
    end_event = threading.Event() # Event set when all data are processed
    task_queue = queue.Queue() # Thread safe queue for interprocess communication
    raw_data = list() # Container of the raw data ...
    raw_data_lock = threading.Lock() # ... and its lock
    audio_encoder = options.encoder()
    logging.info("Shared ressources initialized")

    # Create threads
    browser_recorder = PulseAudioManager(
        {
            'start': start_barrier,
            'end': end_event
        },
        parec_pipe_write_end)

    browser_inspector = options.app_inspector(
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
        },
        options.continuous)

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

    try:
        end_event.wait()
    except KeyboardInterrupt:
        end_event.set()

    browser_recorder.join()
    logging.info("%s joined", repr(browser_recorder))
    parec_pipe_write_end.close()

    stream_loader.join()
    logging.info("%s joined", repr(stream_loader))
    parec_pipe_read_end.close()

    browser_inspector.join()
    logging.info("%s joined", repr(browser_inspector))

    song_writer.join()
    logging.info("%s joined", repr(song_writer))

    logging.info("Exit")

if __name__ == "__main__":
    main()
