#!/usr/bin/env python
# -*- coding: utf8 -*-
# All strings are unicode (even docstrings)
from __future__ import unicode_literals

import sys
import struct

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
