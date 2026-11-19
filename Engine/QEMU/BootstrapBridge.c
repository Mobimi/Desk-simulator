//
//  BootstrapBridge.c
//  Desk-simulator Engine Layer
//
//  Native C-ABI implementation for dynamic QEMU execution, dedicated thread
//  bootstrapping with 4MB+ stack & Mach QoS, POSIX process lifecycle, and display callbacks.
//

#include "BootstrapBridge.h"
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

// Cross-platform threading detection
#if defined(__APPLE__) || defined(__unix__) || defined(__linux__) || (defined(_POSIX_THREADS) && !defined(_WIN32))
#define DESK_HAS_PTHREADS 1
#include <pthread.h>
#if defined(__APPLE__)
#include <pthread/qos.h>
#include <sys/qos.h>
#endif
#endif

// Cross-platform POSIX spawn & process management
#if defined(__APPLE__) || defined(__unix__) || defined(__linux__) || (defined(_POSIX_VERSION) && !defined(_WIN32))
#define DESK_HAS_POSIX_SPAWN 1
#include <signal.h>
#include <spawn.h>
#include <sys/wait.h>
#include <unistd.h>
#if defined(__APPLE__)
#include <crt_externs.h>
#define environ (*_NSGetEnviron())
#else
extern char **environ;
#endif
#endif

// =========================================================================
// Global Engine State
// =========================================================================

static volatile QEMUStatusCode s_status = QEMU_STATUS_STOPPED;
static volatile bool s_exit_requested = false;

#if defined(DESK_HAS_PTHREADS)
static pthread_mutex_t s_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t s_cond = PTHREAD_COND_INITIALIZER;
static pthread_t s_bootstrap_thread;
static bool s_bootstrap_thread_active = false;
#endif

static QEMUDisplayFrameCallback s_display_callback = NULL;
static void *s_display_user_data = NULL;

// =========================================================================
// Architecture Validation Helpers
// =========================================================================

static bool desk_is_target_whitelisted(const char *target) {
    if (!target) {
        return false;
    }
    // Strict whitelist: x86_64-softmmu and aarch64-softmmu (and canonical aliases)
    if (strcmp(target, "x86_64") == 0 ||
        strcmp(target, "x86_64-softmmu") == 0 ||
        strcmp(target, "qemu-system-x86_64") == 0) {
        return true;
    }
    if (strcmp(target, "aarch64") == 0 ||
        strcmp(target, "arm64") == 0 ||
        strcmp(target, "aarch64-softmmu") == 0 ||
        strcmp(target, "qemu-system-aarch64") == 0) {
        return true;
    }
    return false;
}

static bool desk_is_forbidden_arch(const char *str) {
    if (!str) {
        return false;
    }
    const char *forbidden[] = {
        "mips", "ppc", "sparc", "riscv", "s390x",
        "i386", "m68k", "sh4", "xtensa", "cris", "alpha",
        NULL
    };
    for (int i = 0; forbidden[i] != NULL; i++) {
        if (strstr(str, forbidden[i]) != NULL) {
            return true;
        }
    }
    // Check 32-bit arm only if not arm64
    if (strstr(str, "arm") != NULL && strstr(str, "arm64") == NULL) {
        return true;
    }
    return false;
}

// =========================================================================
// Core QEMU Lifecycle Implementation
// =========================================================================

int qemu_init(int argc, char **argv, char **envp) {
    (void)envp;

#if defined(DESK_HAS_PTHREADS)
    pthread_mutex_lock(&s_mutex);
#endif

    s_status = QEMU_STATUS_INITIALIZING;
    s_exit_requested = false;

    // Check if argv specifies a forbidden architecture binary
    if (argv && argc > 0 && argv[0] != NULL) {
        if (desk_is_forbidden_arch(argv[0])) {
            s_status = QEMU_STATUS_ERROR;
#if defined(DESK_HAS_PTHREADS)
            pthread_mutex_unlock(&s_mutex);
#endif
            return -1;
        }
    }

    s_status = QEMU_STATUS_RUNNING;

#if defined(DESK_HAS_PTHREADS)
    pthread_cond_broadcast(&s_cond);
    pthread_mutex_unlock(&s_mutex);
#endif

    return 0;
}

