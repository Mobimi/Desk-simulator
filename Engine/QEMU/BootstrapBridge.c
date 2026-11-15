//
//  BootstrapBridge.c
//  Desk-simulator Engine Layer
//
//  Reference C-ABI implementation for dynamic QEMU execution and thread bootstrapping.
//

#include "BootstrapBridge.h"
#include <stdbool.h>

static volatile QEMUStatusCode s_status = QEMU_STATUS_STOPPED;
static volatile bool s_exit_requested = false;

int qemu_init(int argc, char **argv, char **envp) {
    (void)argc;
    (void)argv;
    (void)envp;
    s_status = QEMU_STATUS_INITIALIZING;
    s_exit_requested = false;
    s_status = QEMU_STATUS_RUNNING;
    return 0;
}

void qemu_main_loop(void) {
    while (!s_exit_requested && s_status == QEMU_STATUS_RUNNING) {
        // Wait or process internal events
        break;
    }
    s_status = QEMU_STATUS_TERMINATING;
}

int qemu_request_exit(void) {
    s_exit_requested = true;
    s_status = QEMU_STATUS_TERMINATING;
    return 0;
}

void qemu_cleanup(void) {
    s_status = QEMU_STATUS_STOPPED;
    s_exit_requested = false;
}

int qemu_is_running(void) {
    return (s_status == QEMU_STATUS_RUNNING) ? 1 : 0;
}

QEMUStatusCode qemu_get_status(void) {
    return s_status;
}
