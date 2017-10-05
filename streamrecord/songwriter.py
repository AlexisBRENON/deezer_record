#!/usr/bin/env python3
"""
Implementation of the thread writing raw data on disk with right name
"""

import io
import math
import time
import queue
import struct
import logging
import threading

def round_on_sample(byte_index, channels=2, channel_bytes_width=2):
    """
    Given a byte_index, return a smaller index witch match a whole sample.
    Sample parameters can be tuned giving the number of channels and the width
    of a channel in byte.
    """
    byte_index = int(byte_index)
    while byte_index % (channels*channel_bytes_width) != 0:
        byte_index -= 1
    return byte_index

def find_longest_silence(data, previous_result=None, threshold=0x0010, minimal_length=0.1):
    """ find the longest silence in a raw stream.
        previous_result: Result returns from the previous call. This allow the function to start
        from the last point instead of computing same silences many times.
        threshold: minimal absolute value of a sample under which you consider it's a silence
        minimal_length: minimal length in seconds of a silence to detect
        returns A dictionnary with 'found' and 'longest_silence' keys
    """
    minimal_length = (44100 * 2 * 2) * minimal_length
    if not previous_result:
        current_silence = {
            'begin': None,
            'end': None,
            }
        longest_silence = current_silence.copy() # Longest silence found
        longest_silence['length'] = 0
        in_silence = False # Indicator if we still are in a silence
        index = 0 # Loop index
    else:
        current_silence = previous_result['current_silence']
        longest_silence = previous_result['longest_silence']
        in_silence = previous_result['state']['in_silence']
        index = previous_result['state']['index']

    while index <= len(data)-4:
        # 1 sample is 4 bytes (2 2-bytes channels)
        sample_values = struct.unpack("hh", bytes(data[index:index+4]))

        # Sample value is relative to zero (positive or negative)
        # We consider a silence if sample value is under 0x0020 (over 0xFFFF)
        # TODO: make test to discover the best threshold
        if abs(sample_values[0]) < threshold and abs(sample_values[1]) < threshold:
            # If we're not in a silence, update values accordingly
            if not in_silence:
                in_silence = True
                current_silence['begin'] = index
            # Else, nothing to do, we're still in a silence

        # We're not in a silence
        else:
            # If it's the end of a silence
            if in_silence:
                current_silence['end'] = index
                in_silence = False
                current_silence['length'] = current_silence['end'] - current_silence['begin']
                # Does the silence is notable (sufficient length) and longer than the longest
                if (current_silence['length'] > minimal_length and
                        current_silence['length'] > longest_silence['length']):
                    longest_silence = current_silence.copy()
        index = index+4

    # We ran over all available data
    # If we found a silence with a sufficient length
    # and that we're not still in a silence (witch run on more data not fetched)
    if longest_silence['length'] > 0 and not in_silence:
        # Assert that the cut index is on a whole sample
        longest_silence['length'] = round_on_sample(longest_silence['length'])
        longest_silence['cut'] = round_on_sample(
            longest_silence['begin'] +
            longest_silence['length']/2
        )
        result = {'found': True}
    else:
        result = {'found': False}

    result['state'] = {
        'index': index,
        'in_silence': in_silence
        }
    result['longest_silence'] = longest_silence
    result['current_silence'] = current_silence
    return result

def find_breaking_byte(raw_data, minimal_length=0.1):
    raw_data = list(reversed(raw_data)) # Start from the end of the data
    one_second_samples_num = 2 * 2 * 44100 # Number of bytes in one second
    window_width = (minimal_length * one_second_samples_num)
    number_of_windows = int(2*(math.ceil(len(raw_data) / window_width)))
    signal_power = []

    for i in range(0, number_of_windows):
        window_start = int(math.floor(i * (window_width/2)))
        window_end = int(math.ceil(window_start + window_width))
        signal_power.append(sum([
            math.pow(x, 2) for x in raw_data[window_start:window_end]
        ]) / window_width)

    # TODO: do some recursive research with smaller window width

    minimal_signal_power = min(signal_power)
    break_start = None
    break_end = None
    for i, power in enumerate(signal_power):
        if power == minimal_signal_power:
            break_start = i if break_start is None else break_start
            break_end = i if (break_end is None or break_end == i-1) else break_end
        else:
            if break_start is not None and break_end is not None and break_end != i-1:
                break

    break_start = break_start * (window_width/2)
    break_end = break_end * (window_width/2) + window_width
    break_start = len(raw_data)-(break_start+1)
    break_end = len(raw_data)-(break_end+1)
    breaking_byte = round_on_sample(int(round((break_start + break_end)/2)))

    return breaking_byte

