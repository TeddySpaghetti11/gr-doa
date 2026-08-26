#!/usr/bin/sh
export VOLK_GENERIC=1
export GR_DONT_LOAD_PREFS=1
export srcdir=/home/dev/Documents/ResearchProj_Fork/gr-doa/python/doa
export GR_CONF_CONTROLPORT_ON=False
export PATH="/home/dev/Documents/ResearchProj_Fork/gr-doa/build-fix/python/doa":"$PATH"
export LD_LIBRARY_PATH="/home/dev/Documents/ResearchProj_Fork/gr-doa/build-fix/lib":$LD_LIBRARY_PATH
export PYTHONPATH=/home/dev/Documents/ResearchProj_Fork/gr-doa/build-fix/test_modules:$PYTHONPATH
/usr/bin/python3 /home/dev/Documents/ResearchProj_Fork/gr-doa/python/doa/qa_MUSIC_uca.py 
