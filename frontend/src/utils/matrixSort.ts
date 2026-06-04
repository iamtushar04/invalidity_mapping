/**
 * Sorts matrix rows by the number of Ys (first), then Ps (second), then Ns.
 * Rows with more Ys appear higher. If tied, rows with more Ps appear higher.
 */
export function sortMatrixRows(rows: any[]) {
  return [...rows].sort((a: any, b: any) => {
    // Safely fallback to empty array if mappings are undefined
    const aMappings = a.mappings || [];
    const bMappings = b.mappings || [];

    const aY = aMappings.filter((m: any) => m.classification === "Y").length;
    const aP = aMappings.filter((m: any) => m.classification === "P" || m.classification === "Partial").length;
    
    const bY = bMappings.filter((m: any) => m.classification === "Y").length;
    const bP = bMappings.filter((m: any) => m.classification === "P" || m.classification === "Partial").length;
    
    if (aY !== bY) {
      return bY - aY; // Highest Y wins
    }
    
    if (aP !== bP) {
      return bP - aP; // If Y tied, highest P wins
    }

    // Fallback to score if everything else is perfectly tied
    return (b.score || 0) - (a.score || 0);
  });
}
