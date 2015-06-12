#!/usr/bin/env python
# -*- coding: utf8 -*-
# All strings are unicode (even docstrings)
from __future__ import unicode_literals

import sys
import time
import io
import struct
import subprocess
import re
import my_getopt as getopt

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

def get_x_win_name(winid):
    xwininfo_process = subprocess.Popen(
        ["/usr/bin/xprop", "-id", winid, "WM_NAME"],
        stdout=subprocess.PIPE
        )
    return xwininfo_process.communicate()[0].decode()

def get_x_win_id():
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
    print("Please select an option :")
    for index, choice in choice_list.items():
        print("\t{}) {}".format(index, choice))
    choice = int(input("-> "))
    while not choice in choice_list:
        print("Invalid value")
        choice = int(input("-> "))

    return choice

def move_sink_input():
    print("Let's play your application...")
    _ = input("Then press Enter")
    pacmd_process = subprocess.Popen(
        ["/usr/bin/pacmd", "list-sink-inputs"],
        stdout=subprocess.PIPE
    )
    sink_inputs = {}
    for line in pacmd_process.stdout:
        line = line.decode()
        sink_index = re.search("^\s*index: (.*)", line)
        if sink_index:
            for line in pacmd_process.stdout:
                line = line.decode()
                app_name = re.search("^\s*application.name = \"(.*)\"", line)
                if app_name:
                    sink_inputs[int(sink_index.group(1))] = app_name.group(1)
                    break

    if len(sink_inputs.keys()) == 1:
        sink_input = list(sink_inputs.keys())[0]
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
    silence_length = 4
    silence_begin_index = len(samples)
    silence_end_index = 0
    index = 0
    while index <= len(samples)-4:
        sample_value = struct.unpack("hh", samples[index:index+4])[0]
        if abs(sample_value) < 0x0020 and silence_begin_index > index:
            silence_begin_index = index
        else:
            silence_end_index = index
            if silence_begin_index < silence_end_index:
                if (silence_end_index - silence_begin_index) >= silence_length:
                    silence_length = (silence_end_index - silence_begin_index)
                else:
                    silence_begin_index = len(samples)
        index = index+4

    if silence_length > 0:
        return int(silence_begin_index + silence_length/2)
    else:
        return None

def record_a_song(data, bin_stream_input, win_id, title_regex):

    num_sample = int((44100*4)/2)

    win_current_name = get_x_win_name(win_id)
    current_name_matching = title_regex.search(win_current_name)
    title = current_name_matching.group('title')
    artist = current_name_matching.group('artist')
    file_name = "{}-{}".format(artist, title).replace("/", "-")

    print("Recording {} from {}".format(title, artist))

    raw_file = io.open("{}.raw".format(file_name), "wb")
    while True:
        data = bin_stream_input.read(num_sample)
        while len(data) < num_sample:
            data += bin_stream_input.read(num_sample)

        breaking_sample = has_silence(data)
        if breaking_sample:
            if win_current_name != get_x_win_name(win_id):
                # The song has changed
                raw_file.write(data[:breaking_sample])
                raw_file.close()
                break
            else:
                raw_file.write(data)
                data = []
        else:
            raw_file.write(data)
            data = []
    
    encode(file_name)
    tag(file_name, title, artist)
    return data[breaking_sample:]

def encode(file_name):
    lame_process = subprocess.Popen(
        ["/usr/bin/lame", "-r",
            "-s", "44.1",
            "-m", "j",
            "-h",
            "{}.raw".format(file_name),
            "{}.mp3".format(file_name)]
    )
    lame_process.wait()
    subprocess.call(
        ["/bin/rm", "{}.raw".format(file_name)]
    )

def tag(file_name, title, artist):
    subprocess.call(
        ["/usr/bin/id3v2",
        "--artist", artist,
        "--song", title,
        "{}.mp3".format(file_name)]
    )

def main():
    options = getopt.parse_opt(sys.argv, OPTIONS)
    options['title_regex'] = re.compile(options['title_regex'])
    if not options['winid']:
        options['winid'] = get_x_win_id()

    sink_input = move_sink_input()

    try:
        parec_process = launch_record()
        time.sleep(1)
        initial_name = get_x_win_name(options['winid'])
        initial_recorded = False

        data = ''
        while initial_recorded == False:
            data = record_a_song(
                data,
                parec_process.stdout,
                options['winid'],
                options['title_regex'])

            initial_recorded = (initial_name == get_x_win_name(options['winid']))

        record_a_song(
            data,
            parec_process.stdout,
            options['winid'],
            options['title_regex'])

        parec_process.kill()

    finally:
        reset_sink_input(sink_input)

if __name__ == "__main__":
    print("Deezer recording : Welcome\n")
    main()
    print("\nDeezer recording : Bye")
