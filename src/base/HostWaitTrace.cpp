#include "veyra/diagnostics/HostWaitTrace.h"
#include <windows.h>
#include <TraceLoggingProvider.h>
#include <atomic>

TRACELOGGING_DEFINE_PROVIDER(g_veyraHostWait, "Veyra.HostWait.5090",
    (0x4afbb638, 0x7834, 0x4f9c, 0xa7, 0xab, 0x8f, 0x64, 0x2e, 0x71, 0xa9, 0x05));

namespace veyra::diagnostics {
namespace {
std::atomic<bool> enabled{false};
int64_t frequency = 0;
thread_local HostWaitIdentity identity;
}
HostWaitSession::HostWaitSession() noexcept {
    wchar_t flag[2]{};
    if (GetEnvironmentVariableW(L"VEYRA_TRACE_HOST_WAITS", flag, 2) != 1 || flag[0] != L'1') return;
    LARGE_INTEGER f{};
    if (!QueryPerformanceFrequency(&f)) { status_ = GetLastError(); return; }
    frequency = f.QuadPart;
    status_ = TraceLoggingRegister(g_veyraHostWait);
    if (status_ != ERROR_SUCCESS) return;
    registered_ = true;
    enabled.store(true, std::memory_order_release);
    TraceLoggingWrite(g_veyraHostWait, "HostWaitConfig", TraceLoggingKeyword(1),
        TraceLoggingInt64(frequency, "QpcFrequency"), TraceLoggingUInt32(5, "ThresholdMs"),
        TraceLoggingUInt32(GetCurrentProcessId(), "Pid"));
}
HostWaitSession::~HostWaitSession() {
    if (!registered_) return;
    enabled.store(false, std::memory_order_release);
    TraceLoggingUnregister(g_veyraHostWait);
}
bool hostWaitEnabled() noexcept { return enabled.load(std::memory_order_acquire); }
int64_t hostWaitNow() noexcept {
    if (!hostWaitEnabled()) return 0;
    LARGE_INTEGER q{}; QueryPerformanceCounter(&q); return q.QuadPart;
}
void hostWaitRecord(const char* area, const char* operation, int64_t start, int64_t end,
                    uint64_t loop, int64_t result) noexcept {
    if (!start || !hostWaitEnabled() || end < start || frequency <= 0) return;
    // Filter before EventWrite. Do not report wall time as CPU running time.
    if (end - start < frequency / 200) return;
    TraceLoggingWrite(g_veyraHostWait, "HostWaitSpan", TraceLoggingKeyword(1),
        TraceLoggingString(area, "Area"), TraceLoggingString(operation, "Operation"),
        TraceLoggingInt64(start, "StartQpc"), TraceLoggingInt64(end, "EndQpc"),
        TraceLoggingFloat64(double(end-start)*1000.0/double(frequency), "WallMs"),
        TraceLoggingUInt32(GetCurrentThreadId(), "Tid"), TraceLoggingUInt64(loop, "Loop"),
        TraceLoggingUInt64(identity.source, "Source"), TraceLoggingUInt64(identity.epoch, "Epoch"),
        TraceLoggingUInt64(identity.revision, "Revision"), TraceLoggingInt64(result, "Result"));
}
HostWaitContext::HostWaitContext(HostWaitIdentity value) noexcept : previous_(identity) { identity = value; }
HostWaitContext::~HostWaitContext() { identity = previous_; }
}
