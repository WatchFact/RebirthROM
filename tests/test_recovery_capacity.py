#!/usr/bin/env python3
"""Run the generated recovery checker with simulated block devices; never flash."""
import os
import subprocess
import sys

checker = sys.argv[1]
harness = r'''
function [() {
    if [[ "$1" == -b ]]; then
        [[ "${CASE:-}" != missing ]]
    else
        builtin [ "$@"
    fi
}
blockdev() {
    case "${CASE:-}" in
        short) echo 1048576 ;;
        invalid) echo invalid ;;
        fail) return 1 ;;
        *) echo 2097152 ;;
    esac
}
readlink() {
    if [[ "${CASE:-}" == mounted && "$2" != /dev/block/by-name/* ]]; then
        echo /dev/block/by-name/system
    else
        printf '%s\n' "$2"
    fi
}
source "$1"
'''
for scenario in ('valid', 'short', 'invalid', 'fail', 'missing', 'mounted'):
    result = subprocess.run(['bash', '-c', harness, 'test', checker],
                            env=dict(os.environ, CASE=scenario), capture_output=True)
    assert (result.returncode == 0) == (scenario == 'valid'), (
        scenario, result.returncode, result.stderr.decode())
print('Recovery capacity simulation: six cases passed (no block writes)')
