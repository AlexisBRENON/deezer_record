#!/usr/bin/env python3
# -*- coding: utf8 -*-
# All strings are unicode (even docstrings)
from __future__ import unicode_literals

import sys
import struct
import io
import pdb

def hex_dump():
    str_data = sys.stdin.read(44100*2)
    data = [ord(i) for i in str_data]
    index = 0
    new_data=[]
    while index <= len(data)-2:
        #new_data.append((data[index+1]<<8)+data[index])
        new_data.append((struct.unpack("H", str_data[index:index+2])[0], struct.unpack("h", str_data[index:index+2])[0]))
        index = index + 2

    new_data = list(set(new_data))
    new_data.sort()

    for value in new_data:
        print("({:04x}, {:04x})".format(value[0], value[1]))
        pass

def find_longest_silence(samples):
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
        sample_value = struct.unpack("hh", samples[index:index+4])
        if abs(sample_value[0]) < 0x20 and abs(sample_value[1]) < 0x20:
            if not in_silence:
                in_silence = True
                current_silence['begin'] = index
        else:
            if in_silence:
                current_silence['end'] = index - 4
                in_silence = False
                current_silence['length'] = current_silence['end'] - current_silence['begin']
                if current_silence['length'] > minimal_length and current_silence['length'] > longest_silence['length']:
                    longest_silence = current_silence.copy()
        index = index+4

    if longest_silence['length'] > 0:
        if not in_silence:
            # Assert that the cut index is on a whole sample
            longest_silence['length'] = (int(longest_silence['length']/8))*8
            longest_silence['cut'] = int(longest_silence['begin'] + longest_silence['length']/2)
        return longest_silence
    else:
        return None

if __name__ == "__main__":
    input_file = io.open("big_break.raw", 'rb')
    new_data = input_file.read(44100*4)
    data = b''
    index = 0
    while len(new_data) > 0:
        data += new_data
        print("index : %d" % (index/4))
        print("Adding %d samples" % (len(new_data)/4))
        print("%d samples to analyze" % (len(data)/4))
        silence = find_longest_silence(data)
        if silence:
            if 'cut' in silence:
                breaking_sample = silence['cut']
                print("Break found :")
                print(silence)
                index += len(data)
                data = b''
            else:
                index += silence['begin']
                data = bytes(data[silence['begin']:])
        else:
            index += len(data)
            data = b''
        new_data = input_file.read(44100*4)
