// src/components/WeightInput.tsx
import React from "react";

interface Props {
  value: number;
  onChange: (newWeight: number) => void;
}

export default function WeightInput({ value, onChange }: Props) {
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    let v = Number(e.target.value);
    if (isNaN(v)) v = 0;
    v = Math.max(0, Math.min(100, v)); // clamp 0‑100
    onChange(v);
  };

  return (
    <input
      type="number"
      step="1"
      min={0}
      max={100}
      value={Math.round(value)}
      onChange={handleChange}
      className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5 w-20 text-right focus:outline-none focus:border-indigo-500 font-mono font-bold text-slate-200"
    />
  );
}
