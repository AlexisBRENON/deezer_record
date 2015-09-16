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


class PulseAudioManager(threading.Thread):
    """ PulseAudio manager class that load required module, move sinks
    and restore everything at the end."""
    def __init__(self, start_barrier, end_event, parec_output_pipe):
        """ Create a new PulseAudio Manager
        start_barrier Barrier which synchronize the start of all threads
        end_barrier Not used for the moment
        parec_output_pipe Writing end of a pipe where the parec output will
            be redirected.
        """
        super(PulseAudioManager, self).__init__()
        self.start_barrier = start_barrier
        self.end_event = end_event
        self.parec_process = None
        self.parec_output_pipe = parec_output_pipe
        self.sink_input = None
        self.module_id = None


    def move_sink_input(self):
        """ Let's the user choose a sink to move to the recorder """
        def _parse_sink_inputs():
            """ Read PA output to list all available sinks """
            sink_inputs = {}
            pacmd_process = subprocess.Popen(
                ["/usr/bin/pacmd", "list-sink-inputs"],
                stdout=subprocess.PIPE
            )
            for line in pacmd_process.stdout:
                line = line.decode()
                sink_index = re.search(r"^\s*index: (.*)", line)
                if sink_index:
                    for line in pacmd_process.stdout:
                        line = line.decode()
                        app_name = re.search(r"^\s*application.name = \"(.*)\"", line)
                        if app_name:
                            sink_inputs[int(sink_index.group(1))] = app_name.group(1)
                            break
            return sink_inputs

        # Find which input need to be moved
        print("Let's play your application... Then press Enter.")
        _ = input()
        sink_inputs = _parse_sink_inputs()
        if len(sink_inputs.keys()) == 1:
            self.sink_input = list(sink_inputs.keys())[0]
        else:
            self.sink_input = select(sink_inputs)

        # Load the null module
        self.module_id = int(subprocess.check_output(
            ["/usr/bin/pactl", "load-module", "module-null-sink", "sink_name=deezer_record"]
        ))

        # Move the sink input
        subprocess.call(
            ["/usr/bin/pactl", "move-sink-input", str(self.sink_input), "deezer_record"]
        )

    def reset_sink_input(self):
        """ Reset the PA configuration to its initial state """
        logging.debug("Reset sink input to its right sink")
        subprocess.call(
            ["/usr/bin/pactl", "move-sink-input", str(self.sink_input), "1"]
        )
        logging.debug("Unload NULL module")
        subprocess.call(
            ["/usr/bin/pactl", "unload-module", str(self.module_id)]
        )

    def launch_parec(self):
        """ Actually launch the record of the moved sink """
        self.parec_process = subprocess.Popen(
            ["/usr/bin/parec", "-d", "deezer_record.monitor"],
            stdout=self.parec_output_pipe
        )

    def stop_parec(self):
        """ Stop recording of the stream """
        self.parec_process.terminate()

    def run(self):
        self.move_sink_input()
        logging.info("Start barrier reached")
        self.start_barrier.wait()
        self.launch_parec()

        self.end_event.wait()
        logging.info("End event set")
        self.stop_parec()
        self.reset_sink_input()
        self.parec_output_pipe.close()
        logging.info("Exit")

class AppInspector(threading.Thread):
    """ Inspect the Application title to detect song change """
    def __init__(self, synchronization, data, x_info):
        super(AppInspector, self).__init__()
        self.start_barrier = synchronization['start_barrier']
        self.end_event = synchronization['end_event']
        self.data = data
        self.browser_x_winid = x_info['win_id']
        self.title_regex = x_info['title_regex']

    def get_x_win_title(self):
        """ Get the title of the application's window """
        xwininfo_process = subprocess.Popen(
            ["/usr/bin/xprop", "-id", self.browser_x_winid, "WM_NAME"],
            stdout=subprocess.PIPE
            )
        return xwininfo_process.communicate()[0].decode().split(" = ")[1].strip(" \n\"")

    def run(self):
        logging.info("Start barrier reached")
        self.start_barrier.wait()

        previous_time = time.time()
        initial_name = self.get_x_win_title()
        previous_name = initial_name
        recording_initial = False
        initial_fully_recorded = False
        last_thread = None

        logging.info("Initial song = '%s'", initial_name)
        while not initial_fully_recorded:
            time.sleep(1)
            current_name = self.get_x_win_title()
            # Song has changed
            if previous_name != current_name and self.title_regex.match(current_name):
                logging.info("Song changed => '%s'", current_name)
# We're back to the first song. Let's record it from the beginning
                if not recording_initial and current_name == initial_name:
                    logging.info("Re-recording initial song")
                    recording_initial = True
