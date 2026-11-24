//! Keeps Windows from treating the search as background work.
//!
//! On hybrid Intel CPUs (performance plus efficiency cores), Windows 11 gives
//! a process with no foreground window "EcoQoS" and schedules its threads on
//! the efficiency cores only. A run started over SSH or WMI has no window, so
//! on an i7-14700F it used the 12 E-cores while the 8 P-cores sat idle
//! (measured 2026-11-19: 43% total CPU, 12 threads waiting). Opting out of
//! execution-speed throttling lets the scheduler use every core.
//! API: SetProcessInformation with ProcessPowerThrottling (Microsoft docs,
//! "PROCESS_POWER_THROTTLING_STATE").

#[cfg(windows)]
pub fn use_all_cores() {
    use std::ffi::c_void;
    #[repr(C)]
    struct PowerThrottlingState {
        version: u32,
        control_mask: u32,
        state_mask: u32,
    }
    const PROCESS_POWER_THROTTLING: i32 = 4; // PROCESS_INFORMATION_CLASS::ProcessPowerThrottling
    const CURRENT_VERSION: u32 = 1; // PROCESS_POWER_THROTTLING_CURRENT_VERSION
    const EXECUTION_SPEED: u32 = 1; // PROCESS_POWER_THROTTLING_EXECUTION_SPEED
    extern "system" {
        fn GetCurrentProcess() -> *mut c_void;
        fn SetProcessInformation(process: *mut c_void, class: i32, info: *const c_void, size: u32) -> i32;
    }
    // control the execution-speed policy and set it off: never throttle
    let state = PowerThrottlingState { version: CURRENT_VERSION, control_mask: EXECUTION_SPEED, state_mask: 0 };
    let size = std::mem::size_of::<PowerThrottlingState>() as u32;
    // SAFETY: GetCurrentProcess returns a pseudo-handle that needs no closing, and
    // `state` is a live PROCESS_POWER_THROTTLING_STATE of the size passed.
    let ok = unsafe { SetProcessInformation(GetCurrentProcess(), PROCESS_POWER_THROTTLING, (&state as *const PowerThrottlingState).cast(), size) };
    if ok == 0 {
        eprintln!("note: could not opt out of Windows power throttling; the search may use only efficiency cores");
    }
}

#[cfg(not(windows))]
pub fn use_all_cores() {}
