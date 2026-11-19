//
//  BootstrapBridge.h
//  Desk-simulator Engine Layer
//
//  C-ABI declarations for dynamic QEMU execution, native pthread bootstrapping,
//  POSIX process lifecycle management, and SPICE display frame ingestion.
//

#ifndef BOOTSTRAP_BRIDGE_H
#define BOOTSTRAP_BRIDGE_H

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#include <sys/types.h>

#if defined(_WIN32) && !defined(__CYGWIN__) && !defined(_PID_T_)
typedef int pid_t;
#define _PID_T_
#endif

#ifdef __cplusplus
extern "C" {
#endif

// MARK: - QEMU Execution Status

/// QEMU execution status codes
typedef enum {
    QEMU_STATUS_STOPPED = 0,
    QEMU_STATUS_INITIALIZING = 1,
    QEMU_STATUS_RUNNING = 2,
    QEMU_STATUS_PAUSED = 3,
    QEMU_STATUS_TERMINATING = 4,
    QEMU_STATUS_ERROR = -1
} QEMUStatusCode;

// MARK: - Display Ingestion Types

/// Framebuffer metadata for SPICE display ingestion
typedef struct {
    uint32_t width;
    uint32_t height;
    uint32_t stride;
    uint32_t pixel_format; // 0 = BGRA8888, 1 = RGBA8888
    const uint8_t *data;
    size_t data_len;
} QEMUDisplayFrame;

/// Display frame delivery callback function pointer
typedef void (*QEMUDisplayFrameCallback)(const QEMUDisplayFrame *frame, void *user_data);

// MARK: - Core QEMU Lifecycle

/// Initializes stripped QEMU engine instance with parsed CLI arguments.
/// @param argc Argument count
/// @param argv Argument array
/// @param envp Environment array
/// @return 0 on success, non-zero error code on initialization failure.
int qemu_init(int argc, char **argv, char **envp);

/// Initializes QEMU engine explicitly specifying target architecture ("x86_64-softmmu" or "aarch64-softmmu").
/// @param target Target architecture triple or identifier
/// @param argc Argument count
/// @param argv Argument array
/// @param envp Environment array
/// @return 0 on success, non-zero error code on initialization failure.
int qemu_init_target(const char *target, int argc, char **argv, char **envp);

/// Runs the main QEMU event loop on the current thread. Typically invoked on a dedicated interactive POSIX thread.
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

// MARK: - Dedicated Pthread Execution Hooks

/// Starts QEMU in a dedicated native pthread with 4MB+ stack size and User Interactive Mach QoS.
/// @param argc Argument count
/// @param argv Argument array
/// @param envp Environment array
/// @return 0 on success, non-zero errno on failure.
int qemu_bootstrap_start_thread(int argc, char **argv, char **envp);

/// Waits for the dedicated QEMU pthread to complete execution.
/// @return 0 on success, non-zero errno on failure.
int qemu_bootstrap_join_thread(void);

// MARK: - Out-of-Process POSIX Spawn Hooks (TrollStore / Subprocess Mode)

/// Spawns QEMU as a subprocess via posix_spawn.
/// @param executable Path to the QEMU target binary
/// @param argc Argument count
/// @param argv Argument array
/// @param envp Environment array
/// @return PID > 0 on success, -1 on failure.
pid_t qemu_spawn_process(const char *executable, int argc, char **argv, char **envp);

/// Polls status of a spawned QEMU process.
/// @param pid Process ID of the spawned QEMU process
/// @param exit_code Pointer to store exit code if process exited (can be NULL)
/// @return 1 if still running, 0 if exited, -1 on error.
int qemu_poll_process(pid_t pid, int *exit_code);

/// Requests termination of a spawned QEMU process.
/// @param pid Process ID of the spawned QEMU process
/// @param force If non-zero, sends SIGKILL; otherwise sends SIGTERM
/// @return 0 on success, -1 on error.
int qemu_terminate_process(pid_t pid, int force);

// MARK: - Display Frame Callback Registration

/// Registers callback for streaming raw SPICE display framebuffers to Metal renderer.
/// @param callback Callback function pointer invoked when a new display frame arrives
/// @param user_data User context pointer passed to callback
void qemu_register_display_callback(QEMUDisplayFrameCallback callback, void *user_data);

#ifdef __cplusplus
}
#endif

#endif /* BOOTSTRAP_BRIDGE_H */
