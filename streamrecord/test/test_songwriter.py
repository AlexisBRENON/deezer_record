#! /usr/bin/env python3
""" Test module for the SongWriter class"""

import time
import queue
import pytest
import threading

from songwriter import SongWriter
from encoder import DebugEncoder as Encoder

@pytest.fixture()
def shared_ressources(request):
    """
    PyTest fixture which create all required arguments to instanciate a song writer.
    """
    synchronization = {
        'start': threading.Barrier(1),
        'end': threading.Event(),
        'tasks': queue.Queue()
        }
    data = {
        'raw_data': [],
        'lock': threading.Lock()
        }
    encoder = Encoder()
    def fin():
        """
        Funcion called after the test when fixture is at the end of its life
        """
        encoder.clear()
    request.addfinalizer(fin)
    return {
        'data': data,
        'synchronization': synchronization,
        'encoder': encoder
        }

def test_ending(shared_ressources):
    """
    Test that a song writer stops when the end event is set.
    """
    synchronization = shared_ressources['synchronization']
    data = shared_ressources['data']
    encoder = shared_ressources['encoder']
    songwriter = SongWriter(synchronization, data, encoder)
    synchronization['end'].set()
    songwriter.start()
    songwriter.join()
    assert not songwriter.is_alive()

def test_do_task(shared_ressources):
    """
    Test that a song writer do something when a task is added.
    """
    synchronization = shared_ressources['synchronization']
    data = shared_ressources['data']
    encoder = shared_ressources['encoder']
    songwriter = SongWriter(synchronization, data, encoder)
    songwriter.start()
    time.sleep(0.1)
    synchronization['end'].set()
    synchronization['tasks'].put({
        'id': 0,
        'length': 0,
        'infos': {},
        })
    synchronization['tasks'].join()
    assert 0 in encoder.encoded

def test_detect_no_gap(shared_ressources):
    """
    Test that the song writer write all data if
    no gap is detected and no more data are available
    """
    synchronization = shared_ressources['synchronization']
    data = shared_ressources['data']
    encoder = shared_ressources['encoder']
    length = 44100 * 2 * 2

    from random import randint
    for _ in range(0, length):
        data['raw_data'].append(randint(128, 255))

    songwriter = SongWriter(synchronization, data, encoder)
    songwriter.start()
    time.sleep(0.1)
    synchronization['end'].set()
    synchronization['tasks'].put({
        'id': 0,
        'length': 1,
        'infos': {},
        })
    synchronization['tasks'].join()
    assert encoder.encoded[0].st_size == length

def test_detect_one_gap(shared_ressources):
    """
    Test that song writer detects gap and split on the middle.
    """
    synchronization = shared_ressources['synchronization']
    data = shared_ressources['data']
    encoder = shared_ressources['encoder']
    length_seconds = 6
    part = (44100 * 2 * 2) * length_seconds
    silence_part = (44100 * 2 * 2)
    length = part + 0.5*silence_part
    length2 = 0.5*silence_part + part

    from random import randint
    for _ in range(0, part):
        data['raw_data'].append(randint(128, 255))
    for _ in range(0, silence_part):
        data['raw_data'].append(0)
    for _ in range(0, part):
        data['raw_data'].append(randint(128, 255))

    songwriter = SongWriter(synchronization, data, encoder)
    songwriter.start()
    time.sleep(0.1)
    synchronization['tasks'].put({
        'id': 0,
        'length': length_seconds,
        'infos': {},
        })
    synchronization['tasks'].put({
        'id': 1,
        'length': length_seconds,
        'infos': {},
        })
    synchronization['end'].set()
    synchronization['tasks'].join()
    assert encoder.encoded[0].st_size == length
    assert encoder.encoded[1].st_size == length2

def test_detect_longest_gap_after(shared_ressources):
    """
    Test that song writer doesn't split on the first but on the longest gap.
    """
    synchronization = shared_ressources['synchronization']
    data = shared_ressources['data']
    encoder = shared_ressources['encoder']
    part = 44100 * 2 * 2
    length = part + 0.4*part + part + 0.4 * part
    length2 = 0.4*part + part

    from random import randint
    for _ in range(0, part):
        data['raw_data'].append(randint(128, 255))
    for _ in range(0, int(0.4 * part)):
        data['raw_data'].append(0)
    for _ in range(0, part):
        data['raw_data'].append(randint(128, 255))
    for _ in range(0, int(0.8 * part)):
        data['raw_data'].append(0)
    for _ in range(0, part):
        data['raw_data'].append(randint(128, 255))

    songwriter = SongWriter(synchronization, data, encoder)
    songwriter.start()
    time.sleep(0.1)
    synchronization['tasks'].put({
        'id': 0,
        'length': 2,
        'infos': {},
        })
    synchronization['tasks'].put({
        'id': 1,
        'length': 1,
        'infos': {},
        })
    synchronization['end'].set()
    synchronization['tasks'].join()
    assert encoder.encoded[0].st_size == length
    assert encoder.encoded[1].st_size == length2

def test_detect_longest_gap_before(shared_ressources):
    """
    Test that song writer split on longest gap, not the latest.
    """
    synchronization = shared_ressources['synchronization']
    data = shared_ressources['data']
    encoder = shared_ressources['encoder']
    part = 44100 * 2 * 2
    silence_part = 0.4*part
    length = part + silence_part
    length2 = silence_part + part + silence_part + part

    from random import randint
    for _ in range(0, part):
        data['raw_data'].append(randint(128, 255))
    for _ in range(0, int(2 * silence_part)):
        data['raw_data'].append(0)
    for _ in range(0, part):
        data['raw_data'].append(randint(128, 255))
    for _ in range(0, int(silence_part)):
        data['raw_data'].append(0)
    for _ in range(0, part):
        data['raw_data'].append(randint(128, 255))

    songwriter = SongWriter(synchronization, data, encoder)
    songwriter.start()
    time.sleep(0.1)
    synchronization['tasks'].put({
        'id': 0,
        'length': 1,
        'infos': {},
        })
    synchronization['tasks'].put({
        'id': 1,
        'length': 2,
        'infos': {},
        })
    synchronization['end'].set()
    synchronization['tasks'].join()
    assert encoder.encoded[0].st_size == length
    assert encoder.encoded[1].st_size == length2

@pytest.mark.long
def test_long_track(shared_ressources):
    """
    Test song writer handles long stream of data (~4min)
    """
    synchronization = shared_ressources['synchronization']
    data = shared_ressources['data']
    encoder = shared_ressources['encoder']
    part = (44100 * 2 * 2) * 4*60
    silence_part = 5*(44100*2*2)
    length = silence_part + part + silence_part

    print("Creating long stream of data...")
    from random import randint
    for _ in range(0, silence_part):
        data['raw_data'].append(0)
    for _ in range(0, part):
        data['raw_data'].append(200)
    for _ in range(0, int(2 * silence_part)):
        data['raw_data'].append(0)
    for _ in range(0, int(2 * silence_part)):
        data['raw_data'].append(200)

    songwriter = SongWriter(synchronization, data, encoder)
    songwriter.start()
    time.sleep(0.1)
    synchronization['tasks'].put({
        'id': 0,
        'length': 4*60,
        'infos': {},
        })
    synchronization['end'].set()
    synchronization['tasks'].join()
    assert encoder.encoded[0].st_size == length

