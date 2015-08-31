#!/usr/bin/env python3
"""
Implementation of the thread writing raw data on disk with right name
"""

import threading
import logging


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
        # Copy main part of the song -- until about the last 2 seconds
        while copied_length < song_length - 2:
            with self.raw_data_lock:
                one_second_data = self.raw_data[0:one_second_samples_num]
                del self.raw_data[0:one_second_samples_num]
                available_raw_data = len(self.raw_data)
            self.output_raw_file.write(bytes(one_second_data))
            copied_length += 1
        logging.debug("Copied %s seconds on %s", copied_length, song_length)

# about 2 seconds of song is resting in raw_data
# Read at least 3 seconds to detect a silence
        lasting_raw_data = []
        while len(lasting_raw_data) < 3*one_second_samples_num and available_raw_data > len(lasting_raw_data):
            with self.raw_data_lock:
                available_raw_data = len(self.raw_data)
                lasting_raw_data.extend(
                    self.raw_data[
                        len(lasting_raw_data):
                        len(lasting_raw_data)+one_second_samples_num
                        ])
            logging.debug("%s bytes read from %s bytes availables", len(lasting_raw_data), available_raw_data)
        silence = find_longest_silence(lasting_raw_data)
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
