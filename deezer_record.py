#!/usr/bin/env python
# -*- coding: utf8 -*-
# All strings are unicode (even docstrings)
from __future__ import unicode_literals

import sys
import getopt
import time
import io
import os
import struct
import subprocess
import threading
import re

OPTIONS = [
    {
        'name': 'help',
        'short': 'h',
        'long': 'help',
        'optional': True,
        'arg': False,
        'desc': "Print this usage message",
        'default': False
    },
    {
        'name': 'winid',
        'short': 'i',
        'long': 'winid',
        'optional': True,
        'arg': True,
        'desc': "X Window ID of the player window",
        'default': None
    },
    {
        'name': 'title_regex',
        'short': 'r',
        'long': 'regex',
        'optional': True,
        'arg': True,
        'desc': "Python Regex for window title parsing (with 'title' and 'artist' group)",
        'default': '"(?P<title>.*?) - (?P<artist>.*?) - Google Chrome"'
    }
]

def print_usage(cmd_name):
    """ Short usage output """
    usage_line = "Usage : %s" % (cmd_name)
    full_desc = ""
    for option in OPTIONS:
        if option['optional']:
            usage_line += ' ['
        usage_line += ' -%s' % option['short']
        if option['arg']:
            if option['default']:
                usage_line += ' %s' % option['default']
            else:
                usage_line += ' <%s>' % option['name']
        if option['optional']:
            usage_line += ' ]'
            full_desc += "\t-{short}, --{long} : {desc}\n".format(**option)

    print(usage_line)
    print(full_desc)

def parse_opt(argv):
    """ Parse options passed to the script and return a dictionnary with the
    options value. """
    options = {}
    getopt_options = {
        'short' : "",
        'long' : []
    }

    for option in OPTIONS:
        options[option['name']] = option['default']
        getopt_options['short'] += option['short']
        getopt_options['long'].append(option['long'])
        if option['arg']:
            getopt_options['short'] += ":"
            getopt_options['long'][-1] += "="

    try:
        opts, args = getopt.getopt(argv[1:], getopt_options['short'], getopt_options['long'])
    except getopt.GetoptError:
        sys.stderr.write('## ERROR ## Failed to parse options...\n')
        print_usage(argv[0])
        sys.exit(2)

    # There is some non-option arguments. Warn the user and continue
    if len(args) > 0:
        sys.stderr.write('## WARN  ## Some arguments are useless :\n')
        sys.stderr.write('%s\n' % (args))

    for opt, arg in opts:
        for option in OPTIONS:
            if opt in ("-%s" % option['short'], "--%s" % option['long']):
                if option['arg']:
                    # Option with argument
                    options[option['name']] = arg
                else:
                    # Boolean option
                    options[option['name']] = True
                break

    if options['help']:
        print_usage(argv[0])
        exit(0)

    # Check that the mandatory option is not empty
    for option in OPTIONS:
        if not option['optional'] and not options[option['name']]:
            sys.stderr.write('%s is a mandatory argument...\n\n' % option['name'])
            print_usage(argv[0])
            sys.exit(-1)

    return options

def get_x_win_name(winid):
    xwininfo_process = subprocess.Popen(
        ["/usr/bin/xprop", "-id", winid, "WM_NAME"],
        stdout=subprocess.PIPE
        )
    return unicode(xwininfo_process.communicate()[0], errors="ignore")

def get_x_win_id():
    print("Click on the player window...")
    xwininfo_process = subprocess.Popen(
        ["/usr/bin/xwininfo"],
        stdout=subprocess.PIPE
    )
    for line in xwininfo_process.stdout:
        winid_matching = re.search("Window id: (0x[0-9a-f]*)", line)
        if winid_matching:
            return unicode(winid_matching.group(1), errors="ignore")

def select(choice_list):
    print("Please select an option :")
    for index, choice in choice_list.iteritems():
        print("\t{}) {}".format(index, choice))
    choice = int(input("-> "))
    while not choice in choice_list:
        print("Invalid value")
        choice = int(input("-> "))

    return choice

def move_sink_input():
    print("Let's play your application...")
    _ = raw_input("Then press Enter")
    pacmd_process = subprocess.Popen(
        ["/usr/bin/pacmd", "list-sink-inputs"],
        stdout=subprocess.PIPE
    )
    sink_inputs = {}
    for line in pacmd_process.stdout:
        sink_index = re.search("^\s*index: (.*)", line)
        if sink_index:
            for line in pacmd_process.stdout:
                app_name = re.search("^\s*application.name = \"(.*)\"", line)
                if app_name:
                    sink_inputs[int(sink_index.group(1))] = app_name.group(1)
                    break

    if len(sink_inputs.keys()) == 1:
        sink_input = sink_inputs.keys()[0]
    else:
        sink_input = select(sink_inputs)
    module_id = int(subprocess.check_output(
        ["/usr/bin/pactl", "load-module", "module-null-sink", "sink_name=deezer_record"]
    ))
    subprocess.call(
        ["/usr/bin/pactl", "move-sink-input", str(sink_input), "deezer_record"]
    )
    return (module_id, sink_input)

