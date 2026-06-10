import React, { useState } from 'react';
import { ChevronLeft, ChevronRight, Filter } from 'lucide-react';

interface FilterSidebarProps {
  FilteredMatrix: any[];
  matrixFilter: string;
  setMatrixFilter: (id: string) => void;
}

export default function FilterSidebar({ FilteredMatrix, matrixFilter, setMatrixFilter }: FilterSidebarProps) {
  const [isCollapsed, setIsCollapsed] = useState(false);

  return (
    <div className={`transition-all duration-300 ${isCollapsed ? 'w-14' : 'w-64'} shrink-0 flex flex-col gap-4 border-r border-slate-800/60 pr-4 sticky top-6 self-start max-h-[calc(100vh-3rem)] overflow-y-auto`}>
       <div className="flex items-center justify-between">
          {!isCollapsed && <h3 className="font-bold text-xs uppercase tracking-widest font-mono text-slate-400">Filter Matrix</h3>}
          {isCollapsed && <Filter className="w-5 h-5 text-slate-500 mx-auto" />}
          
          <button 
            onClick={() => setIsCollapsed(!isCollapsed)} 
            className="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-400 transition ml-auto"
            title={isCollapsed ? "Expand Filters" : "Collapse Filters"}
          >
             {isCollapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
          </button>
       </div>

       {!isCollapsed && (
         <div className="space-y-3 mt-2">
           {FilteredMatrix?.map((f: any) => (
             <div
               key={f?.filterId}
               onClick={() => setMatrixFilter(f?.filterId)}
               className={`p-3 rounded-xl border cursor-pointer transition-all text-xs font-semibold ${
                 matrixFilter === f?.filterId
                   ? "bg-indigo-600/10 border-indigo-500 text-indigo-300"
                   : "bg-slate-900/40 border-slate-800 hover:border-slate-700 text-slate-400"
               }`}
             >
               {f?.label}
             </div>
           ))}
         </div>
       )}
    </div>
  );
}
