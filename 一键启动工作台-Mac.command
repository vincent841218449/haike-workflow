#!/bin/zsh
cd "${0:A:h}"
./Haike_video/.venv/bin/python portable/macos.py start --publisher
if [[ $? -ne 0 ]]; then
  read '?启动失败，按回车关闭。'
fi
