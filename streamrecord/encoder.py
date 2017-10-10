#!/usr/bin/env python3
"""
Implementation of different standard encoders
"""

import os
import subprocess

from slugify import slugify

class Encoder:
    """
    Encoder interface.
    An encoder must be able to encode raw data file to another format.
    """

    SUPPORTED_TAGS = {}

    @classmethod
    def get_filename(cls, infos):
        """
        Return a default file name from infos
        """
        if infos and infos['title'] and infos['artist']:
            filename = slugify(infos['artist'][0:50], separator="_")
            filename += "-"
            filename += slugify(infos['title'][0:50], separator="_")
            return filename

    def __init__(self, keep_raw=False):
        self.keep_raw = keep_raw

    def encode(self, basename, infos):
        """
        Encode the raw file at 'basename.raw' to 'basename.***'.
        """
        raise NotImplementedError

    def delete_raw(self, basename):
        """
        Remove raw file after encoding
        """
        if not self.keep_raw:
            subprocess.call(
                ["/bin/rm", "{}.raw".format(basename)]
            )

class DebugEncoder(Encoder):
    """
    Dummy encoder which only monitor calls. It is primarily used for test purpose.
    """

    def __init__(self):
        super(DebugEncoder, self).__init__()
        self.encoded = {}

    def encode(self, basename, infos):
        self.encoded[basename] = os.stat("{}.raw".format(basename))

    def clear(self):
        """
        Delete all raw files monitored by the encoder.
        """
        for basename in self.encoded:
            self.delete_raw(basename)
        self.encoded.clear()

class Mp3LameEncoder(Encoder):
    """
    MP3 Encoder implementation based on lame
    """
    SUPPORTED_TAGS = {
        "title": "--tt",
        "artist": "--ta",
        "album": "--tl",
        "year": "--ty",
        "comment": "--tc",
        "track": "--tn",
        "genre": "--tg"
    }

    def encode(self, basename, infos):
        cmd = [
            "/usr/bin/lame",
            "--quiet",
            # Input data
            "-r", # Use lame with raw input
            "-s", "44.1", # Raw is sample at 44100Hz
            "--bitwidth", "16", # With 16 bits samples
            # Output spec
            "-m", "j", # Encode in joint stereo
            "-h", # Use a quiet good encoding quality
            "-V", "6" # Use a variable bitrate
            ]

        if infos:
            cmd.append("--add-id3v2")
            for key, value in infos.items():
                if key in self.SUPPORTED_TAGS.keys():
                    cmd.append(self.SUPPORTED_TAGS[key])
                    cmd.append(str(value))

        cmd.append("{}.raw".format(basename))
        filename = self.get_filename(infos)
        if not filename:
            filename = basename
        cmd.append("{}.mp3".format(filename))

        lame_process = subprocess.Popen(cmd)
        lame_process.wait()
        self.delete_raw(basename)

class FlacEncoder(Encoder):
    """
    Flac encoder implementation
    """

    SUPPORTED_TAGS = {
        "title": "TITLE",
        "artist": "ARTIST",
        "album": "ALBUM",
        "year": "DATE",
        "comment": "DESCRIPTION",
        "track": "TRACKNUMBER",
        "genre": "GENRE",
        "version": "VERSION",
        "performer": "PERFORMER",
        "copyright": "COPYRIGHT",
        "license": "LICENSE",
        "organization": "ORGANIZATION",
        "location": "LOCATION",
        "contact": "CONTACT",
        "isrc": "ISRC"
    }

    def encode(self, basename, infos):
        cmd = [
            "/usr/bin/flac",
            "--silent"
            # Input data
            "--force-raw-input", # Use lame with raw input
            "--channels=2", # Two channels input
            "--bps=16", # 16 bits per samples
            "--sample-rate=44100", # Raw is sampled at 44100Hz
            # Output spec
            "--replay-gain", # Apply replay gain
            ]

        if infos:
            for key, value in infos.items():
                if key in self.SUPPORTED_TAGS.keys():
                    cmd.append("-T")
                    cmd.append("{}={}".format(
                        self.SUPPORTED_TAGS[key], str(value)))

        cmd.append("-f") # Override already existing file
        filename = self.get_filename(infos)
        if not filename:
            filename = basename
        cmd.append("-o") # Set output file
        cmd.append("{}.flac".format(filename))

        cmd.append("{}.raw".format(basename))

        lame_process = subprocess.Popen(cmd)
        if not self.keep_raw:
            lame_process.wait()
            subprocess.call(
                ["/bin/rm", "{}.raw".format(basename)]
            )
