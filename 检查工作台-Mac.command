#!/bin/zsh
cd "${0:A:h}"
./Haike_video/.venv/bin/python portable/macos.py diagnose
read '?检查结束，按回车关闭。'