class SongWriter(threading.Thread):
    """
    This class read raw data, detect the gap and write it to a file in raw.
    Then it start an encoder to convert it to MP3
    """
    def __init__(self, synchronization, data, encoder):
        super(SongWriter, self).__init__(name="Song Writer")
        self.synchronization = synchronization
        self.raw_data = data['raw_data']
        self.raw_data_lock = data['lock']
        self.encoder = encoder
        logging.debug(self)

    def __str__(self):
        me = {}
        me["synchronization"] = repr(self.synchronization)
        me["raw_data"] = repr(self.raw_data)
        me["raw_data_lock"] = repr(self.raw_data_lock)
        me["encoder"] = repr(self.encoder)
        import json
        return "{}({}){}".format(self.name, self.ident, json.dumps(me))

    def write_data(self, file_name, length):
        """ Write data for ONE song on disk as raw.
        file_name: basename (without extension) of the file which is going to be created
        length: approximated length, in seconds, of the song recorded
        """
        one_second_samples_num = 2 * 2 * 44100 # Number of bytes in one second
        len_available_raw_data = 0 # Number of bytes available in raw_data
        lasting_raw_data = [] # Copy of a part of raw_data which must contain the end of the song
        silence = None # Inter-track gap information
        breaking_byte = None # Index of byte on which to cut the raw stream
        wrote_length = 0.0 # Actual length wrote on disk (in seconds with decimal part)

        with io.open("{}.raw".format(file_name), 'wb') as output_file:
            logging.info("Writing '%s.raw' on disk", file_name)
            # Song length precision is 1 second.
            # Copy the song except the last 2 seconds of data (2 times the precision)
            main_part_length = round_on_sample(int((length-2)*one_second_samples_num))
            with self.raw_data_lock:
                len_available_raw_data = len(self.raw_data)
            logging.debug("Available samples : %d", len_available_raw_data)
            logging.debug("Main part length : %d", main_part_length)
            # Wait until sufficiently data are loaded
            while len_available_raw_data < main_part_length:
                logging.debug("Sleep 1 second...")
                time.sleep(1)
                with self.raw_data_lock:
                    len_available_raw_data = len(self.raw_data)
                logging.debug("Available samples : %d", len_available_raw_data)
                logging.debug("Main part length : %d", main_part_length)

            # Actually write main part on disk
            with self.raw_data_lock:
                output_file.write(bytes(self.raw_data[0:main_part_length]))
                del self.raw_data[0:main_part_length]
                len_available_raw_data = len(self.raw_data)

            logging.debug(
                "Copied %s seconds on %s",
                output_file.tell()/one_second_samples_num,
                length
            )

            # Wait for the remaining data of the song
            while (
                len_available_raw_data < 2*one_second_samples_num and
                not self.synchronization['end'].is_set()
                ):
                time.sleep(1)
                with self.raw_data_lock:
                    len_available_raw_data = len(self.raw_data)

            with self.raw_data_lock:
                lasting_raw_data = list(self.raw_data[0:2*one_second_samples_num])
            if self.synchronization['end'].is_set():
                breaking_byte = len(lasting_raw_data)
            else:
                breaking_byte = find_breaking_byte(lasting_raw_data)

            # Write the end of the song
            output_file.write(bytes(lasting_raw_data[0:breaking_byte]))
            # Delete it from the raw_data
            with self.raw_data_lock:
                del self.raw_data[0:breaking_byte]

            wrote_length = output_file.tell()/one_second_samples_num

        return wrote_length

    def run(self):
        task = None
        remaining_length = 0
        logging.info("Start barrier reached")
        self.synchronization['start'].wait()

        while not (
                self.synchronization['end'].is_set() and
                self.synchronization['tasks'].empty()):
            while task is None:
                try:
                    task = self.synchronization['tasks'].get(timeout=10)
                except queue.Empty:
                    if self.synchronization['end'].is_set():
                        break
                    else:
                        pass
            if task is not None:
                logging.debug("Task measured length: %s s", task['length'])
                logging.debug("Task computed length: %s s", task['length'] + remaining_length)
                wrote_length = self.write_data(task['id'], task['length'] + remaining_length)
                remaining_length = task['length'] - wrote_length
                logging.debug("Task wrote length: %s s", wrote_length)
                logging.debug("Task remaining length: %s s", remaining_length)

                logging.info("Calling encode to convert %s", task['id'])
                self.encoder.encode(
                    task['id'],
                    task['infos'])
                self.synchronization['tasks'].task_done()
                task = None

        logging.info("End Event Set")
        logging.info("Exit")
