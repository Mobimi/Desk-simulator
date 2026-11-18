//
//  DarwinRuntimeBridge.h
//  Desk-simulator Engine Layer
//
//  Native iOS/Darwin C runtime probes for JIT (CS_DEBUGGED), Jetsam available
//  memory (os_proc_available_memory), physical footprint, and entitlements.
//

#ifndef DARWIN_RUNTIME_BRIDGE_H
#define DARWIN_RUNTIME_BRIDGE_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/// Checks whether the current iOS process has CS_DEBUGGED enabled via csops()
/// (active under TrollStore, AltJIT, SideStore, or Xcode debugger).
bool desk_is_jit_enabled(void);

/// Returns bytes remaining before iOS Jetsam terminates this process
/// using os_proc_available_memory() on iOS 13+.
uint64_t desk_available_memory_bytes(void);

/// Returns current process physical memory footprint in bytes via Mach TASK_VM_INFO.
uint64_t desk_process_footprint_bytes(void);

/// Returns total physical RAM installed on the device in bytes.
uint64_t desk_physical_memory_bytes(void);

/// Probes whether the process effectively benefits from increased-memory-limit
/// entitlement (gracefully returns false on standard sideloading without crashing).
bool desk_probe_increased_memory_entitlement(void);

/// Probes whether extended-virtual-addressing entitlement is active by testing
/// high virtual address reservation safely without committing physical pages.
bool desk_probe_extended_va_entitlement(void);

#ifdef __cplusplus
}
#endif

#endif /* DARWIN_RUNTIME_BRIDGE_H */
