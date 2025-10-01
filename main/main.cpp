#include <atomic>
#include <chrono>
#include <thread>

#include "logger.hpp"
#include "task.hpp"

using namespace std::chrono_literals;

extern "C" void app_main(void) {
  espp::Logger logger({.tag = "Template", .level = espp::Logger::Verbosity::DEBUG});

  logger.info("Bootup");

  // counter to show the number of prints, shared between main and task
  std::atomic<int> counter = 0;

  // make a simple task that prints "Hello World!" every second
  espp::Task task({
      .callback = [&](auto &m, auto &cv) -> bool {
        logger.debug("[{}] Hello from the task!", counter++);
        std::unique_lock<std::mutex> lock(m);
        cv.wait_for(lock, 1s);
        // we don't want to stop the task, so return false
        return false;
      },
        .task_config = {
          .name = "Hello World",
          .stack_size_bytes = 4096,
        }
    });
  task.start();

  // also print in the main thread
  while (true) {
    logger.debug("[{}] Hello World!", counter++);
    std::this_thread::sleep_for(1s);
  }
}
