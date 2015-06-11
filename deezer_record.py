#!/usr/bin/env python
# -*- coding: utf8 -*-
# All strings are unicode (even docstrings)
from __future__ import unicode_literals

import sys
import time
import subprocess
import threading
import re

CHROME_ID = sys.argv[1]
CHROME_NAME_REGEX = re.compile('(?P<title>.*?) - (?P<artist>.*?) - Google Chrome')
XPROP_NAME_REGEX = re.compile('^WM_NAME.*"(.*)"$', re.M)

def get_chrome_name():
    xprop_output = unicode(subprocess.check_output("/usr/bin/xprop -id {}".format(CHROME_ID), shell=True), errors='ignore')
    return XPROP_NAME_REGEX.search(xprop_output).group(1)

class FileCleaner(threading.Thread):

    def __init__(self, file, title, artist):
        self.title = title
        self.artist = artist
        self.file = file
        threading.Thread.__init__(self)

    def run(self):
        self.rename_file()
        self.set_id3_tags()

    def rename_file(self):
        self.newfile = "{}-{}.mp3".format(self.artist, self.title).replace("/", "-")
        subprocess.call(
            "mv {} \"{}\"".format(self.file, self.newfile),
            shell=True
        )

    def set_id3_tags(self):
        subprocess.call(
            ["/usr/bin/id3v2",
            "--artist", self.artist,
            "--song", self.title,
            self.newfile]
        )

def record_a_song(current_name, lame_stdin):
    filename = str(time.time())
    lame_process = subprocess.Popen(
        ["/usr/bin/lame", "-r", "-s", "44.1", "-m", "j", "-h", "-", filename],
        stdin=lame_stdin
    )

    current_name_matching = CHROME_NAME_REGEX.match(current_name)
    title = current_name_matching.group('title')
    artist = current_name_matching.group('artist')
    print("Recording : '{}' from '{}'".format(title, artist))
    #time.sleep(10)
    cleaner = FileCleaner(filename, title, artist)

    while current_name == get_chrome_name():
        time.sleep(0.05)

    lame_process.kill()
    cleaner.start()
    return get_chrome_name()

def main():
    initial_name = get_chrome_name()
    current_name = get_chrome_name()

    print("Recording until name become: '{}' another time.".format(initial_name))
    arecord_process = subprocess.Popen(
        ["/usr/bin/arecord", "-f", "cd", "-t", "raw", "-D", "pulse_monitor"],
        stdout=subprocess.PIPE
    )

    current_name = record_a_song(current_name, arecord_process.stdout)
    while current_name != initial_name:
        current_name = record_a_song(current_name, arecord_process.stdout)

    arecord_process.kill()

if __name__ == "__main__":
    print("Deezer recording : Welcome")
    main()
    print("Deezer recording : Bye")