def reset_sink_input(sink_config):
    subprocess.call(
        ["/usr/bin/pactl", "unload-module", str(sink_config[0])]
    )
    subprocess.call(
        ["/usr/bin/pactl", "move-sink-input", str(sink_config[1]), "1"]
    )

def launch_record():
    parec_process = subprocess.Popen(
        ["/usr/bin/parec", "-d", "deezer_record.monitor"],
        stdout=subprocess.PIPE
    )
    return parec_process

def has_silence(samples):
    print("looking for silence")
    # Silence is at least 0.1sec long
    silence_min_length = (44100/10)*4
    silence_begin_index = len(samples)
    silence_end_index = 0
    index = 0
    while index <= len(samples)-2:
        sample_value = struct.unpack("h", samples[index:index+2])[0]
        if abs(sample_value) < 0x0020 and silence_begin_index > index:
            silence_begin_index = index
        else:
            silence_end_index = index
            if silence_begin_index < silence_end_index:
                if (silence_end_index - silence_begin_index) >= silence_min_length:
                    return silence_begin_index + int((silence_end_index - silence_begin_index)/2)
                else:
                    silence_begin_index = len(samples)
        index = index+2
    return None


def main():
    options = parse_opt(sys.argv)
    options['title_regex'] = re.compile(options['title_regex'])
    if not options['winid']:
        options['winid'] = get_x_win_id()

    sink_input = move_sink_input()

    try:
        parec_process = launch_record()
        time.sleep(1)
        initial_name = get_x_win_name(options['winid'])
        initial_recorded = False

        num_sample = (44100/2)*4
        data = ''
        while initial_recorded == False:
            song_changed = False
            win_current_name = get_x_win_name(options['winid'])
            current_name_matching = options['title_regex'].search(win_current_name)
            title = current_name_matching.group('title')
            artist = current_name_matching.group('artist')
            file_name = "{}-{}".format(artist, title)
            raw_file = io.open("{}.raw".format(file_name), "wb")
            print("Recording {} from {}".format(title, artist))
            while not song_changed:

                data = parec_process.stdout.read(num_sample)
                while len(data) < num_sample:
                    data += parec_process.stdout.read(num_sample)

                breaking_sample = has_silence(data)
                if breaking_sample:
                    print("Silence discovered")
                    if win_current_name != get_x_win_name(options['winid']):
                        # The song has changed
                        raw_file.write(bytearray(data[:breaking_sample]))
                        data = data[breaking_sample:]
                        song_changed = True
                    else:
                        raw_file.write(bytearray(data))
                        data = []
                else:
                    raw_file.write(bytearray(data))
                    data = []

            raw_file.close()
            initial_recorded = (initial_name == record_thread.win_current_name)

    finally:
        reset_sink_input(sink_input)

class CleanerThread(threading.Thread):
    """Thread that squash, encode, and tag files"""
    def __init__(self, record_thread, title_regex, squash=True):
        super(CleanerThread, self).__init__()
        self.record_thread = record_thread
        self.title_regex = title_regex
        self.squash = squash
        self.raw_file_name = record_thread.raw_file_name

    def run(self):
        time.sleep(5)
        self.get_tag()

        self.record_thread.join()

        print("Cleaning '{}' to '{}'".format(self.raw_file_name, self.encoded_file_name))
        if self.squash:
            self.squash_file()
        self.encode()
        self.tag()

    def get_tag(self):
        win_current_name = self.record_thread.win_current_name
        current_name_matching = self.title_regex.search(win_current_name)
        self.title = current_name_matching.group('title')
        self.artist = current_name_matching.group('artist')
        self.encoded_file_name = "{}-{}.mp3".format(self.artist, self.title)

    def squash_file(self):
        pass

    def encode(self):
        lame_process = subprocess.Popen(
            ["/usr/bin/lame", "-r",
            "-s", "44.1",
            "-m", "j",
            "-h",
            self.raw_file_name, self.encoded_file_name]
        )
        lame_process.wait()
        subprocess.call(
            ["/bin/rm", self.raw_file_name]
        )

    def tag(self):
        subprocess.call(
            ["/usr/bin/id3v2",
            "--artist", self.artist,
            "--song", self.title,
            self.encoded_file_name]
        )

if __name__ == "__main__":
    print("Deezer recording : Welcome\n")
    main()
    print("\nDeezer recording : Bye")
