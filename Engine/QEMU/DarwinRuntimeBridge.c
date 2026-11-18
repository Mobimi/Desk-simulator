//
//  DarwinRuntimeBridge.c
//  Desk-simulator Engine Layer
//
//  Native iOS/Darwin C runtime probes for JIT, Jetsam memory, and entitlements.
//

#include "DarwinRuntimeBridge.h"

#ifdef __APPLE__
#include <TargetConditionals.h>
#include <mach/mach.h>
#include <mach/task_info.h>
#include <os/proc.h>
#include <sys/mman.h>
#include <sys/sysctl.h>
#include <unistd.h>

#define DESK_CS_OPS_STATUS 0
#define DESK_CS_DEBUGGED 0x10000000u

extern int csops(pid_t pid, unsigned int ops, void *useraddr, size_t usersize);

bool desk_is_jit_enabled(void) {
#if TARGET_OS_SIMULATOR
    return true;
#else
    uint32_t flags = 0;
    if (csops(getpid(), DESK_CS_OPS_STATUS, &flags, sizeof(flags)) == 0) {
        return (flags & DESK_CS_DEBUGGED) != 0;
    }
    return false;
#endif
}

uint64_t desk_available_memory_bytes(void) {
#if TARGET_OS_IOS
    if (__builtin_available(iOS 13.0, *)) {
        return (uint64_t)os_proc_available_memory();
    }
#endif
    uint64_t total = desk_physical_memory_bytes();
    uint64_t used = desk_process_footprint_bytes();
    uint64_t conservativeCap = total / 2;
    return (conservativeCap > used) ? (conservativeCap - used) : 0;
}

uint64_t desk_process_footprint_bytes(void) {
    task_vm_info_data_t vmInfo;
    mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
    kern_return_t kr = task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&vmInfo, &count);
    if (kr == KERN_SUCCESS) {
        return (uint64_t)vmInfo.phys_footprint;
    }
    return 0;
}

uint64_t desk_physical_memory_bytes(void) {
    uint64_t memsize = 0;
    size_t size = sizeof(memsize);
    if (sysctlbyname("hw.memsize", &memsize, &size, NULL, 0) == 0) {
        return memsize;
    }
    return 4ULL * 1024ULL * 1024ULL * 1024ULL;
}

bool desk_probe_increased_memory_entitlement(void) {
#if TARGET_OS_IOS && !TARGET_OS_SIMULATOR
    uint64_t total = desk_physical_memory_bytes();
    uint64_t avail = desk_available_memory_bytes();
    uint64_t used = desk_process_footprint_bytes();
    uint64_t budget = avail + used;
    if (total > 0) {
        // Without com.apple.developer.kernel.increased-memory-limit, iOS caps
        // per-process Jetsam budget near ~50-60% of physical RAM. With it,
        // budget reaches ~70-80%.
        double ratio = (double)budget / (double)total;
        return ratio >= 0.65;
    }
#endif
    return false;
}

bool desk_probe_extended_va_entitlement(void) {
#if TARGET_OS_IOS && !TARGET_OS_SIMULATOR
    // Attempt a non-committed PROT_NONE virtual reservation of 6 GB.
    // Standard iOS virtual address space is ~5-6GB; extended-virtual-addressing
    // raises VA space to 64GB+. PROT_NONE consumes zero physical RAM.
    const size_t probeSize = (size_t)6ULL * 1024ULL * 1024ULL * 1024ULL;
    void *ptr = mmap(NULL, probeSize, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (ptr != MAP_FAILED) {
        munmap(ptr, probeSize);
        return true;
    }
    return false;
#else
    return false;
#endif
}

#else

bool desk_is_jit_enabled(void) { return false; }
uint64_t desk_available_memory_bytes(void) { return 2ULL * 1024ULL * 1024ULL * 1024ULL; }
uint64_t desk_process_footprint_bytes(void) { return 128ULL * 1024ULL * 1024ULL; }
uint64_t desk_physical_memory_bytes(void) { return 6ULL * 1024ULL * 1024ULL * 1024ULL; }
bool desk_probe_increased_memory_entitlement(void) { return false; }
bool desk_probe_extended_va_entitlement(void) { return false; }

#endif
