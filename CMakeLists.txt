# The following lines of boilerplate have to be in your project's CMakeLists
# in this exact order for cmake to work correctly
cmake_minimum_required(VERSION 3.20)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)

# add the component directories that we want to use
set(EXTRA_COMPONENT_DIRS

  # NOTE: if you add any custom components, you should add them to a
  #       `components/` folder within this repository and update the line below
  #       to point to it.
  #
  # "components/"

  # NOTE: if we didn't use the idf-component-manager to get the espp
  #       dependencies, we could instead have ESPP be a submodule within our
  #       'components' folder, which would mean we'd need to add it to the DIRS:
  #
  # "components/espp/components/"
  #
  # NOTE: alternatively, we could install espp system-wide, so we could just
  #       point it to wherever we have espp installed.
  #
  # "/path/to/espp/components/"
)

set(
  COMPONENTS
  # NOTE: you can add additional esp-idf and espp components you want to use to
  #       the line below.
  #
  # Alternatively, If they exist in the component registry, then you can ignore
  # adding them here, and instead use call
  #
  # `idf.py add-dependency "<namespace>/<component>^<version>"`
  #
  # e.g.
  #
  # `idf.py add-dependency "espp/task>=1.0"`
  "main esptool_py"
  CACHE STRING
  "List of components to include"
  )

# TODO: update this with your project's name
project(template)

set(CMAKE_CXX_STANDARD 20)
