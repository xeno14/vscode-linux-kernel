from __future__ import print_function, division

import argparse
import fnmatch
import functools
import json
import math
import multiprocessing
import os
import os.path
import re
import sys


CMD_VAR_RE = re.compile(r'^\s*cmd_(\S+)\s*:=\s*(.+)\s*$', re.MULTILINE)
SOURCE_VAR_RE = re.compile(r'^\s*source_(\S+)\s*:=\s*(.+)\s*$', re.MULTILINE)


def print_progress_bar(progress):
    progress_bar = '[' + '|' * \
        int(50 * progress) + '-' * int(50 * (1.0 - progress)) + ']'
    print('\r', progress_bar, "{0:.1%}".format(
        progress), end='\r', file=sys.stderr)


def parse_cmd_file(out_dir, cmdfile_path):
    with open(cmdfile_path, 'r') as cmdfile:
        cmdfile_content = cmdfile.read()

    commands = {match.group(1): match.group(2)
                for match in CMD_VAR_RE.finditer(cmdfile_content)}
    sources = {match.group(1): match.group(2)
               for match in SOURCE_VAR_RE.finditer(cmdfile_content)}

    return [{
            'directory': out_dir,
            'command': commands[o_file_name],
            'file': source,
            'output': o_file_name
            } for o_file_name, source in sources.items()]


def gen_driver_command(module_name: str, src_file: str, base_compile_command: dict):
    command = base_compile_command["command"]

    # TODO replace -DKBUILD_BASENAME, -DKBUILD_MODNAME and source and object file name.

    return {
        'directory': base_compile_command["directory"],
        'command': command,
        'file': src_file,
        'output': src_file.replace(".c", ".o")
    }


def is_device_driver_source(src_file: str):
    with open(src_file, "r") as f:
        content = f.read()
    return r"<linux/" in content


def gen_compile_commands(out_dir: str, drivers: list):
    print("Building *.o.cmd file list...", file=sys.stderr)

    out_dir = os.path.abspath(out_dir)

    cmd_files = []
    for cur_dir, subdir, files in os.walk(out_dir):
        cmd_files.extend(os.path.join(cur_dir, cmdfile_name)
                         for cmdfile_name in fnmatch.filter(files, '*.o.cmd'))

    print("Parsing *.o.cmd files...", file=sys.stderr)

    n_processed = 0
    print_progress_bar(0)

    compdb = []
    pool = multiprocessing.Pool()
    try:
        for compdb_chunk in pool.imap_unordered(functools.partial(parse_cmd_file, out_dir), cmd_files, chunksize=int(math.sqrt(len(cmd_files)))):
            compdb.extend(compdb_chunk)
            n_processed += 1
            print_progress_bar(n_processed / len(cmd_files))

    finally:
        pool.terminate()
        pool.join()

    print("Generating commands for device drivers...", file=sys.stderr)
    import glob
    base_compile_command = compdb[0]
    driver_cmds = []
    for driver in drivers:
        for src in glob.glob(os.path.join(driver, "*.c")):
            if src.endswith(".mod.c"):
                continue
            if not is_device_driver_source(src):
                print(src, "seems not a device driver source. skipping.", file=sys.stderr)
                continue
            driver_cmd = gen_driver_command(driver, src, base_compile_command)
            driver_cmds.append(driver_cmd)

    print(file=sys.stderr)
    print("Writing compile_commands.json...", file=sys.stderr)

    with open('compile_commands.json', 'w') as compdb_file:
        json.dump(compdb + driver_cmds, compdb_file, indent=1)


def main():
    cmd_parser = argparse.ArgumentParser()
    cmd_parser.add_argument('-O', '--out-dir', type=str,
                            default=os.getcwd(), help="Build output directory")
    cmd_parser.add_argument('-d', '--drivers', type=str,
                            nargs='+', help="device drivers")
    args = cmd_parser.parse_args()
    gen_compile_commands(
        args.out_dir, [d.strip() for d in args.drivers]
    )


if __name__ == '__main__':
    main()
