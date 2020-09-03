# Copyright 2020 Canonical, Ltd.
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

import argparse
import logging
import os
import sys
import time

from cloudinit import atomic_helper, safeyaml, stages

from subiquitycore.log import setup_logger
from subiquitycore.utils import run_command

from .common import (
    LOGDIR,
    setup_environment,
    )


def make_server_args_parser():
    parser = argparse.ArgumentParser(
        description='SUbiquity - Ubiquity for Servers',
        prog='subiquity')
    parser.add_argument('--dry-run', action='store_true',
                        dest='dry_run',
                        help='menu-only, do not call installer function')
    parser.add_argument('--socket')
    parser.add_argument('--machine-config', metavar='CONFIG',
                        dest='machine_config',
                        help="Don't Probe. Use probe data file")
    parser.add_argument('--bootloader',
                        choices=['none', 'bios', 'prep', 'uefi'],
                        help='Override style of bootloader to use')
    parser.add_argument('--answers')
    parser.add_argument('--autoinstall', action='store')
    with open('/proc/cmdline') as fp:
        cmdline = fp.read()
    parser.add_argument('--kernel-cmdline', action='store', default=cmdline)
    parser.add_argument('--source', default=[], action='append',
                        dest='sources', metavar='URL',
                        help='install from url instead of default.')
    parser.add_argument(
        '--snaps-from-examples', action='store_const', const=True,
        dest="snaps_from_examples",
        help=("Load snap details from examples/snaps instead of store. "
              "Default in dry-run mode.  "
              "See examples/snaps/README.md for more."))
    parser.add_argument(
        '--no-snaps-from-examples', action='store_const', const=False,
        dest="snaps_from_examples",
        help=("Load snap details from store instead of examples. "
              "Default in when not in dry-run mode.  "
              "See examples/snaps/README.md for more."))
    parser.add_argument(
        '--snap-section', action='store', default='server',
        help=("Show snaps from this section of the store in the snap "
              "list screen."))
    return parser


def main():
    setup_environment()
    # setup_environment sets $APPORT_DATA_DIR which must be set before
    # apport is imported, which is done by this import:
    from subiquity.server.server import SubiquityServer
    parser = make_server_args_parser()
    opts = parser.parse_args(sys.argv[1:])
    logdir = LOGDIR
    if opts.dry_run:
        logdir = ".subiquity"
        if opts.snaps_from_examples is None:
            opts.snaps_from_examples = True
    if opts.socket is None:
        if opts.dry_run:
            opts.socket = '.subiquity/socket'
        else:
            opts.socket = '/run/subiquity/socket'
    os.makedirs(os.path.basename(opts.socket), exist_ok=True)

    logfiles = setup_logger(dir=logdir, base='subiquity-server')

    logger = logging.getLogger('subiquity')
    version = os.environ.get("SNAP_REVISION", "unknown")
    logger.info("Starting Subiquity server revision {}".format(version))
    logger.info("Arguments passed: {}".format(sys.argv))

    if not opts.dry_run:
        ci_start = time.time()
        status_txt = run_command(["cloud-init", "status", "--wait"]).stdout
        logger.debug("waited %ss for cloud-init", time.time() - ci_start)
        if "status: done" in status_txt:
            logger.debug("loading cloud config")
            init = stages.Init()
            init.read_cfg()
            init.fetch(existing="trust")
            cloud = init.cloudify()
            autoinstall_path = '/autoinstall.yaml'
            if 'autoinstall' in cloud.cfg:
                if not os.path.exists(autoinstall_path):
                    atomic_helper.write_file(
                        autoinstall_path,
                        safeyaml.dumps(
                            cloud.cfg['autoinstall']).encode('utf-8'),
                        mode=0o600)
            if os.path.exists(autoinstall_path):
                opts.autoinstall = autoinstall_path
        else:
            logger.debug(
                "cloud-init status: %r, assumed disabled",
                status_txt)

    block_log_dir = os.path.join(logdir, "block")
    os.makedirs(block_log_dir, exist_ok=True)
    handler = logging.FileHandler(os.path.join(block_log_dir, 'discover.log'))
    handler.setLevel('DEBUG')
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(name)s:%(lineno)d %(message)s"))
    logging.getLogger('probert').addHandler(handler)
    handler.addFilter(lambda rec: rec.name != 'probert.network')
    logging.getLogger('curtin').addHandler(handler)
    logging.getLogger('block-discover').addHandler(handler)

    subiquity_interface = SubiquityServer(opts, block_log_dir)

    subiquity_interface.note_file_for_apport(
        "InstallerServerLog", logfiles['debug'])
    subiquity_interface.note_file_for_apport(
        "InstallerServerLogInfo", logfiles['info'])

    subiquity_interface.run()


if __name__ == '__main__':
    sys.exit(main())
