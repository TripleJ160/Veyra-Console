#include "veyra/diagnostics/HostWaitTrace.h"
#include <windows.h>
#include <cstdio>
#include <cstring>
#include <future>
#include <mutex>
#include <thread>

// Explicitly synthetic positive controls; never gameplay performance evidence.
int main(int argc, char** argv) {
    using namespace veyra::diagnostics;
    const bool requested = argc == 2 && std::strcmp(argv[1], "--enabled") == 0;
    SetEnvironmentVariableW(L"VEYRA_TRACE_HOST_WAITS", requested ? L"1" : nullptr);
    HostWaitSession session;
    if (session.status() || hostWaitEnabled() != requested) return 1;
    LARGE_INTEGER frequency{}, before{}, after{};
    QueryPerformanceFrequency(&frequency);
    QueryPerformanceCounter(&before);
    constexpr unsigned iterations = 1000000;
    for (unsigned i = 0; i < iterations; ++i) {
        HostWaitSpan span("selftest", "emptySpan");
    }
    QueryPerformanceCounter(&after);
    const double ns = double(after.QuadPart-before.QuadPart)*1e9 / frequency.QuadPart / iterations;
    {
        HostWaitContext context({9001, 2, 3});
        HostWaitSpan span("selftest", "Sleep30ms");
        Sleep(30);
    }
    std::mutex mutex;
    std::promise<void> locked;
    auto ready = locked.get_future();
    std::thread holder([&] {
        std::lock_guard lock(mutex);
        locked.set_value();
        Sleep(40);
    });
    ready.wait();
    {
        HostWaitContext context({9002, 2, 3});
        HostWaitSpan span("selftest", "ContendedMutex40ms");
        std::lock_guard lock(mutex);
        span.finish();
    }
    holder.join();
    {
        HostWaitSpan span("selftest", "Busy20ms");
        QueryPerformanceCounter(&before);
        do { QueryPerformanceCounter(&after); }
        while (after.QuadPart-before.QuadPart < frequency.QuadPart/50);
    }
    std::printf("{\"synthetic\":true,\"enabled\":%s,\"iterations\":%u,\"nsPerEmptySpan\":%.3f,\"qpcFrequency\":%lld,\"providerStatus\":%lu}\n",
        requested ? "true" : "false", iterations, ns, frequency.QuadPart, session.status());
}