int qemu_init_target(const char *target, int argc, char **argv, char **envp) {
    if (!desk_is_target_whitelisted(target)) {
#if defined(DESK_HAS_PTHREADS)
        pthread_mutex_lock(&s_mutex);
#endif
        s_status = QEMU_STATUS_ERROR;
#if defined(DESK_HAS_PTHREADS)
        pthread_mutex_unlock(&s_mutex);
#endif
        return -1;
    }

    return qemu_init(argc, argv, envp);
}

void qemu_main_loop(void) {
#if defined(DESK_HAS_PTHREADS)
    pthread_mutex_lock(&s_mutex);

    while (!s_exit_requested && (s_status == QEMU_STATUS_RUNNING || s_status == QEMU_STATUS_PAUSED)) {
        if (s_status == QEMU_STATUS_PAUSED) {
            pthread_cond_wait(&s_cond, &s_mutex);
            continue;
        }

        // Active run loop tick (simulates event processing with 20ms cadence)
        struct timespec ts;
        clock_gettime(CLOCK_REALTIME, &ts);
        ts.tv_nsec += 20000000L; // 20ms
        if (ts.tv_nsec >= 1000000000L) {
            ts.tv_sec += 1;
            ts.tv_nsec -= 1000000000L;
        }
        pthread_cond_timedwait(&s_cond, &s_mutex, &ts);
    }

    s_status = QEMU_STATUS_TERMINATING;
    pthread_mutex_unlock(&s_mutex);
#else
    while (!s_exit_requested && s_status == QEMU_STATUS_RUNNING) {
        break;
    }
    s_status = QEMU_STATUS_TERMINATING;
#endif
}

int qemu_request_exit(void) {
#if defined(DESK_HAS_PTHREADS)
    pthread_mutex_lock(&s_mutex);
#endif

    s_exit_requested = true;
    if (s_status == QEMU_STATUS_RUNNING || s_status == QEMU_STATUS_PAUSED) {
        s_status = QEMU_STATUS_TERMINATING;
    }

#if defined(DESK_HAS_PTHREADS)
    pthread_cond_broadcast(&s_cond);
    pthread_mutex_unlock(&s_mutex);
#endif

    return 0;
}

void qemu_cleanup(void) {
#if defined(DESK_HAS_PTHREADS)
    pthread_mutex_lock(&s_mutex);
#endif

    s_status = QEMU_STATUS_STOPPED;
    s_exit_requested = false;

#if defined(DESK_HAS_PTHREADS)
    pthread_cond_broadcast(&s_cond);
    pthread_mutex_unlock(&s_mutex);
#endif
}

int qemu_is_running(void) {
#if defined(DESK_HAS_PTHREADS)
    pthread_mutex_lock(&s_mutex);
#endif

    int running = (s_status == QEMU_STATUS_RUNNING) ? 1 : 0;

#if defined(DESK_HAS_PTHREADS)
    pthread_mutex_unlock(&s_mutex);
#endif

    return running;
}

QEMUStatusCode qemu_get_status(void) {
#if defined(DESK_HAS_PTHREADS)
    pthread_mutex_lock(&s_mutex);
#endif

    QEMUStatusCode status = s_status;

#if defined(DESK_HAS_PTHREADS)
    pthread_mutex_unlock(&s_mutex);
#endif

    return status;
}

// =========================================================================
// Dedicated Pthread Execution Hooks
// =========================================================================

#if defined(DESK_HAS_PTHREADS)
static void *desk_qemu_thread_entry(void *arg) {
    (void)arg;
#if defined(__APPLE__)
    // Elevate Mach QoS to User Interactive on Apple Silicon / Darwin
    pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE, 0);
#endif
    qemu_main_loop();
    return NULL;
}
#endif

