#!/usr/bin/sh
export VOLK_GENERIC=1
export GR_DONT_LOAD_PREFS=1
export srcdir=/home/theo/Documents/ResearchProj/GNU_Radio/Plugins/gr-doa/python/doa
export GR_CONF_CONTROLPORT_ON=False
export PATH="/home/theo/Documents/ResearchProj/GNU_Radio/Plugins/gr-doa/build-libresdr/python/doa":"$PATH"
export LD_LIBRARY_PATH="/home/theo/Documents/ResearchProj/GNU_Radio/Plugins/gr-doa/build-libresdr/lib":$LD_LIBRARY_PATH
export PYTHONPATH=/home/theo/Documents/ResearchProj/GNU_Radio/Plugins/gr-doa/build-libresdr/test_modules:$PYTHONPATH
/usr/bin/python3 /home/theo/Documents/ResearchProj/GNU_Radio/Plugins/gr-doa/python/doa/qa_find_local_max.py 