# Initial track has been fully measured, break the loop
                if recording_initial and current_name != initial_name:
                    logging.info("Initial song recorded. Quit the loop")
                    initial_fully_recorded = True
                new_time = time.time()
                last_thread = SongWriter(
                    self.data,
                    new_time - previous_time,
                    previous_name,
                    self.title_regex)
                logging.debug("Launching writer thread : %s", last_thread)
                last_thread.start()
                previous_time = new_time
                previous_name = current_name

# Stop all threads
        logging.info("Set end event")
        self.end_event.set()
        last_thread.join()
        logging.debug("%s joined", last_thread)
        logging.info("Exit")

class StreamLoader(threading.Thread):
    """ Thread that load the data from the pipe. It one of the most important one to avoid data
    leaks. """
    def __init__(self, start_barrier, end_event, bin_stream_input, raw_data, raw_data_lock):
        """
        start_barrier: Barrier to synchronize all the threads
        end_event: Event to stop all threads
        bin_stream_input: Reading end of the pipe where parec writes
        raw_data: Container for the read data
        raw_data_lock: Lock for raw_data access control
        """
        super(StreamLoader, self).__init__()
        self.start_barrier = start_barrier
        self.end_event = end_event
        self.bin_stream_input = bin_stream_input
        self.raw_data = raw_data
        self.raw_data_lock = raw_data_lock

    def run(self):
        bytes_to_read = int((44100/10) * 2 * 2)
        logging.info("Start barrier reached")
        self.start_barrier.wait()
        while not self.end_event.is_set():
            data = self.bin_stream_input.read(bytes_to_read)
            with self.raw_data_lock:
                self.raw_data.extend(data)
        self.end_event.wait()
        logging.info("End event set")
        logging.info("Exit")


class SongWriter(threading.Thread):
    """
    This class read raw data, detect the gap and write it to a file in raw.
    Then it start an encoder to convert it to MP3
    """
    def __init__(self, data, length_sec, window_title, title_regex):
        super(SongWriter, self).__init__()
        current_name_matching = title_regex.match(window_title)
        self.title = current_name_matching.group('title')[0:50]
        self.artist = current_name_matching.group('artist')[0:50]
# TODO: sanitize file name
        self.file_name = "{}-{}".format(self.artist, self.title).replace("/", "-")
        self.output_raw_file = io.open("%s.raw" % (self.file_name), 'wb')
        self.song_length = length_sec
        self.raw_data = data['raw_data']
        self.raw_data_lock = data['lock']

    def run(self):
        # 2 channels of 16 bits (2 bytes) each with 44100 samples per seconds
        one_second_samples_num = 2 * 2 * 44100
        song_length = self.song_length
        copied_length = 0
        available_raw_data = 0

        logging.info("Writing '%s.raw' on disk", self.file_name)
        # Copy main part of the song -- until about the last 10 seconds
        while copied_length < song_length - 10:
            with self.raw_data_lock:
                one_second_data = self.raw_data[0:one_second_samples_num]
                del self.raw_data[0:one_second_samples_num]
                available_raw_data = len(self.raw_data)
            self.output_raw_file.write(bytes(one_second_data))
            copied_length += 1
        logging.debug("Copied %s seconds on %s", copied_length, song_length)


        lasting_raw_data = []
        silence = None
# Read more samples until a gap is detected
        while (not silence) and available_raw_data > len(lasting_raw_data):
            with self.raw_data_lock:
                available_raw_data = len(self.raw_data)
                lasting_raw_data.extend(
                    self.raw_data[
                        len(lasting_raw_data):
                        len(lasting_raw_data)+one_second_samples_num
                        ])
            logging.debug("No silence. More bytes read (%s / %s)", len(lasting_raw_data), available_raw_data)
            silence = find_longest_silence(lasting_raw_data)

        # cut on the right sample
        breaking_sample = None
        if not silence:
            logging.debug("No silence found. Write all availables data")
            breaking_sample = len(lasting_raw_data)
        else:
            breaking_sample = silence['cut']
# Write the end of the song
        self.output_raw_file.write(bytes(lasting_raw_data[0:breaking_sample]))
# Delete it from the raw_data
        with self.raw_data_lock:
            del self.raw_data[0:breaking_sample]

        logging.info("Converting RAW to MP3 (%s)", self.file_name)
        encode(self.file_name, self.artist, self.title)
        logging.info("'%s.mp3' saved", self.file_name)
        logging.info("Exit")

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
    minimal_length = (44100/200)*4
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
    browser_recorder = PulseAudioManager(start_barrier, end_event, parec_pipe_write_end)

    browser_inspector = AppInspector(
        {
            'start_barrier': start_barrier,
            'end_event': end_event
        }, {
            'raw_data' : raw_data,
            'lock': raw_data_lock
        }, {
            'win_id': options.winid,
            'title_regex': title_regex
        })

    stream_loader = StreamLoader(
        start_barrier,
        end_event,
        parec_pipe_read_end,
        raw_data,
        raw_data_lock)

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
