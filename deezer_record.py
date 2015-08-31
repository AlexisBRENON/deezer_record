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

import io
import os
import re
import time
import struct
import logging
import argparse
import threading
import subprocess

from pulseaudiomanager import PulseAudioManager
from appinspector import AppInspector
from streamloader import StreamLoader
from songwriter import SongWriter

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

def select(choice_list):
    """ Ask the user to select an option
    choice_list: The list of options
    return the index of the choice
    """
    print("Please select an option :")
    for index, choice in choice_list.items():
        print("\t{}) {}".format(index, choice))
    choice = int(input("-> "))
    while not choice in choice_list:
        print("Invalid value")
        choice = int(input("-> "))

    return choice


def find_longest_silence(samples):
    """ find the longest silence in a raw stream
    returns None if no silence is found or a dictionnary, with begin and end keys associated to the
    index of the beginning and ending samples; length key; cut indexing the sample where to cut. If
    cut is not present, you're currently in a silence, and more data are required
    """
    minimal_length = (44100/100)*4
    current_silence = {
        'begin': None,
        'end': None,
        }
    longest_silence = current_silence.copy()
    longest_silence['length'] = 0
    in_silence = False
    index = 0
    while index <= len(samples)-4:
        sample_value = struct.unpack("hh", bytes(samples[index:index+4]))
        if abs(sample_value[0]) < 0x20 and abs(sample_value[1]) < 0x20:
            if not in_silence:
                in_silence = True
                current_silence['begin'] = index
        else:
            if in_silence:
                current_silence['end'] = index - 4
                in_silence = False
                current_silence['length'] = current_silence['end'] - current_silence['begin']
                if (current_silence['length'] > minimal_length and
                        current_silence['length'] > longest_silence['length']):
                    longest_silence = current_silence.copy()
        index = index+4

    if not in_silence and longest_silence['length'] > 0:
        # Assert that the cut index is on a whole sample
        longest_silence['length'] = (int(longest_silence['length']/8))*8
        longest_silence['cut'] = int(longest_silence['begin'] + longest_silence['length']/2)
        return longest_silence
    else:
        return None

class Encoder:
    def __init__(self, type):
        self.type = type

    def encode(self, file_name, artist, title):
def encode(file_name, artist, title):
    """ Encode a raw file to MP3 and add some tag """
# TODO: add tags parameters
    lame_process = subprocess.Popen([
        "/usr/bin/lame", "-r",
        "-s", "44.1",
        "-m", "j",
        "-h",
        "--quiet",
        "--add-id3v2",
        "--ta", artist,
        "--tt", title,
        "{}.raw".format(file_name),
        "{}.mp3".format(file_name)
        ])
    lame_process.wait()
    subprocess.call(
        ["/bin/rm", "{}.raw".format(file_name)]
    )

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
    raw_data = list() # Container of the raw data ...
    raw_data_lock = threading.Lock() # ... and its lock
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

    logging.info("Threads initialized. Ready for launching")

    browser_recorder.start()
    browser_inspector.start()
    stream_loader.start()

    stream_loader.join()
    logging.info("%s joined", stream_loader)
    browser_inspector.join()
    logging.info("%s joined", browser_inspector)
    browser_recorder.join()
    logging.info("%s joined", browser_recorder)
    logging.info("Exit")

if __name__ == "__main__":
    main()
