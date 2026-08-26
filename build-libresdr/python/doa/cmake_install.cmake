# Install script for directory: /home/theo/Documents/ResearchProj/GNU_Radio/Plugins/gr-doa/python/doa

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

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/home/theo/Documents/ResearchProj/GNU_Radio/Plugins/gr-doa/build-libresdr/python/doa/bindings/cmake_install.cmake")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib/python3.14/dist-packages/gnuradio/doa" TYPE FILE FILES
    "/home/theo/Documents/ResearchProj/GNU_Radio/Plugins/gr-doa/python/doa/__init__.py"
    "/home/theo/Documents/ResearchProj/GNU_Radio/Plugins/gr-doa/python/doa/save_antenna_calib.py"
    "/home/theo/Documents/ResearchProj/GNU_Radio/Plugins/gr-doa/python/doa/phase_correct_hier.py"
    "/home/theo/Documents/ResearchProj/GNU_Radio/Plugins/gr-doa/python/doa/average_and_save.py"
    "/home/theo/Documents/ResearchProj/GNU_Radio/Plugins/gr-doa/python/doa/phase_offset_est.py"
    "/home/theo/Documents/ResearchProj/GNU_Radio/Plugins/gr-doa/python/doa/findmax_and_save.py"
    "/home/theo/Documents/ResearchProj/GNU_Radio/Plugins/gr-doa/python/doa/x440_usrp_source.py"
    "/home/theo/Documents/ResearchProj/GNU_Radio/Plugins/gr-doa/python/doa/serial_connection.py"
    "/home/theo/Documents/ResearchProj/GNU_Radio/Plugins/gr-doa/python/doa/signal_replay.py"
    "/home/theo/Documents/ResearchProj/GNU_Radio/Plugins/gr-doa/python/doa/power_detection.py"
    "/home/theo/Documents/ResearchProj/GNU_Radio/Plugins/gr-doa/python/doa/uca_pilot_calibration.py"
    )
endif()

string(REPLACE ";" "\n" CMAKE_INSTALL_MANIFEST_CONTENT
       "${CMAKE_INSTALL_MANIFEST_FILES}")
if(CMAKE_INSTALL_LOCAL_ONLY)
  file(WRITE "/home/theo/Documents/ResearchProj/GNU_Radio/Plugins/gr-doa/build-libresdr/python/doa/install_local_manifest.txt"
     "${CMAKE_INSTALL_MANIFEST_CONTENT}")
endif()
