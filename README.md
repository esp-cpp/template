# ESP++ Template

Template repository for building an ESP app with ESP++ (espp) components and
ESP-IDF components.

## Development

This repository is designed to be used as a template repository - so you can
sepcify this as the template repository type when creating a new repository on
GitHub.

After setting this as the template, make sure to update the following:
- [This README](./README.md) to contain the relevant description and images of your project
- The [./CMakeLists.txt](./CMakeLists.txt) file to have the components that you
  want to use (and any you may have added to the [components
  folder](./components)) as well as to update the project name
- The [./main/main.cpp](./main/main.cpp) To run the main code for your app. The
  [main folder](./main) is also where you can put additional header and source
  files that you don't think belong in their own components but help keep the
  main code clean.

## Cloning

Since this repo contains a submodule, you need to make sure you clone it
recursively, e.g. with:

``` sh
git clone --recurse-submodules <your repo name>
```

Alternatively, you can always ensure the submodules are up to date after cloning
(or if you forgot to clone recursively) by running:

``` sh
git submodule update --init --recursive
```

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
