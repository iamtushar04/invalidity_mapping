import React, { useState } from 'react';
import { Table as TableIcon, LayoutPanelLeft } from 'lucide-react';
import Tooltip from '@/components/Tooltip';
import { getCellColor } from '@/utils';

interface MatrixTableProps {
  matrixData: any;
  filteredRows: any[];
  selectedMatrixPatents: any[];
  handleToggleMatrixPatent: (row: any) => void;
  handleCreateMultipleCharts: () => void;
  chartStatuses?: Record<string, string>;
  handleViewChart?: (refPatentId: string, patentNumber: string) => void;
  handleDownloadReport?: (format: string, refId?: string, refNum?: string) => void;
}

export default function MatrixTable({
  matrixData,
  filteredRows,
  selectedMatrixPatents,
  handleToggleMatrixPatent,
  handleCreateMultipleCharts,
  chartStatuses = {},
  handleViewChart,
  handleDownloadReport
}: MatrixTableProps) {
  const [isColumnsCollapsed, setIsColumnsCollapsed] = useState(false);

  // Helper to extract unique, mathematically-sorted column headers
  const getUniqueSortedColumns = () => {
    if (!matrixData?.rows?.length) return [];
    
    // Extract mappings from all rows to ensure we get all columns even if the first row is pending/failed
    const uniqueMap = new Map();
    matrixData.rows.forEach((row: any) => {
      (row.mappings || []).forEach((m: any) => {
        if (m?.element_id && !uniqueMap.has(m.element_id)) {
          uniqueMap.set(m.element_id, m);
        }
      });
    });

    const uniqueCols = Array.from(uniqueMap.values());
    
    // Sort mathematically (e.g., 1, 2, 10, 11) using localeCompare with numeric=true
    return uniqueCols.sort((a, b) => {
      const idA = String(a.element_id || "");
      const idB = String(b.element_id || "");
      return idA.localeCompare(idB, undefined, { numeric: true, sensitivity: 'base' });
    });
  };

  const columns = getUniqueSortedColumns();

  return (
    <div className="bg-slate-950/40 border border-slate-800 rounded-2xl overflow-hidden flex flex-col relative w-full">
      <div className="p-3 bg-slate-900/60 border-b border-slate-800 flex justify-between items-center">
        <button 
          onClick={() => setIsColumnsCollapsed(!isColumnsCollapsed)}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-xs font-semibold text-slate-300 hover:text-indigo-400 hover:border-indigo-500/50 transition"
        >
          <LayoutPanelLeft className="w-4 h-4" />
          {isColumnsCollapsed ? "Show Patent Details" : "Hide Patent Details"}
        </button>

        <button 
          onClick={handleCreateMultipleCharts}
          disabled={selectedMatrixPatents.length === 0}
          className="bg-indigo-600 disabled:opacity-50 hover:bg-indigo-500 px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1 transition"
        >
          <TableIcon className="w-3 h-3" /> 
          Create Chart {selectedMatrixPatents.length > 0 ? `(${selectedMatrixPatents.length})` : ''}
        </button>
      </div>

      <div className="overflow-x-auto relative">
        <table className="w-full text-left border-collapse min-w-max">
          <thead>
            <tr className="border-b border-slate-800 bg-slate-900/60 font-mono text-xs uppercase text-slate-400">
              {/* Sticky Checkbox */}
              <th className="p-2 border-r border-slate-800/50 w-24 text-center text-[10px]">
                CHART
              </th>
              
              {!isColumnsCollapsed && (
                <>
                  <th className="p-4 w-64 bg-slate-900/30">Prior Art Patent</th>
                  <th className="p-4 text-center w-24 bg-slate-900/30" title="Mathematical keyword/vector similarity score before LLM review">
                    Vector Score
                  </th>
                </>
              )}

              {columns.map((m: any) => (
                <th key={m.element_id} className="p-4 text-center w-16">
                  <Tooltip content={m.element_text || "No text available"} width="w-64" position="bottom">
                    <span className="cursor-help border-b border-dashed border-slate-600 hover:text-white transition-colors">{m.element_id}</span>
                  </Tooltip>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 text-sm">
            {filteredRows?.map((row: any) => {
              const status = chartStatuses[row.reference_patent_id] || "none";
              return (
              <tr key={row.reference_patent_id} className="hover:bg-slate-900/30 transition-colors">
                <td className="p-2 border-r border-slate-800/50 text-center w-36">
                  {status === "processing" || status === "pending" ? (
                    <span className="text-[10px] bg-slate-800 text-indigo-400 px-2 py-1 rounded-full animate-pulse border border-slate-700 whitespace-nowrap">
                      ⚙️ Generating...
                    </span>
                  ) : status === "done" ? (
                    <div className="flex flex-col items-center gap-1">
                      <button 
                        onClick={() => handleViewChart && handleViewChart(row.reference_patent_id, row.patent_number)}
                        className="text-[10px] w-full bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 px-2 py-1 rounded border border-emerald-500/30 transition whitespace-nowrap"
                      >
                        📊 View Chart
                      </button>
                      <button 
                        onClick={() => handleDownloadReport && handleDownloadReport('pdf', row.reference_patent_id, row.patent_number)}
                        className="text-[10px] w-full bg-slate-800 text-slate-300 hover:bg-slate-700 px-2 py-1 rounded border border-slate-700 transition whitespace-nowrap"
                      >
                        📄 Download PDF
                      </button>
                    </div>
                  ) : (
                    <input 
                      type="checkbox"
                      checked={!!selectedMatrixPatents.find((p: any) => p.reference_patent_id === row.reference_patent_id)}
                      onChange={() => handleToggleMatrixPatent(row)}
                      className="w-4 h-4 accent-indigo-500 rounded cursor-pointer mx-auto block"
                    />
                  )}
                </td>

                {!isColumnsCollapsed && (
                  <>
                    <td className="p-4 bg-slate-950/20">
                      <span className="font-mono font-bold text-slate-300">{row.patent_number}</span>
                      <div className="text-xxs text-slate-500 font-semibold truncate max-w-xs">{row.title}</div>
                    </td>
                    <td className="p-4 text-center bg-slate-950/20">
                      <span className={`px-2 py-0.5 rounded font-mono font-bold ${row.score >= 80
                        ? "bg-emerald-500/10 text-emerald-400"
                        : row.score >= 50
                          ? "bg-amber-500/10 text-amber-400"
                          : "bg-rose-500/10 text-rose-400"
                        }`}>
                        {row.score.toFixed(1)}
                      </span>
                    </td>
                  </>
                )}

                {columns.map((col: any) => {
                  // Safely find the matching cell for this column, ignoring duplicates
                  const cell = row?.mappings?.find((m: any) => m.element_id === col.element_id);
                  const classification = cell?.analyst_classification || cell?.classification || "N";
                  const fallbackText = classification === "N" 
                    ? "No relevant passage found." 
                    : "Passage retrieved but pending persistence. Generate chart to view.";
                  
                  return (
                    <td key={col.element_id} className="p-4 text-center">
                      <Tooltip content={cell?.cited_passage || fallbackText} width="w-72" position="bottom">
                        <span className={`w-8 h-8 rounded-lg flex items-center justify-center mx-auto text-xxs font-bold border transition hover:scale-105 z-10 ${getCellColor(classification)}`}>
                          {classification}
                        </span>
                      </Tooltip>
                    </td>
                  );
                })}
              </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
