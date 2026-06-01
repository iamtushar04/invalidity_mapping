export const getCellColor = (classification: string) => {
    switch (classification) {
        case "Y": return "bg-emerald-500/20 text-emerald-400 border-emerald-500/30";
        case "Partial": return "bg-amber-500/20 text-amber-400 border-amber-500/30";
        case "Obviousness": return "bg-orange-500/20 text-orange-400 border-orange-500/30";
        default: return "bg-slate-800/40 text-slate-400 border-slate-700/50";
    }
};