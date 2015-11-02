#! /usr/bin/env python3
""" Test module for the SongWriter class"""

import io
import os
import pytest

import encoder as encoders

@pytest.fixture(scope="session")
def raw_file(request):
    with io.open("0.raw", "wb") as raw_file:
        raw_file.write(bytes([200]*44100*2*2*10))
    def fin():
        os.unlink("0.raw")
    request.addfinalizer(fin)

@pytest.fixture
def tags(request):
    tags = {
        'title': "test",
        'artist': "encoder",
        'album': "test_encoder.py",
        'year': 2015,
        'track': 0,
        'genre': 'experimental',
        'version': 1.0,
        'performer': 'Alexis BRENON',
        'copyright': "None",
        'licence': "CC-0",
        'organization': "Personal",
        'location': "France",
        'contact': "brenon.alexis@gmail.com",
        'isrc': "Unknown",
        'comment': "Test only a quite short comment"
        }
    return tags

def test_abstract_encoder(raw_file):
    encoder = encoders.Encoder()
    with pytest.raises(NotImplementedError):
        encoder.encode("0", None)

def test_mp3_lame_encoder(raw_file):
    encoder = encoders.Mp3LameEncoder(keep_raw=True)
    encoder.encode("0", None)
    # TODO : check existence and compute the length of the resulting file
    assert False
    os.unlink("0.mp3")

def test_mp3_lame_encoder_tags(raw_file, tags):
    encoder = encoders.Mp3LameEncoder(keep_raw=True)
    encoder.encode("0", tags)
    # TODO : check tags
    assert False
    os.unlink("{}.mp3".format(encoder.get_filename(tags)))

def test_flac_encoder(raw_file):
    encoder = encoders.FlacEncoder(keep_raw=True)
    encoder.encode("0", None)
    # TODO : check existence and compute the length of the resulting file
    assert False
    os.unlink("0.mp3")

def test_flac_encoder_tags(raw_file, tags):
    encoder = encoders.FlacEncoder(keep_raw=True)
    encoder.encode("0", tags)
    # TODO : check tags
    assert False
    os.unlink("{}.flac".format(encoder.get_filename(tags)))
