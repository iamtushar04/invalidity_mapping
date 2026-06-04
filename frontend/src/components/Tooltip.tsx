import React, { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';

interface TooltipProps {
  content: string;
  children: React.ReactNode;
  width?: string;
  position?: "top" | "bottom";
}

export default function Tooltip({ content, children, width = "max-w-xs", position = "top" }: TooltipProps) {
  const [isVisible, setIsVisible] = useState(false);
  const triggerRef = useRef<HTMLDivElement>(null);
  const [coords, setCoords] = useState({ top: 0, left: 0 });

  useEffect(() => {
    if (isVisible && triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect();
      setCoords({
        left: rect.left + rect.width / 2,
        top: position === "top" ? rect.top : rect.bottom,
      });
    }
  }, [isVisible, position]);
    
  const arrowClasses = position === "top"
    ? "top-full left-1/2 -translate-x-1/2 -mt-px border-4 border-transparent border-t-slate-700"
    : "bottom-full left-1/2 -translate-x-1/2 -mb-px border-4 border-transparent border-b-slate-700";

  return (
    <>
      <div 
        ref={triggerRef}
        className="relative flex items-center justify-center cursor-pointer"
        onMouseEnter={() => setIsVisible(true)}
        onMouseLeave={() => setIsVisible(false)}
      >
        {children}
      </div>

      {isVisible && content && createPortal(
        <div 
          className="fixed z-[9999] pointer-events-none"
          style={{
            left: coords.left,
            top: coords.top,
            transform: position === "top" ? "translate(-50%, -100%)" : "translate(-50%, 0)",
            marginTop: position === "bottom" ? "8px" : "0",
            marginBottom: position === "top" ? "8px" : "0",
          }}
        >
          <div className={`relative p-3 bg-slate-800 text-slate-200 text-xs font-sans text-left leading-relaxed rounded-xl shadow-2xl border border-slate-700 whitespace-pre-wrap ${width} max-h-[60vh] overflow-y-auto`}>
            {content}
            <div className={`fixed ${arrowClasses}`}></div>
          </div>
        </div>,
        document.body
      )}
    </>
  );
}
