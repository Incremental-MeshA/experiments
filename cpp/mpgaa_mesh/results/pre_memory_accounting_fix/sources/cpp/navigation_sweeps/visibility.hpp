#pragma once
#include "ima/model.hpp"

namespace ima::navigation {
struct Run {int di=0,lo=0,hi=0;};
struct Visibility {
    int headings=0,maximum=0;
    std::map<std::pair<int,int>,std::vector<Run>> runs;
    double compilation_s=0;

    static Cell rotate(Cell q,int times){while(times--){int i=q.i;q.i=-q.j;q.j=i;}return q;}
    static bool quarter_symmetric(const Model& m){
        if(m.headings%4)return false;
        using Signature=std::tuple<int,int,int,int,std::vector<Cell>>;
        std::set<Signature> all;
        for(auto& p:m.primitives)all.emplace(p.start,p.end,p.di,p.dj,p.cells);
        for(auto& p:m.primitives){
            auto d=rotate({p.di,p.dj},1);std::vector<Cell> cells;
            for(auto q:p.cells)cells.push_back(rotate(q,1));
            if(!all.count({(p.start+m.headings/4)%m.headings,(p.end+m.headings/4)%m.headings,d.i,d.j,cells}))return false;
        }
        return true;
    }
    static std::vector<Run> encode(const std::vector<std::uint8_t>& depth,int side,int radius,int n){
        std::vector<Run> result;
        for(int i=0;i<side;++i){int j=0;while(j<side){
            while(j<side && depth[std::size_t(i)*side+j]>n)++j;
            if(j==side)break;
            int lo=j;
            while(j+1<side && depth[std::size_t(i)*side+j+1]<=n)++j;
            result.push_back({i-radius,lo-radius,j-radius});++j;
        }}return result;
    }
    static Visibility compile(const Model& m,int max_depth=64){
        require(max_depth>0 && max_depth<255,"invalid visibility depth");auto begin=Clock::now();
        Visibility v;v.headings=m.headings;v.maximum=max_depth;
        int reach=std::max(m.reach_i,m.reach_j),radius=max_depth*reach,side=2*radius+1;
        std::size_t positions=std::size_t(side)*side,states=positions*m.headings;
        require(states<std::numeric_limits<std::uint32_t>::max(),"visibility lattice too large");
        std::vector<std::vector<Cell>> support(m.headings);
        for(int h=0;h<m.headings;++h){std::set<Cell> cells;for(int p:m.by_start[h])cells.insert(m.primitives[p].cells.begin(),m.primitives[p].cells.end());support[h].assign(cells.begin(),cells.end());}
        bool symmetric=quarter_symmetric(m);int base=symmetric ? m.headings/4 : m.headings;
        std::vector<int> depths={1};for(int n=2;n<=max_depth;n*=2)depths.push_back(n);
        if(depths.back()!=max_depth)depths.push_back(max_depth);
        for(int heading=0;heading<base;++heading){
            std::vector<std::uint8_t> distance(states,255),seen(positions,255);
            std::vector<std::uint32_t> queue;queue.reserve(std::min<std::size_t>(states,1000000));
            auto initial=(std::size_t(radius)*side+radius)*m.headings+heading;distance[initial]=0;queue.push_back(std::uint32_t(initial));
            for(std::size_t at=0;at<queue.size();++at){
                std::size_t packed=queue[at],cell=packed/m.headings;int h=int(packed%m.headings),d=distance[packed];
                int i=int(cell/side),j=int(cell%side);
                if(d+1<max_depth)for(int id:m.by_start[h]){
                    auto& p=m.primitives[id];int ni=i+p.di,nj=j+p.dj;
                    require(ni>=0 && nj>=0 && ni<side && nj<side,"visibility bound failed");
                    auto next=(std::size_t(ni)*side+nj)*m.headings+p.end;
                    if(distance[next]==255){distance[next]=std::uint8_t(d+1);queue.push_back(std::uint32_t(next));}
                }
                for(auto off:support[h]){
                    int ni=i+off.i,nj=j+off.j;require(ni>=0 && nj>=0 && ni<side && nj<side,"visibility footprint bound failed");
                    auto next=std::size_t(ni)*side+nj;seen[next]=std::min(seen[next],std::uint8_t(d+1));
                }
            }
            for(int turn=0;turn<(symmetric?4:1);++turn){
                int out_h=heading+turn*base;std::vector<std::uint8_t> rotated;
                if(turn){rotated.assign(positions,255);for(int i=0;i<side;++i)for(int j=0;j<side;++j){
                    auto q=rotate({i-radius,j-radius},turn);rotated[std::size_t(q.i+radius)*side+q.j+radius]=seen[std::size_t(i)*side+j];
                }}
                for(int n:depths)v.runs[{out_h,n}]=encode(turn?rotated:seen,side,radius,n);
            }
        }
        v.compilation_s=seconds(begin);return v;
    }
    void write(const std::string& path)const{
        std::ofstream out(path);require(bool(out),"cannot write visibility");
        out<<"IMA_VIS 1 "<<headings<<' '<<maximum<<' '<<std::setprecision(17)<<compilation_s<<' '<<runs.size()<<'\n';
        for(auto& [key,list]:runs){out<<key.first<<' '<<key.second<<' '<<list.size()<<'\n';for(auto r:list)out<<r.di<<' '<<r.lo<<' '<<r.hi<<'\n';}
    }
    static Visibility read(const std::string& path){
        std::ifstream in(path);std::string tag;int version=0;std::size_t count=0;Visibility v;
        in>>tag>>version>>v.headings>>v.maximum>>v.compilation_s>>count;require(tag=="IMA_VIS" && version==1,"bad visibility header");
        for(std::size_t i=0;i<count;++i){int h,n;std::size_t nr;in>>h>>n>>nr;auto& list=v.runs[{h,n}];list.resize(nr);for(auto& r:list)in>>r.di>>r.lo>>r.hi;}
        require(bool(in),"truncated visibility");return v;
    }
};
}
