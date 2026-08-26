# Install script for directory: /home/dev/Documents/ResearchProj_Fork/gr-doa/include/gnuradio/doa

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
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include/gnuradio/doa" TYPE FILE FILES
    "/home/dev/Documents/ResearchProj_Fork/gr-doa/include/gnuradio/doa/api.h"
    "/home/dev/Documents/ResearchProj_Fork/gr-doa/include/gnuradio/doa/calibrate_lin_array.h"
    "/home/dev/Documents/ResearchProj_Fork/gr-doa/include/gnuradio/doa/autocorrelate.h"
    "/home/dev/Documents/ResearchProj_Fork/gr-doa/include/gnuradio/doa/MUSIC_lin_array.h"
    "/home/dev/Documents/ResearchProj_Fork/gr-doa/include/gnuradio/doa/MUSIC_uca.h"
    "/home/dev/Documents/ResearchProj_Fork/gr-doa/include/gnuradio/doa/find_local_max.h"
    "/home/dev/Documents/ResearchProj_Fork/gr-doa/include/gnuradio/doa/antenna_correction.h"
    "/home/dev/Documents/ResearchProj_Fork/gr-doa/include/gnuradio/doa/rootMUSIC_linear_array.h"
    "/home/dev/Documents/ResearchProj_Fork/gr-doa/include/gnuradio/doa/signal_replay_cpp.h"
    "/home/dev/Documents/ResearchProj_Fork/gr-doa/include/gnuradio/doa/power_detection_cpp.h"
    )
endif()

string(REPLACE ";" "\n" CMAKE_INSTALL_MANIFEST_CONTENT
       "${CMAKE_INSTALL_MANIFEST_FILES}")
if(CMAKE_INSTALL_LOCAL_ONLY)
  file(WRITE "/home/dev/Documents/ResearchProj_Fork/gr-doa/build-fix/include/gnuradio/doa/install_local_manifest.txt"
     "${CMAKE_INSTALL_MANIFEST_CONTENT}")
endif()
