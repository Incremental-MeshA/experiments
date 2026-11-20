#pragma once
#include "ima/model.hpp"
#include <numeric>

namespace ima::navigation {
struct Spec {
    std::string id,kind;int radius=0,k=0,cr=0,n=0,max_moves=0,repeats=1;std::uint64_t seed=0;bool trace=false;
};
inline std::map<std::string,Spec> read_specs(const std::string& path){
    std::ifstream in(path);std::string tag;int version=0;std::size_t count=0;in>>tag>>version>>count;
    require(tag=="NAV_SPEC" && version==1,"bad scenario header");std::map<std::string,Spec> result;
    for(std::size_t i=0;i<count;++i){Spec s;int trace=0;in>>std::quoted(s.id)>>s.kind>>s.radius>>s.k>>s.cr>>s.n>>s.max_moves>>s.repeats>>s.seed>>trace;s.trace=trace;
        require((s.kind=="unknown" && s.radius>=1) || (s.kind=="dynamic" && s.k>0 && s.n==s.k && s.cr>0),"invalid scenario");
        require(s.max_moves>0 && s.repeats>0 && result.emplace(s.id,s).second,"duplicate/invalid scenario");
    }require(bool(in),"truncated scenario specifications");return result;
}
struct Random {
    std::uint64_t state;
    std::uint64_t next(){state+=0x9e3779b97f4a7c15ULL;auto z=state;z=(z^(z>>30))*0xbf58476d1ce4e5b9ULL;z=(z^(z>>27))*0x94d049bb133111ebULL;return z^(z>>31);}
    std::size_t below(std::size_t n){require(n>0,"empty random range");std::uint64_t threshold=(std::uint64_t(0)-n)%n,r;do{r=next();}while(r<threshold);return r%n;}
};
struct Calendar {
    std::size_t cells;std::uint64_t seed;std::map<int,std::vector<std::uint32_t>> priorities;
    const std::vector<std::uint32_t>& phase(int number){
        auto [it,inserted]=priorities.try_emplace(number);
        if(inserted){auto& p=it->second;p.resize(cells);std::iota(p.begin(),p.end(),0);Random rng{mix(seed^mix(std::uint64_t(number)))};
            for(std::size_t i=p.size();i>1;--i)std::swap(p[i-1],p[rng.below(i)]);
        }return it->second;
    }
};
struct Phase {
    std::size_t requested_half=0,actual_half=0;bool clamped=false;std::uint64_t hash=0;
};
struct World {
    Grid truth,belief;std::vector<std::uint8_t> seen;
    std::size_t blocked=0,known=0,mismatch=0;std::uint64_t world_hash=0,belief_hash=0;
    explicit World(const Grid& initial,bool unknown):truth(initial),belief(unknown?Grid(initial.height,initial.width):initial),seen(initial.cells.size(),unknown?0:1){
        for(std::size_t i=0;i<truth.cells.size();++i)if(truth.cells[i]){++blocked;world_hash^=mix(i+0x786e6176ULL);}
        known=unknown?0:seen.size();mismatch=unknown?blocked:0;belief_hash=unknown?0:world_hash;
    }
    std::size_t index(Cell q)const{return std::size_t(q.i)*truth.width+q.j;}
    Phase change(Calendar& calendar,int phase,int cr,Cell agent,Cell goal){
        require(truth.free(agent) && truth.free(goal),"invalid phase endpoints");
        Phase event;event.requested_half=std::size_t(std::floor(double(truth.cells.size())*cr/200+.5));
        std::size_t protected_cells=agent==goal?1:2;
        event.actual_half=std::min({event.requested_half,blocked,truth.cells.size()-blocked-protected_cells});event.clamped=event.actual_half<event.requested_half;
        std::vector<std::uint32_t> b,o;b.reserve(event.actual_half);o.reserve(event.actual_half);
        auto a=index(agent),g=index(goal);
        for(auto q:calendar.phase(phase)){
            if(q==a || q==g)continue;
            if(truth.cells[q]){if(o.size()<event.actual_half)o.push_back(q);}
            else if(b.size()<event.actual_half)b.push_back(q);
            if(b.size()==event.actual_half && o.size()==event.actual_half)break;
        }
        require(b.size()==o.size() && b.size()==event.actual_half,"phase pool accounting failed");
        // Both lists are selected from the pre-phase world; a new block cannot
        // be selected for reopening in the same phase. Density is preserved.
        for(const auto* list:{&b,&o})for(auto q:*list){
            bool old=truth.cells[q]!=belief.cells[q];truth.cells[q]^=1;
            bool now=truth.cells[q]!=belief.cells[q];if(now && !old)++mismatch;else if(old && !now)--mismatch;
            world_hash^=mix(std::uint64_t(q)+0x786e6176ULL);
        }
        event.hash=world_hash;return event;
    }
    struct Observation {std::vector<Cell> blocks,opens;std::size_t probes=0,newly=0;};
    void observe_cell(int i,int j,Observation& out){
        auto q=std::size_t(i)*truth.width+j;++out.probes;
        if(!seen[q]){seen[q]=1;++known;++out.newly;}
        if(truth.cells[q]!=belief.cells[q]){
            (truth.cells[q]?out.blocks:out.opens).push_back({i,j});belief.cells[q]=truth.cells[q];--mismatch;belief_hash^=mix(q+0x786e6176ULL);
        }
    }
    Observation square(State s,int radius){
        Observation out;
        for(int i=std::max(0,s.i-radius);i<=std::min(truth.height-1,s.i+radius);++i)
            for(int j=std::max(0,s.j-radius);j<=std::min(truth.width-1,s.j+radius);++j)observe_cell(i,j,out);
        return out;
    }
    template<class Runs> Observation stencil(State s,const Runs& runs){
        Observation out;
        for(auto r:runs){int i=s.i+r.di;if(i<0 || i>=truth.height)continue;
            int lo=std::max(0,s.j+r.lo),hi=std::min(truth.width-1,s.j+r.hi);
            for(int j=lo;j<=hi;++j)observe_cell(i,j,out);
        }return out;
    }
};
}
