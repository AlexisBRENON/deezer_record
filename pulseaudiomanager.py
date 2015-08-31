#!/usr/bin/env python3
"""
Main PulseAudio manager implementation
"""

import logging
import threading
import subprocess

class PulseAudioManager(threading.Thread):
    """ PulseAudio manager class that load required module, move sinks
    and restore everything at the end."""
    def __init__(self, thread_synchronization, parec_output_pipe):
        """ Create a new PulseAudio Manager
        thread_synchronization Dictionnary with 'start' and 'end' objects for synchronization
        parec_output_pipe Writing end of a pipe where the parec output will
            be redirected.
        """
        super(PulseAudioManager, self).__init__()
        self.thread_start = thread_synchronization['start']
        self.thread_end = thread_synchronization['end']
        self.parec_process = None
        self.parec_output_pipe = parec_output_pipe
        self.sink_input = None
        self.module_id = None

    def move_sink_input(self):
        """ Let's the user choose a sink to move to the recorder """
        def _parse_sink_inputs():
            """ Read PA output to list all available sinks """
            sink_inputs = {}
            pacmd_process = subprocess.Popen(
                ["/usr/bin/pacmd", "list-sink-inputs"],
                stdout=subprocess.PIPE
            )
            for line in pacmd_process.stdout:
                line = line.decode()
                sink_index = re.search(r"^\s*index: (.*)", line)
                if sink_index:
                    for line in pacmd_process.stdout:
                        line = line.decode()
                        app_name = re.search(r"^\s*application.name = \"(.*)\"", line)
                        if app_name:
                            sink_inputs[int(sink_index.group(1))] = app_name.group(1)
                            break
            return sink_inputs

        # Find which input need to be moved
        print("Let's play your application... Then press Enter.")
        _ = input()
        sink_inputs = _parse_sink_inputs()
        if len(sink_inputs.keys()) == 1:
            self.sink_input = list(sink_inputs.keys())[0]
        else:
            self.sink_input = select(sink_inputs)

        # Load the null module
        self.module_id = int(subprocess.check_output(
            ["/usr/bin/pactl", "load-module", "module-null-sink", "sink_name=deezer_record"]
        ))

        # Move the sink input
        subprocess.call(
            ["/usr/bin/pactl", "move-sink-input", str(self.sink_input), "deezer_record"]
        )

    def reset_sink_input(self):
        """ Reset the PA configuration to its initial state """
        logging.debug("Reset sink input to its right sink")
        subprocess.call(
            ["/usr/bin/pactl", "move-sink-input", str(self.sink_input), "1"]
        )
        logging.debug("Unload NULL module")
        subprocess.call(
            ["/usr/bin/pactl", "unload-module", str(self.module_id)]
        )

    def launch_parec(self):
        """ Actually launch the record of the moved sink """
        self.parec_process = subprocess.Popen(
            ["/usr/bin/parec", "-d", "deezer_record.monitor"],
            stdout=self.parec_output_pipe
        )

    def stop_parec(self):
        """ Stop recording of the stream """
        self.parec_process.terminate()

    def run(self):
        self.move_sink_input()
        logging.info("Start barrier reached")
        self.thread_start.wait()
        self.launch_parec()

        self.thread_end.wait()
        logging.info("End event set")
        self.stop_parec()
        self.reset_sink_input()
        logging.info("Exit")
