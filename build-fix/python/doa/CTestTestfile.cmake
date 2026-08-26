# CMake generated Testfile for 
# Source directory: /home/dev/Documents/ResearchProj_Fork/gr-doa/python/doa
# Build directory: /home/dev/Documents/ResearchProj_Fork/gr-doa/build-fix/python/doa
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
add_test(qa_calibrate_lin_array "/usr/bin/sh" "qa_calibrate_lin_array_test.sh")
set_tests_properties(qa_calibrate_lin_array PROPERTIES  _BACKTRACE_TRIPLES "/usr/local/lib/cmake/gnuradio/GrTest.cmake;119;add_test;/home/dev/Documents/ResearchProj_Fork/gr-doa/python/doa/CMakeLists.txt;48;GR_ADD_TEST;/home/dev/Documents/ResearchProj_Fork/gr-doa/python/doa/CMakeLists.txt;0;")
add_test(qa_autocorrelate "/usr/bin/sh" "qa_autocorrelate_test.sh")
set_tests_properties(qa_autocorrelate PROPERTIES  _BACKTRACE_TRIPLES "/usr/local/lib/cmake/gnuradio/GrTest.cmake;119;add_test;/home/dev/Documents/ResearchProj_Fork/gr-doa/python/doa/CMakeLists.txt;49;GR_ADD_TEST;/home/dev/Documents/ResearchProj_Fork/gr-doa/python/doa/CMakeLists.txt;0;")
add_test(qa_MUSIC_lin_array "/usr/bin/sh" "qa_MUSIC_lin_array_test.sh")
set_tests_properties(qa_MUSIC_lin_array PROPERTIES  _BACKTRACE_TRIPLES "/usr/local/lib/cmake/gnuradio/GrTest.cmake;119;add_test;/home/dev/Documents/ResearchProj_Fork/gr-doa/python/doa/CMakeLists.txt;50;GR_ADD_TEST;/home/dev/Documents/ResearchProj_Fork/gr-doa/python/doa/CMakeLists.txt;0;")
add_test(qa_MUSIC_uca "/usr/bin/sh" "qa_MUSIC_uca_test.sh")
set_tests_properties(qa_MUSIC_uca PROPERTIES  _BACKTRACE_TRIPLES "/usr/local/lib/cmake/gnuradio/GrTest.cmake;119;add_test;/home/dev/Documents/ResearchProj_Fork/gr-doa/python/doa/CMakeLists.txt;51;GR_ADD_TEST;/home/dev/Documents/ResearchProj_Fork/gr-doa/python/doa/CMakeLists.txt;0;")
add_test(qa_uca_pilot_calibration "/usr/bin/sh" "qa_uca_pilot_calibration_test.sh")
set_tests_properties(qa_uca_pilot_calibration PROPERTIES  _BACKTRACE_TRIPLES "/usr/local/lib/cmake/gnuradio/GrTest.cmake;119;add_test;/home/dev/Documents/ResearchProj_Fork/gr-doa/python/doa/CMakeLists.txt;52;GR_ADD_TEST;/home/dev/Documents/ResearchProj_Fork/gr-doa/python/doa/CMakeLists.txt;0;")
add_test(qa_find_local_max "/usr/bin/sh" "qa_find_local_max_test.sh")
set_tests_properties(qa_find_local_max PROPERTIES  _BACKTRACE_TRIPLES "/usr/local/lib/cmake/gnuradio/GrTest.cmake;119;add_test;/home/dev/Documents/ResearchProj_Fork/gr-doa/python/doa/CMakeLists.txt;53;GR_ADD_TEST;/home/dev/Documents/ResearchProj_Fork/gr-doa/python/doa/CMakeLists.txt;0;")
add_test(qa_rootMUSIC_linear_array "/usr/bin/sh" "qa_rootMUSIC_linear_array_test.sh")
set_tests_properties(qa_rootMUSIC_linear_array PROPERTIES  _BACKTRACE_TRIPLES "/usr/local/lib/cmake/gnuradio/GrTest.cmake;119;add_test;/home/dev/Documents/ResearchProj_Fork/gr-doa/python/doa/CMakeLists.txt;54;GR_ADD_TEST;/home/dev/Documents/ResearchProj_Fork/gr-doa/python/doa/CMakeLists.txt;0;")
subdirs("bindings")
