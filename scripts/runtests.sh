#!/bin/bash
set -eux
cloud-init status
cloud-init status --wait
python3 -m unittest discover
export SUBIQUITY_REPLAY_TIMESCALE=100
for answers in examples/answers*.yaml; do
    rm -f .subiquity/subiquity-curtin-install.conf
    rm -f .subiquity/subiquity-debug.log
    rm -f .subiquity/run/subiquity/updating
    # The --foreground is important to avoid subiquity getting SIGTTOU-ed.
    timeout --foreground 60 sh -c "LANG=C.UTF-8 python3 -m subiquity.cmd.tui --answers $answers --dry-run --snaps-from-examples --machine-config examples/simple.json"
    python3 scripts/validate-yaml.py .subiquity/subiquity-curtin-install.conf
    if [ ! -e .subiquity/subiquity-debug.log ]; then
        echo "log file not created"
        exit 1
    fi
    if grep passw0rd .subiquity/subiquity-debug.log | grep -v "Loaded answers" | grep -v "answers_action"; then
        echo "password leaked into log file"
        exit 1
    fi
done
