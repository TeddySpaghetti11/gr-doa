#----------------------------------------------------------------
# Generated CMake target import file for configuration "Release".
#----------------------------------------------------------------

# Commands may need to know the format version.
set(CMAKE_IMPORT_FILE_VERSION 1)

# Import target "gnuradio::gnuradio-doa" for configuration "Release"
set_property(TARGET gnuradio::gnuradio-doa APPEND PROPERTY IMPORTED_CONFIGURATIONS RELEASE)
set_target_properties(gnuradio::gnuradio-doa PROPERTIES
  IMPORTED_LOCATION_RELEASE "${_IMPORT_PREFIX}/lib/x86_64-linux-gnu/libgnuradio-doa.so.1.0.0.0"
  IMPORTED_SONAME_RELEASE "libgnuradio-doa.so.1.0.0"
  )

list(APPEND _cmake_import_check_targets gnuradio::gnuradio-doa )
list(APPEND _cmake_import_check_files_for_gnuradio::gnuradio-doa "${_IMPORT_PREFIX}/lib/x86_64-linux-gnu/libgnuradio-doa.so.1.0.0.0" )

# Commands beyond this point should not need to know the version.
set(CMAKE_IMPORT_FILE_VERSION)
