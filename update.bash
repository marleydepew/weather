#!/bin/bash
cd /home/ubuntu/programs
source venv/bin/activate
python3 update.py 2>&1 | ts '[%Y-%m-%d %H:%M:%.S]' | tee -a update.py.log
