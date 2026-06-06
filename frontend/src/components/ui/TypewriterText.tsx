import React, { useState, useEffect, useRef } from 'react';

export const TypewriterText = ({ 
  text, 
  delay = 15,
  startOnView = false
}: { 
  text: string, 
  delay?: number,
  startOnView?: boolean
}) => {
  const [displayedText, setDisplayedText] = useState("");
  const [hasStarted, setHasStarted] = useState(!startOnView);
  const containerRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!startOnView) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setHasStarted(true);
          observer.disconnect();
        }
      },
      { threshold: 0.1 }
    );

    if (containerRef.current) {
      observer.observe(containerRef.current);
    }

    return () => observer.disconnect();
  }, [startOnView]);

  useEffect(() => {
    if (!text) {
      setDisplayedText("");
      return;
    }
    
    if (!hasStarted) {
      setDisplayedText("");
      return;
    }

    setDisplayedText("");
    let i = 0;
    const interval = setInterval(() => {
      setDisplayedText(text.substring(0, i));
      i++;
      if (i > text.length) clearInterval(interval);
    }, delay);
    
    return () => clearInterval(interval);
  }, [text, delay, hasStarted]);

  return <span ref={containerRef}>{displayedText}</span>;
};