int qemu_bootstrap_start_thread(int argc, char **argv, char **envp) {
#if defined(DESK_HAS_PTHREADS)
    pthread_mutex_lock(&s_mutex);
    if (s_bootstrap_thread_active) {
        pthread_mutex_unlock(&s_mutex);
        return EBUSY;
    }

    if (s_status != QEMU_STATUS_RUNNING) {
        s_status = QEMU_STATUS_INITIALIZING;
        s_exit_requested = false;
        if (argv && argc > 0 && argv[0] != NULL) {
            if (desk_is_forbidden_arch(argv[0])) {
                s_status = QEMU_STATUS_ERROR;
                pthread_mutex_unlock(&s_mutex);
                return -1;
            }
        }
        s_status = QEMU_STATUS_RUNNING;
    }
    (void)envp;

    pthread_attr_t attr;
    int ret = pthread_attr_init(&attr);
    if (ret != 0) {
        pthread_mutex_unlock(&s_mutex);
        return ret;
    }

    // Set stack size to 4MB (4 * 1024 * 1024 bytes)
    size_t stack_size = 4 * 1024 * 1024;
    pthread_attr_setstacksize(&attr, stack_size);

    // Apply User Interactive Mach QoS on Darwin
#if defined(__APPLE__)
    pthread_attr_set_qos_class_np(&attr, QOS_CLASS_USER_INTERACTIVE, 0);
#endif

    ret = pthread_create(&s_bootstrap_thread, &attr, desk_qemu_thread_entry, NULL);
    pthread_attr_destroy(&attr);

    if (ret == 0) {
        s_bootstrap_thread_active = true;
    }

    pthread_mutex_unlock(&s_mutex);
    return ret;
#else
    (void)argc;
    (void)argv;
    (void)envp;
    return -1;
#endif
}

int qemu_bootstrap_join_thread(void) {
#if defined(DESK_HAS_PTHREADS)
    pthread_mutex_lock(&s_mutex);
    if (!s_bootstrap_thread_active) {
        pthread_mutex_unlock(&s_mutex);
        return 0;
    }
    pthread_t thread = s_bootstrap_thread;
    pthread_mutex_unlock(&s_mutex);

    void *result = NULL;
    int ret = pthread_join(thread, &result);

    pthread_mutex_lock(&s_mutex);
    s_bootstrap_thread_active = false;
    pthread_mutex_unlock(&s_mutex);

    return ret;
#else
    return 0;
#endif
}

// =========================================================================
// Out-of-Process POSIX Spawn Hooks
// =========================================================================

#if defined(DESK_HAS_POSIX_SPAWN)

pid_t qemu_spawn_process(const char *executable, int argc, char **argv, char **envp) {
    if (!executable || !argv) {
        return (pid_t)-1;
    }
    (void)argc;
    pid_t pid = (pid_t)-1;
    char **effective_env = envp ? envp : environ;

    int ret = posix_spawn(&pid, executable, NULL, NULL, argv, effective_env);
    if (ret != 0) {
        return (pid_t)-1;
    }
    return pid;
}

int qemu_poll_process(pid_t pid, int *exit_code) {
    if (pid <= 0) {
        if (exit_code) *exit_code = -1;
        return -1;
    }

    int status = 0;
    pid_t res = waitpid(pid, &status, WNOHANG);

    if (res == 0) {
        // Process is still running
        return 1;
    } else if (res == pid) {
        // Process has terminated
        if (exit_code) {
            if (WIFEXITED(status)) {
                *exit_code = WEXITSTATUS(status);
            } else if (WIFSIGNALED(status)) {
                *exit_code = 128 + WTERMSIG(status);
            } else {
                *exit_code = status;
            }
        }
        return 0;
    } else {
        // Error or process does not exist
        if (exit_code) *exit_code = -1;
        return -1;
    }
}

int qemu_terminate_process(pid_t pid, int force) {
    if (pid <= 0) {
        return -1;
    }
    int sig = (force != 0) ? SIGKILL : SIGTERM;
    return kill(pid, sig);
}

#else

pid_t qemu_spawn_process(const char *executable, int argc, char **argv, char **envp) {
    (void)executable;
    (void)argc;
    (void)argv;
    (void)envp;
    return (pid_t)-1;
}

int qemu_poll_process(pid_t pid, int *exit_code) {
    (void)pid;
    if (exit_code) *exit_code = -1;
    return -1;
}

int qemu_terminate_process(pid_t pid, int force) {
    (void)pid;
    (void)force;
    return -1;
}

#endif

// =========================================================================
// Display Frame Callback Registration
// =========================================================================

void qemu_register_display_callback(QEMUDisplayFrameCallback callback, void *user_data) {
#if defined(DESK_HAS_PTHREADS)
    pthread_mutex_lock(&s_mutex);
#endif

    s_display_callback = callback;
    s_display_user_data = user_data;

#if defined(DESK_HAS_PTHREADS)
    pthread_mutex_unlock(&s_mutex);
#endif
}
