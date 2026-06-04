import { useState, useEffect } from "react";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL as string;
const TERMINAL_STATUSES = ["done", "failed"];

interface UseAutoAnalysisParams {
  step: number;
  projectId: string;
  token: string | null;
  priorArtList: any[];
  handleRunAnalysisAll: () => Promise<void>;
  setUploadMsg: (msg: string) => void;
}

interface UseAutoAnalysisReturn {
  embedStatuses: Record<string, string>;
  armAutoAnalysis: () => void;
}

/**
 * Checks whether every patent in the list has settled to a terminal state.
 * A patent is "settled" if Redis has reported "done" or "failed" for it.
 * Returns false if any patent has not yet reported back (key missing in statuses).
 */
function allPatentsSettled(
  statuses: Record<string, string>,
  patentList: any[]
): boolean {
  if (patentList.length === 0) return false;
  const reportedKeys = Object.keys(statuses);
  const allReported = patentList.every((p: any) =>
    reportedKeys.includes(p.patent_number)
  );
  const allTerminal = Object.values(statuses).every((s) =>
    TERMINAL_STATUSES.includes(s)
  );
  return allReported && allTerminal;
}

/**
 * Custom hook that:
 * 1. Polls the embed-status API every 3s while on Step 4.
 * 2. Exposes `armAutoAnalysis()` to arm the auto-trigger.
 * 3. When ALL patents settle (done or failed), automatically fires analysis.
 */
export function useAutoAnalysis({
  step,
  projectId,
  token,
  priorArtList,
  handleRunAnalysisAll,
  setUploadMsg,
}: UseAutoAnalysisParams): UseAutoAnalysisReturn {
  const [embedStatuses, setEmbedStatuses] = useState<Record<string, string>>({});
  // When true, the hook will auto-trigger analysis once all patents settle
  const [autoAnalysisPending, setAutoAnalysisPending] = useState<boolean>(false);

  // Call this from page.tsx after user adds patents (manual or Excel)
  const armAutoAnalysis = () => {
    setAutoAnalysisPending(true);
  };

  useEffect(() => {
    let interval: ReturnType<typeof setInterval> | null = null;

    if (step === 4 && projectId && token) {
      const fetchEmbedStatus = async () => {
        try {
          const res = await fetch(
            `${BACKEND_URL}/prior-art/${projectId}/embed-status`,
            { headers: { Authorization: `Bearer ${token}` } }
          );
          if (!res.ok) return;

          const data = await res.json();
          const statuses: Record<string, string> = data.statuses || {};
          setEmbedStatuses(statuses);

          // AUTO-TRIGGER: Only fires when armed AND all patents have settled
          if (autoAnalysisPending && allPatentsSettled(statuses, priorArtList)) {
            setAutoAnalysisPending(false); // disarm — ensures it fires only once

            const failedCount = Object.values(statuses).filter(
              (s) => s === "failed"
            ).length;
            const doneCount = Object.values(statuses).filter(
              (s) => s === "done"
            ).length;

            if (doneCount > 0) {
              // At least some patents embedded — run analysis on them
              if (failedCount > 0) {
                setUploadMsg(
                  `⚡ ${failedCount} patent(s) failed to embed. Running analysis on ${doneCount} successfully embedded patent(s)...`
                );
              } else {
                setUploadMsg(`⚡ All patents embedded! Auto-starting analysis...`);
              }
              // Short delay so user can read the message before the UI transitions
              setTimeout(() => handleRunAnalysisAll(), 1500);
            } else {
              // All patents failed — do NOT trigger analysis
              setUploadMsg(
                `⚠️ All patents failed to embed. Please check patent numbers and try again.`
              );
            }
          }
        } catch (err) {
          console.error("Failed to fetch embed status:", err);
        }
      };

      fetchEmbedStatus();
      interval = setInterval(fetchEmbedStatus, 3000);
    }

    return () => {
      if (interval) clearInterval(interval);
    };
    // Re-create the effect if the arm flag or the patent list changes
  }, [step, projectId, token, autoAnalysisPending, priorArtList]);

  return { embedStatuses, armAutoAnalysis };
}
