# Copyright 2019 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import fcntl
import logging
import os
import select
import subprocess
import threading
import time

from systemd import journal

import yaml

from curtin.config import merge_config


log = logging.getLogger('subiquity.autoinstall')


def merge_autoinstall_configs(source_paths, target_path):
    config = {}
    for path in source_paths:
        with open(path) as fp:
            c = yaml.safe_load(fp)
        merge_config(config, c)
    with open(target_path, 'w') as fp:
        yaml.dump(config, fp)


EARLY_COMMAND_IDENTIFIER = 'subiquity_early_command'


# Running the early-commands from an autoinstall config sounds easy,
# but the wrinkles come from the fact that multiple instances of
# subiquity can be running. We want to only run the early-commands
# once, but we want to see the output from them on all consoles
# subiquity runs on. So we use a lock / check structure: all
# subiquities subscribe to events in the journal with a particular
# tag, start a thread to print such events out and then try to lock a
# file. Once the file is locked, they all check for a stamp file and
# if it is not there, create it and then run the early commands (with
# output redirected to the journal).
#
# This is all a bit over the top for early-commands but this is how
# running the actually install will work as well so hopefully not all
# wasted effort...
def run_early_commands(config, lock_path, stamp_path):
    ident = EARLY_COMMAND_IDENTIFIER
    reader = journal.Reader()
    reader.add_match("SYSLOG_IDENTIFIER={}".format(EARLY_COMMAND_IDENTIFIER))
    pipe_r, pipe_w = os.pipe()

    def send(msg):
        journal.send(msg, SYSLOG_IDENTIFIER=ident)

    with open(lock_path, 'w') as lock_file:
        def print_events():
            for event in reader:
                print(event['MESSAGE'])
            while True:
                r, w, e = select.select([pipe_r, reader.fileno()], [], [])
                if reader.fileno() in r:
                    if reader.process() == journal.APPEND:
                        for event in reader:
                            print(event['MESSAGE'])
                if pipe_r in r:
                    os.close(pipe_r)
                    return

        printer_thread = threading.Thread(target=print_events)
        printer_thread.setDaemon(True)
        printer_thread.start()

        fcntl.flock(lock_file, fcntl.LOCK_EX)
        if not os.path.exists(stamp_path):
            open(stamp_path, 'w').close()
            send("running autoinstall early-commands")
            for cmd in config['early-commands']:
                send("running {}".format(cmd))
                cmd = [
                    'systemd-cat', '--level-prefix=false',
                    '--identifier=' + EARLY_COMMAND_IDENTIFIER,
                    'sh', '-c', cmd,
                    ]
                subprocess.run(cmd)
            # Wait a little while to make sure printer thread has seen
            # all events (there must be a less horrid way to do this).
            time.sleep(1)
        os.write(pipe_w, b'x')
        os.close(pipe_w)
