# Install script for directory: /home/dev/Documents/ResearchProj_Fork/gr-doa/grc

# Set the install prefix
if(NOT DEFINED CMAKE_INSTALL_PREFIX)
  set(CMAKE_INSTALL_PREFIX "/usr/local")
endif()
string(REGEX REPLACE "/$" "" CMAKE_INSTALL_PREFIX "${CMAKE_INSTALL_PREFIX}")

# Set the install configuration name.
if(NOT DEFINED CMAKE_INSTALL_CONFIG_NAME)
  if(BUILD_TYPE)
    string(REGEX REPLACE "^[^A-Za-z0-9_]+" ""
           CMAKE_INSTALL_CONFIG_NAME "${BUILD_TYPE}")
  else()
    set(CMAKE_INSTALL_CONFIG_NAME "Release")
  endif()
  message(STATUS "Install configuration: \"${CMAKE_INSTALL_CONFIG_NAME}\"")
endif()

# Set the component getting installed.
if(NOT CMAKE_INSTALL_COMPONENT)
  if(COMPONENT)
    message(STATUS "Install component: \"${COMPONENT}\"")
    set(CMAKE_INSTALL_COMPONENT "${COMPONENT}")
  else()
    set(CMAKE_INSTALL_COMPONENT)
  endif()
endif()

# Install shared libraries without execute permission?
if(NOT DEFINED CMAKE_INSTALL_SO_NO_EXE)
  set(CMAKE_INSTALL_SO_NO_EXE "1")
endif()

# Is this installation the result of a crosscompile?
if(NOT DEFINED CMAKE_CROSSCOMPILING)
  set(CMAKE_CROSSCOMPILING "FALSE")
endif()

# Set path to fallback-tool for dependency-resolution.
if(NOT DEFINED CMAKE_OBJDUMP)
  set(CMAKE_OBJDUMP "/usr/bin/objdump")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/share/gnuradio/grc/blocks" TYPE FILE FILES
    "/home/dev/Documents/ResearchProj_Fork/gr-doa/grc/doa_calibrate_lin_array.block.yml"
    "/home/dev/Documents/ResearchProj_Fork/gr-doa/grc/doa_autocorrelate.block.yml"
    "/home/dev/Documents/ResearchProj_Fork/gr-doa/grc/doa_save_antenna_calib.block.yml"
    "/home/dev/Documents/ResearchProj_Fork/gr-doa/grc/doa_MUSIC_lin_array.block.yml"
    "/home/dev/Documents/ResearchProj_Fork/gr-doa/grc/doa_MUSIC_uca.block.yml"
    "/home/dev/Documents/ResearchProj_Fork/gr-doa/grc/doa_find_local_max.block.yml"
    "/home/dev/Documents/ResearchProj_Fork/gr-doa/grc/doa_antenna_correction.block.yml"
    "/home/dev/Documents/ResearchProj_Fork/gr-doa/grc/doa_rootMUSIC_linear_array.block.yml"
    "/home/dev/Documents/ResearchProj_Fork/gr-doa/grc/doa_phase_correct_hier.block.yml"
    "/home/dev/Documents/ResearchProj_Fork/gr-doa/grc/doa_average_and_save.block.yml"
    "/home/dev/Documents/ResearchProj_Fork/gr-doa/grc/doa_phase_offset_est.block.yml"
    "/home/dev/Documents/ResearchProj_Fork/gr-doa/grc/doa_findmax_and_save.block.yml"
    "/home/dev/Documents/ResearchProj_Fork/gr-doa/grc/doa_x440_usrp_source.block.yml"
    "/home/dev/Documents/ResearchProj_Fork/gr-doa/grc/doa_serial_connection.block.yml"
    "/home/dev/Documents/ResearchProj_Fork/gr-doa/grc/doa_signal_replay.block.yml"
    "/home/dev/Documents/ResearchProj_Fork/gr-doa/grc/doa_power_detection.block.yml"
    "/home/dev/Documents/ResearchProj_Fork/gr-doa/grc/doa_uca_pilot_calibration.block.yml"
    "/home/dev/Documents/ResearchProj_Fork/gr-doa/grc/doa_signal_replay_cpp.block.yml"
    "/home/dev/Documents/ResearchProj_Fork/gr-doa/grc/doa_power_detection_cpp.block.yml"
    )
endif()

string(REPLACE ";" "\n" CMAKE_INSTALL_MANIFEST_CONTENT
       "${CMAKE_INSTALL_MANIFEST_FILES}")
if(CMAKE_INSTALL_LOCAL_ONLY)
  file(WRITE "/home/dev/Documents/ResearchProj_Fork/gr-doa/build-fix/grc/install_local_manifest.txt"
     "${CMAKE_INSTALL_MANIFEST_CONTENT}")
endif()
