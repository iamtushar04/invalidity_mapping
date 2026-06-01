// src/hooks/useClaimSplit.ts
import { useState } from "react";

/**
 * Hook that wraps the FastAPI claim‑split endpoint.
 * Returns a callable `runSplit` plus loading / error state.
 */
export default function useClaimSplit() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * Calls the backend service to split the selected claims and assign weights.
   * @param projectId  The current project identifier.
   * @param claimIds   Array of claim IDs selected by the user.
   * @param token      Bearer token for auth (already stored in the page component).
   * @returns A map: claimId → array of element objects ({ element_id, text, label, weight, ... })
   */
  const runSplit = async (
    projectId: string,
    claimIds: string[],
    token: string
  ): Promise<Record<string, any[]>> => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_BACKEND_URL}/analysis/${projectId}/split`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ claim_ids: claimIds }),
        }
      );
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Failed to split claims via LLM");
      }
      const json = await res.json();
      // Expected shape: { results: { [claimId]: [{ element_id, text, weight, ... }] } }
      return json.results || {};
    } catch (e: any) {
      setError(e.message);
      throw e;
    } finally {
      setLoading(false);
    }
  };

  return { runSplit, loading, error };
}
