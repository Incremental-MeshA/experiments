#pragma once
#include <cstddef>
#include <cstdlib>
#include <cstdint>
#include <limits>
#include <new>

// Separate profiling binary. Timed binary uses the unmodified system allocator.
namespace allocation_profile {
inline std::size_t live=0,peak=0;
inline void reset_peak() { peak=live; }
}
#ifdef IMA_TRACK_ALLOC
namespace allocation_profile {
struct Header { void* raw; std::size_t bytes; };
inline void* allocate(std::size_t n,std::size_t alignment) {
    if (!n) n=1;
    if (alignment<alignof(std::max_align_t)) alignment=alignof(std::max_align_t);
    if (n>std::numeric_limits<std::size_t>::max()-alignment-sizeof(Header)) throw std::bad_alloc();
    void* raw=std::malloc(n+alignment+sizeof(Header));
    if (!raw) throw std::bad_alloc();
    auto start=reinterpret_cast<std::uintptr_t>(raw)+sizeof(Header);
    auto aligned=(start+alignment-1)&~std::uintptr_t(alignment-1);
    auto* h=reinterpret_cast<Header*>(aligned)-1; h->raw=raw; h->bytes=n;
    live+=n; if (live>peak) peak=live;
    return reinterpret_cast<void*>(aligned);
}
inline void release(void* p) noexcept {
    if (!p) return;
    auto* h=reinterpret_cast<Header*>(p)-1; live-=h->bytes; std::free(h->raw);
}
}
void* operator new(std::size_t n) { return allocation_profile::allocate(n,alignof(std::max_align_t)); }
void* operator new[](std::size_t n) { return ::operator new(n); }
void operator delete(void* p) noexcept { allocation_profile::release(p); }
void operator delete[](void* p) noexcept { ::operator delete(p); }
void operator delete(void* p,std::size_t) noexcept { ::operator delete(p); }
void operator delete[](void* p,std::size_t) noexcept { ::operator delete(p); }
void* operator new(std::size_t n,std::align_val_t a) { return allocation_profile::allocate(n,std::size_t(a)); }
void* operator new[](std::size_t n,std::align_val_t a) { return ::operator new(n,a); }
void operator delete(void* p,std::align_val_t) noexcept { ::operator delete(p); }
void operator delete[](void* p,std::align_val_t) noexcept { ::operator delete(p); }
void operator delete(void* p,std::size_t,std::align_val_t) noexcept { ::operator delete(p); }
void operator delete[](void* p,std::size_t,std::align_val_t) noexcept { ::operator delete(p); }
#endif
