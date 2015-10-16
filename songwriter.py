#!/usr/bin/env python3
"""
Implementation of the thread writing raw data on disk with right name
"""

import io
import time
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

def find_longest_silence(data, previous_result=None, threshold=0x0020, minimal_length=0.05):
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

        with io.open("{}.raw".format(file_name), 'wb') as output_file:
            logging.info("Writing '%s.raw' on disk", file_name)
            # Copy main part of the song (90%)
            with self.raw_data_lock:
                len_available_raw_data = len(self.raw_data)
            main_part_length = round_on_sample(int((length*0.9)*one_second_samples_num))
            # Wait until sufficiently data are loaded
            while len_available_raw_data < main_part_length:
                time.sleep(1)
                with self.raw_data_lock:
                    len_available_raw_data = len(self.raw_data)

            with self.raw_data_lock:
                output_file.write(bytes(self.raw_data[0:main_part_length]))
                del self.raw_data[0:main_part_length]
                len_available_raw_data = len(self.raw_data)

            logging.debug(
                "Copied %s seconds on %s",
                output_file.tell()/one_second_samples_num,
                length
            )

            # Read more samples until a gap is detected
            with self.raw_data_lock:
                len_available_raw_data = len(self.raw_data)
            silence = find_longest_silence(lasting_raw_data)
            while (not silence['found']) and len_available_raw_data > len(lasting_raw_data):
                # Make sure that the next song has actually started before looking for a gap
                time.sleep(5)
                with self.raw_data_lock:
                    lasting_raw_data.extend(
                        self.raw_data[
                            len(lasting_raw_data):
                            len(lasting_raw_data)+(5*one_second_samples_num)
                            ])
                    len_available_raw_data = len(self.raw_data)
                logging.debug(
                    "No silence found. More bytes read (%s / %s)",
                    len(lasting_raw_data), len_available_raw_data)
                silence = find_longest_silence(lasting_raw_data, silence)

            if not silence['found']:
                # No silence detected, we probably are at the end of the playlist,
                # write all data loaded
                logging.debug("No silence found. Write all availables data")
                breaking_byte = len(lasting_raw_data)
            else:
                breaking_byte = silence['longest_silence']['cut']
            # Write the end of the song
            output_file.write(bytes(lasting_raw_data[0:breaking_byte]))
            # Delete it from the raw_data
            with self.raw_data_lock:
                del self.raw_data[0:breaking_byte]

    def run(self):
        logging.info("Start barrier reached")
        self.synchronization['start'].wait()

        while not (
                self.synchronization['end'].is_set() and
                self.synchronization['tasks'].empty()):
            task = self.synchronization['tasks'].get()
            self.write_data(task['id'], task['length'])

            logging.info("Calling encode to convert %s", task['id'])
            self.encoder.encode(
                task['id'],
                task['infos'])
            self.synchronization['tasks'].task_done()

        logging.info("End Event Set")
        logging.info("Exit")
