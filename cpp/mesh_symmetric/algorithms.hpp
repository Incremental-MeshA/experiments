#pragma once
#include "../mesh_conditional/factory.hpp"
namespace ima::mesh_symmetric {
using mesh_envelope::MeshIndex;
struct Work:mesh_envelope::Work {
    std::uint64_t activated_blocks=0,deferred_block_cells=0,optimistic_rounds=0,path_probes=0,gap_hits=0;
    void add(const Work& b){mesh_envelope::Work::add(b);activated_blocks+=b.activated_blocks;deferred_block_cells+=b.deferred_block_cells;optimistic_rounds+=b.optimistic_rounds;path_probes+=b.path_probes;gap_hits+=b.gap_hits;}
};
// The working graph can be neither a subgraph nor a supergraph of reality.
// A valid working-optimal path is exact only after every still-missing opening
// with mesh detour lower bound <= its cost has been released.
class Symmetric : public Planner {
    const Model& m;const Certificate& cert;Grid actual,working;State goal,previous,no_path;
    bool symmetric,use_gap,mesh_bounds,has_previous=false,has_no_path=false;std::uint64_t limit;
    mpgaa_lazy::LazyMPGAA backend;Suffix suffix;
    CellSet deferred_blocks;CellMap<double> deferred_opens;
    std::priority_queue<std::pair<double,Cell>,std::vector<std::pair<double,Cell>>,std::greater<std::pair<double,Cell>>> waiting;
    std::set<Cell> pending_blocks,pending_opens;
    double travel=0;Stats stats;Work work;
    double bound(State s,Cell q) const {return mesh_bounds?cert.bound(s.cell(),goal.cell(),q):0;}
    void set_working(Cell q,bool blocked) {
        if(working.blocked(q)==blocked)return;
        working.set(q,blocked);
        if(blocked){pending_opens.erase(q);pending_blocks.insert(q);}else{pending_blocks.erase(q);pending_opens.insert(q);}
    }
    bool release(State s,double upper) {
        auto before=stats.activated_cells;double threshold=upper+travel;
        while(!waiting.empty()) {
            auto [key,q]=waiting.top();auto it=deferred_opens.find(q);
            if(it==deferred_opens.end() || it->second!=key){waiting.pop();continue;}
            double guard=std::isfinite(upper)?EPS*(1+std::abs(key)+std::abs(threshold)):0;
            if(std::isfinite(upper) && key>threshold+guard)break;
            waiting.pop();
            if(std::isfinite(upper)) {
                double fresh=bound(s,q)+travel;++stats.refined_cells;guard=EPS*(1+std::abs(fresh)+std::abs(threshold));
                if(fresh>threshold+guard){deferred_opens[q]=fresh;waiting.push({fresh,q});continue;}
            }
            deferred_opens.erase(q);set_working(q,false);++stats.activated_cells;
        }
        return stats.activated_cells!=before;
    }
    bool validate_candidate(const Path& p) {
        if(deferred_blocks.empty())return true;
        std::set<Cell> hit;
        for(std::size_t at=0;at<p.ids.size();++at)for(std::size_t j=1;j<m.primitives[p.ids[at]].cells.size();++j) {
            auto off=m.primitives[p.ids[at]].cells[j];Cell q{p.states[at].i+off.i,p.states[at].j+off.j};
            ++stats.checked_cells;++work.path_probes;
            if(!actual.free(q)){require(deferred_blocks.count(q),"unclassified optimistic obstacle");hit.insert(q);}
        }
        for(Cell q:hit){deferred_blocks.erase(q);set_working(q,true);++work.activated_blocks;}
        return hit.empty();
    }
    Path call(State s) {
        backend.set_limit(limit-stats.expansions);auto p=backend.replan(s,{pending_blocks.begin(),pending_blocks.end()},{pending_opens.begin(),pending_opens.end()});
        pending_blocks.clear();pending_opens.clear();stats.add(p.stats);++stats.backend_calls;
        static_cast<mpgaa_lazy::Work&>(work).add(backend.counters());++work.optimistic_rounds;return p;
    }
public:
    Symmetric(const MeshIndex& index,const Certificate& certificate,const Grid& grid,State t,bool both,std::uint64_t cap,bool gap=true,bool bounds=true)
        :m(index.model),cert(certificate),actual(grid),working(grid),goal(t),symmetric(both),use_gap(both&&gap),mesh_bounds(bounds),limit(cap),backend(index,grid,t,mpgaa_lazy::Mode::Batch,cap),suffix(m) {}
    const Work& counters() const{return work;}
    void set_limit(std::uint64_t cap){limit=cap;}
    Path replan(State s,const std::vector<Cell>& blocks={},const std::vector<Cell>& opens={}) override {
        auto [b,o]=net_changes(actual,blocks,opens);stats={};work={};bool eager_open=false;
        if(mesh_bounds && has_previous && s.cell()!=previous.cell()){double d=cert.distance(s.cell(),previous.cell());travel+=d+EPS*(1+d);}
        has_previous=true;previous=s;suffix.update(b,o);
        for(Cell q:b) {
            actual.set(q,true);deferred_opens.erase(q);
            if(symmetric && working.free(q))deferred_blocks.insert(q);
            else{deferred_blocks.erase(q);bool change=!working.blocked(q);set_working(q,true);if(change)++work.activated_blocks;}
        }
        for(Cell q:o) {
            actual.set(q,false);deferred_blocks.erase(q);
            if(working.blocked(q)) {
                if(mesh_bounds){double key=bound(s,q)+travel;deferred_opens[q]=key;waiting.push({key,q});}
                else{set_working(q,false);++stats.activated_cells;eager_open=true;}
            } else deferred_opens.erase(q);
        }
        if(waiting.size()>2*deferred_opens.size()+64){waiting={};for(const auto& [q,k]:deferred_opens)waiting.push({k,q});}
        Path result,incumbent;std::size_t at=0;
        if(eager_open)has_no_path=false;
        if(!actual.free(s.cell()) || !actual.free(goal.cell())){suffix.install(Path{});goto done;}
        if(has_no_path && s==no_path && deferred_opens.empty()){stats.certified=true;goto done;}
        if(suffix.position(s,at)) {
            incumbent=suffix.tail(at);
            if(!eager_open && !release(s,incumbent.cost)){result=std::move(incumbent);stats.certified=true;goto done;}
        }
        has_no_path=false;
        while(true) {
            if(stats.expansions>=limit){stats.capped=true;break;}
            auto candidate=call(s);if(candidate.stats.capped){stats.capped=true;break;}
            if(!candidate.success()) {
                if(!deferred_opens.empty()){require(release(s,INF),"missing openings not released");continue;}
                has_no_path=true;no_path=s;suffix.install(Path{});break;
            }
            if(use_gap && incumbent.success() && candidate.cost>=incumbent.cost-EPS) {
                if(release(s,incumbent.cost))continue;
                result=std::move(incumbent);stats.certified=true;++work.gap_hits;suffix.install(result);break;
            }
            if(!validate_candidate(candidate))continue;
            if(!incumbent.success() || candidate.cost<incumbent.cost)incumbent=std::move(candidate);
            if(release(s,incumbent.cost))continue;
            result=std::move(incumbent);suffix.install(result);break;
        }
        if(stats.capped){result=Path{};suffix.install(Path{});has_no_path=false;}
    done:
        stats.deferred_cells=deferred_opens.size();work.deferred_block_cells=deferred_blocks.size();result.stats=stats;return result;
    }
    void audit() const {
        backend.audit();
        auto saved=suffix;std::size_t at=0;
        if(saved.position(previous,at)) {
            auto p=saved.tail(at);validate_path(actual,m,previous,goal,p);validate_path(working,m,previous,goal,p);
            auto exact=search("lba",working,m,previous,goal,1000000);
            require(!exact.stats.capped && exact.success() && std::abs(exact.cost-p.cost)<1e-6,"saved incumbent not working-optimal");
        }
        for(int i=0;i<actual.height;++i)for(int j=0;j<actual.width;++j) {
            Cell q{i,j};bool a=actual.blocked(q),w=working.blocked(q);
            require((a&&!w)==bool(deferred_blocks.count(q)),"symmetric block partition");
            require((!a&&w)==bool(deferred_opens.count(q)),"symmetric opening partition");
        }
    }
};
}
