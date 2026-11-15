//
//  BootstrapBridge.h
//  Desk-simulator Engine Layer
//
//  C-ABI declarations for dynamic QEMU execution and thread bootstrapping.
//

#ifndef BOOTSTRAP_BRIDGE_H
#define BOOTSTRAP_BRIDGE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/// QEMU execution status codes
typedef enum {
    QEMU_STATUS_STOPPED = 0,
    QEMU_STATUS_INITIALIZING = 1,
    QEMU_STATUS_RUNNING = 2,
    QEMU_STATUS_PAUSED = 3,
    QEMU_STATUS_TERMINATING = 4,
    QEMU_STATUS_ERROR = -1
} QEMUStatusCode;

/// Initializes stripped QEMU engine instance with parsed CLI arguments.
/// @param argc Argument count
/// @param argv Argument array
/// @param envp Environment array
/// @return 0 on success, non-zero error code on initialization failure.
int qemu_init(int argc, char **argv, char **envp);

/// Runs the main QEMU event loop. Typically invoked on a dedicated interactive POSIX thread.
void qemu_main_loop(void);

/// Signals the QEMU main loop to exit cleanly.
/// @return 0 on success, non-zero if unable to signal main loop.
int qemu_request_exit(void);

/// Cleans up QEMU internal state, accelerators, memory maps, and sockets.
void qemu_cleanup(void);

/// Queries whether the QEMU main event loop is currently active.
/// @return 1 if running, 0 if stopped/terminated.
int qemu_is_running(void);

/// Returns current QEMU status code.
QEMUStatusCode qemu_get_status(void);

#ifdef __cplusplus
}
#endif

#endif /* BOOTSTRAP_BRIDGE_H */
