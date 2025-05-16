# ESP++ Template

Template repository for building an ESP app with ESP++ (espp) components and
ESP-IDF components.

<!-- markdown-toc start - Don't edit this section. Run M-x markdown-toc-refresh-toc -->
**Table of Contents**

- [ESP++ Template](#esp-template)
  - [Development](#development)
  - [Build and Flash](#build-and-flash)
  - [Output](#output)
  - [Developing](#developing)
    - [Code style](#code-style)

<!-- markdown-toc end -->

## Development

This repository is designed to be used as a template repository - so you can
sepcify this as the template repository type when creating a new repository on
GitHub.

After setting this as the template, make sure to update the following:
- [This README](./README.md) to contain the relevant description and images of
  your project
- Add additional component dependencies you may want, e.g.:

    ```console
    idf.py add-dependency "espp/timer>=1.0"
    ```

- The [./CMakeLists.txt](./CMakeLists.txt) file to update the project name.
- The [./main/main.cpp](./main/main.cpp) To run the main code for your app. The
  [main folder](./main) is also where you can put additional header and source
  files that you don't think belong in their own components but help keep the
  main code clean.
- The [./sdkconfig.defaults](./sdkconfig.defaults) to configure the defaults for
  your project / processor.
- Update the [./.github/workflows/build.yml](./.github/workflows/build.yml) file
  to have the correct target architecture (e.g. `esp32s3`) for your project.
- Update the [./.github/workflows/package_main.yml](./.github/workflows/package_main.yml) file
  to:
  - have the correct target architecture (e.g. `esp32s3`) for your project
  - include all the build outputs you may want (e.g. littlefs file system images)
  - have the right name for the generated 1-click programmer executable
- Enable `Read and Write permissions` under `Workflow Permissions` on the
  `Settings->Actions` subpage of the repository. that will allow the static
  analysis tool to put its results into a comment on any pull requests in your
  repository.

## Build and Flash

Build the project and flash it to the board, then run monitor tool to view serial output:

```
idf.py -p PORT flash monitor
```

(Replace PORT with the name of the serial port to use.)

(To exit the serial monitor, type ``Ctrl-]``.)

See the Getting Started Guide for full steps to configure and use ESP-IDF to build projects.

## Output

Example screenshot of the console output from this app:

![CleanShot 2023-07-12 at 14 01 21](https://github.com/esp-cpp/template/assets/213467/7f8abeae-121b-4679-86d8-7214a76f1b75)

## Developing

If you're developing code for this repository, it's recommended to configure
your development environment:

### Code style

1. Ensure `clang-format` is installed
2. Ensure [pre-commit](https://pre-commit.com) is installed
3. Set up `pre-commit` for this repository:

  ``` console
  pre-commit install
  ```

This helps ensure that consistent code formatting is applied, by running
`clang-format` each time you change the code (via a git pre-commit hook) using
the [./.clang-format](./.clang-format) code style configuration file.

If you ever want to re-run the code formatting on all files in the repository,
you can do so:

``` console
pre-commit run --all-files
```
