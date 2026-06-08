"use client";

import React, { useState, useEffect, useRef } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import {
  FileText, CheckSquare, Layers, Database, Play,
  Table as TableIcon, FileDown, ArrowLeft, Plus,
  Trash2, Loader2, Sparkles, AlertCircle, Check,
  Edit3, ShieldAlert, LogOut, LayoutDashboard, ChevronLeft, ChevronRight
} from "lucide-react";

import useClaimSplit from "@/hooks/useClaimSplit";
import { useAutoAnalysis } from "@/hooks/useAutoAnalysis";
import { sortMatrixRows } from "@/utils/matrixSort";
import WeightInput from "@/components/WeightInput";
import { computePriorityFromWeight, validateWeightSum } from "@/utils/priority";
import { getCellColor } from "@/utils";
import { FilteredMatrix } from "@/constant";
import Tooltip from "@/components/Tooltip";
import FilterSidebar from "@/components/matrix/FilterSidebar";
import MatrixTable from "@/components/matrix/MatrixTable";
import { TypewriterText } from "@/components/ui/TypewriterText";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL as string;

export default function ProjectAnalysisPage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  console.log("params", params)
  const projectId = params.id as string;

  // Authentication & Project
  const [token, setToken] = useState<string | null>(null);
  const [project, setProject] = useState<any>(null);

  // Loading & UI Step — synced with URL (?step=N) and localStorage
  const getInitialStep = () => {
    const urlStep = searchParams.get("step");
    if (urlStep !== null) return parseInt(urlStep, 10);
    const saved = localStorage.getItem(`project-step-${params.id}`);
    if (saved !== null) return parseInt(saved, 10);
    return 0;
  };
  const [step, setStepState] = useState<number>(getInitialStep);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const ingestIntervalRef = useRef<NodeJS.Timeout | null>(null);
  
  // Streaming state for Step 0 ingestion
  const [ingestStreamStatus, setIngestStreamStatus] = useState<string | null>(null);
  const [ingestStreamProgress, setIngestStreamProgress] = useState<number>(0);

  // Wrapper to sync step → URL + localStorage
  const setStep = (newStep: number) => {
    setStepState(newStep);
    router.replace(`/project/${params.id}?step=${newStep}`);
    localStorage.setItem(`project-step-${params.id}`, String(newStep));
  };

  // Subject Patent Ingestion (Phase 1)
  const [patentNum, setPatentNum] = useState<string>("");
  const [patentData, setPatentData] = useState<any>(null);

  // Claim Selection (Phase 2)
  const [selectedClaims, setSelectedClaims] = useState<string[]>([]); // UUID list

  // Claim Elements Breakdown (Phase 3)
  const [activeClaimId, setActiveClaimIdState] = useState<string | null>(null);
  const [elements, setElements] = useState<any[]>([]);
  // Mapping claimId → weight (average weight of its elements) for badge display
  const [claimWeightMap, setClaimWeightMap] = useState<Record<string, number>>({});
  const { runSplit, loading: splitLoading, error: splitError } = useClaimSplit();

  const setActiveClaimId = (id: string | null) => {
    setActiveClaimIdState(id);
    if (id) localStorage.setItem(`project-claimId-${params.id}`, id);
  };

  // Prior Art Input (Phase 4)
  const [priorArtInput, setPriorArtInput] = useState<string>("");
  const [priorArtList, setPriorArtList] = useState<any[]>([]);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);

  // useAutoAnalysis hook: handles embed-status polling + auto-trigger of analysis
  // armAutoAnalysis() is called after user adds patents to arm the auto-trigger
  const { embedStatuses, armAutoAnalysis } = useAutoAnalysis({
    step,
    projectId,
    token,
    priorArtList,
    handleRunAnalysisAll: () => handleRunAnalysisAll(),
    setUploadMsg,
  });

  // Background Job Mapping Status (Phase 5)
  const [analysisStatus, setAnalysisStatus] = useState<any>(null);
  const [matrixData, setMatrixData] = useState<any>(null);
  const [matrixFilter, setMatrixFilterState] = useState<string>("all");

  const setMatrixFilter = (f: string) => {
    setMatrixFilterState(f);
    localStorage.setItem(`project-matrixFilter-${params.id}`, f);
  };

  // Claim Chart & Export (Phase 6)
  const [selectedMatrixPatents, setSelectedMatrixPatents] = useState<any[]>([]);
  const [multiChartData, setMultiChartData] = useState<any[]>([]);
  const [carouselIndex, setCarouselIndex] = useState<number>(0);
  const [chartStatuses, setChartStatuses] = useState<Record<string, string>>({});
  const [carouselInputValue, setCarouselInputValue] = useState<string>("1");

  const [selectedRefPatent, setSelectedRefPatent] = useState<any>(null);
  const [chartData, setChartData] = useState<any>(null);
  const [chartRows, setChartRows] = useState<any[]>([]);
  const [isEditingChart, setIsEditingChart] = useState<boolean>(false);

  // Restore step, claimId, and matrixFilter from URL/localStorage on mount
  useEffect(() => {
    const initialStep = getInitialStep();
    setStepState(initialStep);

    const savedClaimId = localStorage.getItem(`project-claimId-${params.id}`);
    if (savedClaimId) setActiveClaimIdState(savedClaimId);

    const savedFilter = localStorage.getItem(`project-matrixFilter-${params.id}`);
    if (savedFilter) setMatrixFilterState(savedFilter);

    // Restore elements and weights
    const savedElements = localStorage.getItem(`project-elements-${params.id}`);
    if (savedElements) setElements(JSON.parse(savedElements));

    const savedWeightMap = localStorage.getItem(`project-weightMap-${params.id}`);
    if (savedWeightMap) setClaimWeightMap(JSON.parse(savedWeightMap));

    // Restore Step 6 Chart Data
    const savedMultiChart = localStorage.getItem(`project-multiChart-${params.id}`);
    const savedCarouselIndex = localStorage.getItem(`project-carouselIndex-${params.id}`);
    const savedSelectedMatrix = localStorage.getItem(`project-selectedMatrix-${params.id}`);
    
    if (savedMultiChart) {
      try {
        const parsedMultiChart = JSON.parse(savedMultiChart);
        setMultiChartData(parsedMultiChart);
        
        let cIndex = 0;
        if (savedCarouselIndex) {
            cIndex = parseInt(savedCarouselIndex, 10);
            setCarouselIndex(cIndex);
            setCarouselInputValue((cIndex + 1).toString());
        }
        
        if (parsedMultiChart.length > cIndex) {
            setSelectedRefPatent(parsedMultiChart[cIndex].refPatent);
            setChartData(parsedMultiChart[cIndex].chartData);
            setChartRows(parsedMultiChart[cIndex].chartRows);
        }
      } catch (e) {
        console.error("Failed to parse saved chart data", e);
      }
    }
    
    if (savedSelectedMatrix) {
        try {
            setSelectedMatrixPatents(JSON.parse(savedSelectedMatrix));
        } catch (e) { console.error(e); }
    }
  }, [params.id]);

  // Persist elements and weight map when they change
  useEffect(() => {
    if (elements.length > 0) {
      localStorage.setItem(`project-elements-${params.id}`, JSON.stringify(elements));
    }
  }, [elements, params.id]);

  useEffect(() => {
    if (Object.keys(claimWeightMap).length > 0) {
      localStorage.setItem(`project-weightMap-${params.id}`, JSON.stringify(claimWeightMap));
    }
  }, [claimWeightMap, params.id]);

  // Persist chart data when it changes
  useEffect(() => {
    if (multiChartData.length > 0) {
      localStorage.setItem(`project-multiChart-${params.id}`, JSON.stringify(multiChartData));
    }
  }, [multiChartData, params.id]);

  useEffect(() => {
    if (selectedMatrixPatents.length > 0) {
      localStorage.setItem(`project-selectedMatrix-${params.id}`, JSON.stringify(selectedMatrixPatents));
    }
  }, [selectedMatrixPatents, params.id]);

  useEffect(() => {
    localStorage.setItem(`project-carouselIndex-${params.id}`, String(carouselIndex));
  }, [carouselIndex, params.id]);

  // Auto-fetch data based on restored step
  useEffect(() => {
    if (!token || !projectId) return;
    
    // If we landed on Step 4 (Prior Art) and don't have it loaded
    if (step >= 4 && priorArtList.length === 0) {
      fetchPriorArt(token);
    }

    // If we landed on Step 5 (Matrix) and don't have it loaded
    if (step === 5 && !matrixData && activeClaimId) {
      autoFetchMatrix(token, activeClaimId);
    }
  }, [step, token, projectId, activeClaimId]);

  const autoFetchMatrix = async (authToken: string, claimId: string) => {
    try {
      setLoading(true);
      const res = await fetch(`${BACKEND_URL}/analysis/${projectId}/matrix?claim_id=${claimId}`, {
        headers: { Authorization: `Bearer ${authToken}` }
      });
      if (res.ok) {
        const data = await res.json();
        setMatrixData(data);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const fetchChartStatuses = async (authToken: string = token!) => {
    if (!projectId) return;
    try {
      const res = await fetch(`${BACKEND_URL}/charts/${projectId}/charts/status`, {
        headers: { Authorization: `Bearer ${authToken}` }
      });
      if (res.ok) {
        const data = await res.json();
        setChartStatuses(data.statuses || {});
      }
    } catch (err) {
      console.error("Failed to fetch chart statuses:", err);
    }
  };

  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (token && projectId && step >= 5) {
      fetchChartStatuses(token); // initial fetch
      interval = setInterval(() => {
        fetchChartStatuses(token);
      }, 5000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [step, token, projectId]);

  // Initialize and check credentials
  useEffect(() => {
    const storedToken = localStorage.getItem("token");
    if (!storedToken) {
      router.push("/");
      return;
    }
    setToken(storedToken);
    fetchProject(storedToken);
  }, []);

  const handleLogout = () => {
    localStorage.removeItem("token");
    setToken(null);
    router.push("/");
  };

  const fetchProject = async (authToken: string) => {
    try {
      setLoading(true);
      const res = await fetch(`${BACKEND_URL}/projects/${projectId}`, {
        headers: { Authorization: `Bearer ${authToken}` }
      });
      if (!res.ok) throw new Error("Failed to load project details.");
      const data = await res.json();
      setProject(data);

      // Auto-fetch ingested subject patent if present
      if (data.subject_patent_id) {
        await fetchSubjectPatent(data.subject_patent_id, authToken, data);
        // Only jump to step 1 if no step is already persisted (first visit)
        const savedStep = localStorage.getItem(`project-step-${projectId}`);
        const urlStep = searchParams.get("step");
        if (!savedStep && !urlStep) {
          setStep(1);
        }
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchSubjectPatent = async (patentId: string, authToken: string, projectData?: any) => {
    try {
      const res = await fetch(`${BACKEND_URL}/patents/project/${projectId}`, {
        headers: { Authorization: `Bearer ${authToken}` }
      });
      if (res.ok) {
        const data = await res.json();
        setPatentData(data);
        setPatentNum(data.patent_number);
        if (data.claims && data.claims.length > 0) {
          // Preset select claim selection if present in project
          const proj = projectData || project;
          setSelectedClaims(proj?.selected_claim_ids || []);
        }
      }
    } catch (err) {
      console.error(err);
    }
  };

  // Phase 1: Ingestion
  const handleIngest = async () => {
    if (!patentNum.trim()) return;
    const cleanedPatentNum = patentNum.replace(/\s+/g, "");
    setError(null);
    setIngestStreamStatus("Queued for ingestion...");
    setIngestStreamProgress(0);
    try {
      const res = await fetch(`${BACKEND_URL}/patents/ingest`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ patent_number: cleanedPatentNum, project_id: projectId })
      });
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Ingestion failed.");
      }
      
      // Start polling
      startIngestionPolling(cleanedPatentNum);

    } catch (err: any) {
      setError(err.message);
    }
  };

  const startIngestionPolling = (patentNumber?: string) => {
    if (ingestIntervalRef.current) {
      clearInterval(ingestIntervalRef.current);
      ingestIntervalRef.current = null;
    }
    ingestIntervalRef.current = setInterval(async () => {
      try {
        const statusRes = await fetch(`${BACKEND_URL}/patents/project/${projectId}/ingestion-status`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        
        // Prevent state updates if polling was cancelled while fetch was in-flight
        if (!ingestIntervalRef.current) return;

        if (statusRes.ok) {
          const statusData = await statusRes.json();
          if (statusData.status === "processing" || statusData.status === "pending") {
            setIngestStreamStatus(statusData.message || "Processing...");
            setIngestStreamProgress(statusData.progress || 0);
          } else if (statusData.status === "success") {
            if (ingestIntervalRef.current) {
              clearInterval(ingestIntervalRef.current);
              ingestIntervalRef.current = null;
            }
            setIngestStreamStatus("Success! Fetching final patent data...");
            setIngestStreamProgress(100);
            // Fetch the final patent data
            const finalRes = await fetch(`${BACKEND_URL}/patents/project/${projectId}`, {
              headers: { Authorization: `Bearer ${token}` }
            });
            
            // Final check to ensure we haven't navigated away
            if (!ingestIntervalRef.current && step !== 0) return;
            
            if (finalRes.ok) {
              const finalData = await finalRes.json();
              setPatentData(finalData);
              setStep(1); // Go to detail review
            }
          } else if (statusData.status === "failed") {
            if (ingestIntervalRef.current) {
              clearInterval(ingestIntervalRef.current);
              ingestIntervalRef.current = null;
            }
            if (patentNumber) throw new Error(statusData.message || "Background ingestion failed.");
          }
        }
      } catch (pollErr: any) {
        if (ingestIntervalRef.current) {
          clearInterval(ingestIntervalRef.current);
          ingestIntervalRef.current = null;
        }
        setError(pollErr.message);
      }
    }, 2000);
  };

  // Resume polling on mount if we are on step 0
  useEffect(() => {
    if (token && projectId && step === 0) {
      startIngestionPolling();
    }
    return () => {
      if (ingestIntervalRef.current) {
        clearInterval(ingestIntervalRef.current);
        ingestIntervalRef.current = null;
      }
    };
  }, [token, projectId, step]);

  // Phase 2: Claim Selection
  const toggleClaimSelection = (claimId: string) => {
    setSelectedClaims(prev =>
      prev.includes(claimId) ? [] : [claimId]
    );
  };

  const handleSaveSelectedClaims = async () => {
    if (selectedClaims.length === 0) {
      setError("Please select at least one claim.");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`${BACKEND_URL}/claims/project/${projectId}/selected-claims`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ claim_ids: selectedClaims })
      });
      if (!res.ok) throw new Error("Failed to save selected claims.");

      // --- NEW: Call LLM split service using the hook defined at component top
      // Ensure we have a valid token before calling the split service
      if (!token) {
        setError("Authentication token missing. Please log in again.");
        setLoading(false);
        return;
      }
      const splitResult = await runSplit(projectId, selectedClaims, token);
      // splitResult format: { claimId: [{ element_id, text, weight, label, ... }] }
      // Update elements for the first claim and store weight map for UI badges
      // splitResult format: { claimId: [{ element_id, text, weight, label, ... }] }
      // Update elements for the first claim and store weight map for UI badges
      const firstClaimId = selectedClaims[0];
      setActiveClaimId(firstClaimId);
      setElements(splitResult[firstClaimId] || []);
      // Build a simple weight map: average weight per claim (or sum of its elements)
      const weightMap: Record<string, number> = {};
      for (const cid of selectedClaims) {
        const elems = splitResult[cid] || [];
        const sum = elems.reduce((a: number, e: any) => a + (e.weight ?? 0), 0);
        weightMap[cid] = sum / (elems.length || 1);
      }
      setClaimWeightMap(weightMap);
      setStep(3); // Go to weightingng
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Phase 3: Claim Weighting
  const fetchOrParseElements = async (claimId: string) => {
    setLoading(true);
    try {
      const res = await fetch(`${BACKEND_URL}/claims/${claimId}/parse-elements`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!res.ok) throw new Error("Failed to parse claim elements.");
      const data = await res.json();
      setElements(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const [lockedWeights, setLockedWeights] = useState<Set<number>>(new Set());

  const handleWeightChange = (index: number, newWeight: number) => {
    setLockedWeights(prev => new Set(prev).add(index));
    setElements(prev => {
      const list = [...prev];
      list[index].weight = parseFloat(newWeight.toString()) || 0;
      return list;
    });
  };

  const handleAutoBalance = () => {
    setElements(prev => {
      const list = [...prev];
      const lockedSum = Array.from(lockedWeights).reduce((sum, idx) => sum + (list[idx]?.weight || 0), 0);
      const remainingPoints = Math.max(0, 100 - lockedSum);
      
      const unlockedIndices = list.map((_, i) => i).filter(i => !lockedWeights.has(i));
      
      // Fallback 1: No unlocked elements
      if (unlockedIndices.length === 0) {
        setLockedWeights(new Set());
        const totalOriginal = list.reduce((sum, el) => sum + (el.weight || 0), 0);
        if (totalOriginal === 0) {
           const base = Math.floor(100 / list.length);
           const remainder = 100 - (base * list.length);
           list.forEach((el, i) => { el.weight = base + (i < remainder ? 1 : 0); });
           return list;
        }
        const exacts = list.map(el => ((el.weight || 0) / totalOriginal) * 100);
        const ints = exacts.map(e => Math.floor(e));
        const rems = exacts.map((e, i) => ({ i, r: e - ints[i] }));
        rems.sort((a, b) => b.r - a.r);
        const missing = 100 - ints.reduce((a,b) => a+b, 0);
        for (let i=0; i<missing; i++) ints[rems[i].i]++;
        list.forEach((el, i) => { el.weight = ints[i]; });
        return list;
      }

      const unlockedSum = unlockedIndices.reduce((sum, idx) => sum + (list[idx].weight || 0), 0);
      
      // Fallback 2: Unlocked elements sum to 0
      if (unlockedSum === 0) {
        const baseVal = Math.floor(remainingPoints / unlockedIndices.length);
        const missingPoints = remainingPoints - (baseVal * unlockedIndices.length);
        unlockedIndices.forEach((idx, i) => {
          list[idx].weight = baseVal + (i < missingPoints ? 1 : 0);
        });
        return list;
      }

      // Proportional Scaling for Unlocked Elements
      const exacts = unlockedIndices.map(idx => ((list[idx].weight || 0) / unlockedSum) * remainingPoints);
      const ints = exacts.map(e => Math.floor(e));
      const rems = exacts.map((e, i) => ({ idx: unlockedIndices[i], arrayIndex: i, r: e - ints[i] }));
      rems.sort((a, b) => b.r - a.r);
      
      const missing = remainingPoints - ints.reduce((a,b) => a+b, 0);
      for (let i = 0; i < missing; i++) {
        ints[rems[i].arrayIndex]++;
      }
      
      unlockedIndices.forEach((idx, i) => {
        list[idx].weight = ints[i];
      });

      return list;
    });
  };

  const handleElementChange = (index: number, field: string, value: any) => {
    setElements(prev => {
      const list = [...prev];
      list[index] = { ...list[index], [field]: value };
      return list;
    });
  };

  const handleAddCustomLimitation = () => {
    const newId = `C${elements.filter((e: any) => e.is_custom).length + 1}`;
    setElements((prev: any[]) => [
      ...prev,
      {
        element_id: newId,
        label: "Custom Limitation",
        text: "",
        weight: 0,
        comment: "",
        is_custom: true
      }
    ]);
  };

  const handleRemoveCustomLimitation = (index: number) => {
    setElements(prev => {
      const list = [...prev];
      list.splice(index, 1);
      return list;
    });
  };

  const handleSaveWeights = async () => {
    // Validate that the weights sum exactly to 100
    if (!validateWeightSum(elements)) {
      setError("Total weight must equal exactly 100%. Please adjust the weights before saving.");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(`${BACKEND_URL}/claims/${activeClaimId}/elements`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ elements })
      });
      if (!res.ok) throw new Error("Failed to save customized weights.");

      // Fetch existing prior art
      await fetchPriorArt();
      setStep(4); // Prior art
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Phase 4: Prior Art Input
  const fetchPriorArt = async (authToken: string = token!) => {
    try {
      const res = await fetch(`${BACKEND_URL}/prior-art/${projectId}`, {
        headers: { Authorization: `Bearer ${authToken}` }
      });
      if (res.ok) {
        const data = await res.json();
        setPriorArtList(data);
      }
    } catch (err) {
      console.error(err);
    }
  };



  const handleAddManualPriorArt = async () => {
    if (!priorArtInput.trim()) return;
    setLoading(true);
    try {
      const res = await fetch(`${BACKEND_URL}/prior-art/${projectId}/numbers`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ patent_numbers: priorArtInput })
      });
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to queue prior art numbers.");
      }
      
      const data = await res.json();
      if (data.status === "duplicate") {
        throw new Error(data.message || "Patents are already present.");
      }
      
      setPriorArtInput("");
      if (data.duplicates_skipped > 0) {
        setUploadMsg(`${data.count} queued. ${data.duplicates_skipped} duplicates skipped. ⚡ Auto-analysis will trigger when embedding completes...`);
      } else {
        setUploadMsg("Prior art numbers queued! ⚡ Auto-analysis will trigger when embedding completes...");
      }
      armAutoAnalysis(); // arm the auto-trigger
      setTimeout(fetchPriorArt, 3000);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleExcelUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    setLoading(true);
    const formData = new FormData();
    formData.append("file", files[0]);

    try {
      const res = await fetch(`${BACKEND_URL}/prior-art/${projectId}/upload`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData
      });
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to upload excel spreadsheet.");
      }
      
      const data = await res.json();
      if (data.status === "duplicate") {
        throw new Error(data.message || "Patents are already present.");
      }
      
      if (data.duplicates_skipped > 0) {
        setUploadMsg(`${data.count} queued. ${data.duplicates_skipped} duplicates skipped. ⚡ Auto-analysis will trigger when embedding completes...`);
      } else {
        setUploadMsg("Spreadsheet parsed and queued! ⚡ Auto-analysis will trigger when embedding completes...");
      }
      armAutoAnalysis(); // arm the auto-trigger
      setTimeout(fetchPriorArt, 3000);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleEmbedPatent = async (patentNumber: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${BACKEND_URL}/prior-art/${projectId}/patent/${patentNumber}/embed`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Embedding generation failed.");
      }
      setUploadMsg(`Successfully stored ${patentNumber} in the embedding database.`);
      fetchPriorArt();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Active status polling loop
  // Phase 5: Obviousness Analysis & Matrix - Run analysis for all selected claims
  const handleRunAnalysisAll = async () => {
    // The backend now automatically triggers the analysis when embedding completes.
    // We just transition the UI to step 5 to watch the background progress.
    setStep(5);
    pollAnalysisStatus();
  };
  // Active status polling loop
  const pollInterval = useRef<any>(null);

  const pollAnalysisStatus = () => {
    if (pollInterval.current) clearInterval(pollInterval.current);

    const fetchStatus = async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/analysis/${projectId}/status`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (res.ok) {
          const data = await res.json();
          setAnalysisStatus(data);

          if (data.percent_complete === 100) {
            clearInterval(pollInterval.current);
          }
          
          // Continuously fetch Matrix data so chunks stream in live
          fetchMatrixData();
        }
      } catch (err) {
        console.error(err);
      }
    };

    fetchStatus();
    pollInterval.current = setInterval(fetchStatus, 3000);
  };

  const fetchMatrixData = async () => {
    try {
      const url = activeClaimId 
        ? `${BACKEND_URL}/analysis/${projectId}/matrix?claim_id=${activeClaimId}`
        : `${BACKEND_URL}/analysis/${projectId}/matrix`;
        
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setMatrixData(data);
      }
    } catch (err) {
      console.error(err);
    }
  };

  // Phase 6: Chart Generation & Persistence
  const handleToggleMatrixPatent = (row: any) => {
    setSelectedMatrixPatents(prev => {
      const exists = prev.find(p => p.reference_patent_id === row.reference_patent_id);
      if (exists) return prev.filter(p => p.reference_patent_id !== row.reference_patent_id);
      return [...prev, row];
    });
  };

  const handleCreateMultipleCharts = async () => {
    if (selectedMatrixPatents.length === 0) return;
    try {
      const refIds = selectedMatrixPatents.map(p => p.reference_patent_id);
      const res = await fetch(`${BACKEND_URL}/charts/${projectId}/charts/generate-async`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ reference_patent_ids: refIds })
      });
      if (!res.ok) throw new Error("Failed to queue chart generation.");
      
      // Clear selection so the user can select others immediately
      setSelectedMatrixPatents([]);
      fetchChartStatuses(token!);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleViewChart = async (refPatentId: string, patentNumber: string) => {
    setLoading(true);
    try {
      // Find all patents that have a "done" chart status
      const donePatents = matrixData?.rows?.filter((r: any) => chartStatuses[r.reference_patent_id] === "done") || [];
      
      // If the clicked one isn't in the done list (failsafe), add it manually
      if (!donePatents.find((p: any) => p.reference_patent_id === refPatentId)) {
        donePatents.push({ reference_patent_id: refPatentId, patent_number: patentNumber });
      }

      // Fetch all done charts in parallel
      const fetchPromises = donePatents.map(async (p: any) => {
        const res = await fetch(`${BACKEND_URL}/charts/${projectId}/charts/${p.reference_patent_id}/generate?force=false`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` }
        });
        if (!res.ok) throw new Error(`Failed to load claim chart for ${p.patent_number}`);
        const data = await res.json();
        return {
          refPatent: { reference_patent_id: p.reference_patent_id, patent_number: p.patent_number },
          chartData: data,
          chartRows: data.chart_rows || []
        };
      });

      const generatedCharts = await Promise.all(fetchPromises);
      
      // Find the index of the specific chart the user clicked
      let targetIndex = generatedCharts.findIndex(c => c.refPatent.reference_patent_id === refPatentId);
      if (targetIndex === -1) targetIndex = 0;

      setMultiChartData(generatedCharts);
      setCarouselIndex(targetIndex);
      setSelectedRefPatent(generatedCharts[targetIndex].refPatent);
      setChartData(generatedCharts[targetIndex].chartData);
      setChartRows(generatedCharts[targetIndex].chartRows);
      setCarouselInputValue((targetIndex + 1).toString());
      setStep(6);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCarouselChange = (direction: "prev" | "next") => {
    let newIndex = carouselIndex;
    if (direction === "prev" && carouselIndex > 0) newIndex--;
    if (direction === "next" && carouselIndex < multiChartData.length - 1) newIndex++;
    
    setCarouselIndex(newIndex);
    setCarouselInputValue((newIndex + 1).toString());
    setSelectedRefPatent(multiChartData[newIndex].refPatent);
    setChartData(multiChartData[newIndex].chartData);
    setChartRows(multiChartData[newIndex].chartRows);
    setIsEditingChart(false);
  };

  const handleCarouselInputSubmit = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      const val = parseInt(carouselInputValue);
      if (!isNaN(val) && val >= 1 && val <= multiChartData.length) {
        const newIndex = val - 1;
        setCarouselIndex(newIndex);
        setSelectedRefPatent(multiChartData[newIndex].refPatent);
        setChartData(multiChartData[newIndex].chartData);
        setChartRows(multiChartData[newIndex].chartRows);
        setIsEditingChart(false);
      } else {
        setCarouselInputValue((carouselIndex + 1).toString());
      }
    }
  };

  const handleUpdateChartRow = (index: number, field: string, value: string) => {
    setChartRows(prev => {
      const list = [...prev];
      list[index][field] = value;
      return list;
    });
  };

  const handleSaveChartEdits = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${BACKEND_URL}/charts/${projectId}/charts/${selectedRefPatent.reference_patent_id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ chart_rows: chartRows })
      });
      if (!res.ok) throw new Error("Failed to save changes.");
      const data = await res.json();
      setChartData(data);
      setChartRows(data.chart_rows || []);
      setIsEditingChart(false);
      await fetchMatrixData();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadReport = (format: string, refId?: string, refNum?: string) => {
    const targetRefId = refId || selectedRefPatent?.reference_patent_id;
    const targetRefNum = refNum || selectedRefPatent?.patent_number;
    if (!targetRefId) return;
    const url = `${BACKEND_URL}/charts/${projectId}/charts/${targetRefId}/export?format=${format}&token=${token}`;
    const link = document.createElement("a");
    link.href = url;
    link.download = `Claim_Chart_${patentNum}_vs_${targetRefNum}.${format}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Helpers for Matrix Rendering Filters
  const filteredRows = () => {
    if (!matrixData || !matrixData.rows) return [];

    const filtered = matrixData.rows.filter((row: any) => {
      if (matrixFilter === "all") return true;
      if (matrixFilter === "strong") return row.score >= 80;
      if (matrixFilter === "good") return row.score >= 50 && row.score < 80;
      if (matrixFilter === "partial") return row.score < 50;
      if (matrixFilter === "all_y") {
        return row.mappings.every((m: any) => m.classification === "Y");
      }
      if (matrixFilter === "missing_one") {
        const notY = row.mappings.filter((m: any) => m.classification !== "Y").length;
        return notY === 1;
      }
      return true;
    });

    return sortMatrixRows(filtered);
  };



  return (
    <div className="min-h-screen bg-[#0b0f19] text-slate-100 flex flex-col font-sans">
      <header className="border-b border-slate-800/80 bg-slate-950/50 backdrop-blur px-8 py-4 flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center gap-4">
          <div className="bg-indigo-600/20 p-2 rounded-xl border border-indigo-500/30 text-indigo-400">
            <Sparkles className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-xl font-bold bg-gradient-to-r from-indigo-200 via-indigo-100 to-indigo-300 bg-clip-text text-transparent">
              Invalidity Analysis Suite
            </h1>
            <p className="text-xs text-slate-400 font-mono">Project ID: {projectId.slice(0, 8)}... / {project?.name}</p>
          </div>
        </div>

        <div className="flex items-center gap-6">
          <button
            onClick={() => router.push("/")}
            className="p-2 rounded-xl text-slate-400 hover:text-indigo-400 hover:bg-indigo-400/10 transition-colors flex items-center gap-2"
            title="Projects Dashboard"
          >
            <LayoutDashboard className="w-5 h-5" />
          </button>
          <div className="hidden lg:flex items-center gap-2 text-xs font-semibold text-slate-400">
            {[
              { stepNum: 0, label: "Ingest" },
              { stepNum: 1, label: "Review" },
              { stepNum: 2, label: "Claims" },
              { stepNum: 3, label: "Weights" },
              { stepNum: 4, label: "Prior Art" },
              { stepNum: 5, label: "Matrix" },
              { stepNum: 6, label: "Chart" }
            ].map((item) => (
              <React.Fragment key={item.stepNum}>
                <div
                  onClick={() => {
                    if (patentData) setStep(item.stepNum);
                  }}
                  className={`px-3 py-1.5 rounded-lg cursor-pointer transition-all duration-300 border ${step === item.stepNum
                    ? "bg-indigo-600/20 text-indigo-300 border-indigo-500/50 shadow-[0_0_15px_rgba(99,102,241,0.15)]"
                    : "bg-slate-900/60 border-transparent hover:border-slate-700 text-slate-500"
                    }`}
                >
                  {item.label}
                </div>
                {item.stepNum < 6 && <div className="w-1 h-0.5 bg-slate-800" />}
              </React.Fragment>
            ))}
          </div>
          
          <button
            onClick={handleLogout}
            className="p-2 rounded-xl text-slate-400 hover:text-rose-400 hover:bg-rose-400/10 transition-colors flex items-center gap-2"
            title="Logout"
          >
            <LogOut className="w-5 h-5" />
          </button>
        </div>
      </header>

      <main className="flex-1 max-w-7xl w-full mx-auto p-8">
        {error && (
          <div className="mb-6 p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 flex items-center gap-3">
            <AlertCircle className="w-5 h-5 flex-shrink-0" />
            <p className="text-sm font-medium">{error}</p>
            <button onClick={() => setError(null)} className="ml-auto hover:text-white text-xs">Dismiss</button>
          </div>
        )}

        {loading && (
          <div className="fixed inset-0 bg-slate-950/70 backdrop-blur-sm z-50 flex flex-col items-center justify-center gap-3">
            <Loader2 className="w-12 h-12 text-indigo-500 animate-spin" />
            <p className="text-sm text-slate-300 font-medium">Processing request with LLM routing models...</p>
          </div>
        )}

        {step === 0 && (
          <div className="max-w-xl mx-auto mt-12 bg-slate-950/40 border border-slate-800/80 rounded-2xl p-8 backdrop-blur shadow-[0_8px_32px_rgba(0,0,0,0.4)]">
            <div className="text-center mb-6">
              <FileText className="w-12 h-12 text-indigo-400 mx-auto mb-3" />
              <h2 className="text-2xl font-bold mb-2">Ingest Subject Patent</h2>
              <p className="text-sm text-slate-400">
                Enter your target patent number. We fetch real USPTO database XML files and run `gpt-5-mini` parsing.
              </p>
            </div>

            {ingestStreamStatus ? (
              <div className="space-y-4">
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                  <div className="flex items-center gap-3 mb-4 text-indigo-400 font-mono text-sm">
                    <Loader2 className="w-5 h-5 animate-spin" />
                    {ingestStreamStatus}
                  </div>
                  <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
                    <div 
                      className="bg-indigo-500 h-2 rounded-full transition-all duration-500" 
                      style={{ width: `${ingestStreamProgress}%` }}
                    />
                  </div>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-mono text-slate-400 uppercase tracking-widest mb-1.5">Patent Number</label>
                  <input
                    type="text"
                    value={patentNum}
                    onChange={(e) => setPatentNum(e.target.value)}
                    placeholder="e.g. US6285999B1 (Google PageRank)"
                    className="w-full bg-slate-900 border border-slate-800 rounded-xl px-4 py-3 focus:outline-none focus:border-indigo-500 transition font-mono"
                  />
                </div>

                <button
                  onClick={handleIngest}
                  className="w-full bg-indigo-600 hover:bg-indigo-500 py-3 rounded-xl font-semibold transition shadow-lg shadow-indigo-600/20 flex items-center justify-center gap-2"
                >
                  <Sparkles className="w-4 h-4" /> Start Ingestion
                </button>
              </div>
            )}
          </div>
        )}

        {step === 1 && patentData && (
          <div className="space-y-8">
            <div className="flex justify-between items-center">
              <div>
                <h2 className="text-2xl font-bold">{patentData.title}</h2>
                <p className="text-sm text-slate-400 font-mono">Assignee: {patentData.assignee} / Ingested Successfully</p>
              </div>
              <button
                onClick={() => setStep(2)}
                className="bg-indigo-600 hover:bg-indigo-500 px-6 py-2.5 rounded-xl font-semibold transition"
              >
                Select Claims →
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="bg-slate-950/40 border border-slate-800 p-6 rounded-2xl backdrop-blur">
                <h3 className="text-sm font-bold text-indigo-400 uppercase tracking-widest font-mono mb-3">Core Concept</h3>
                <p className="text-sm text-slate-300 leading-relaxed">
                  <TypewriterText text={patentData.structured_summary?.core_inventive_concept || ""} delay={10} />
                </p>
              </div>

              <div className="bg-slate-950/40 border border-slate-800 p-6 rounded-2xl backdrop-blur">
                <h3 className="text-sm font-bold text-indigo-400 uppercase tracking-widest font-mono mb-3">Problem-Solution Mapping</h3>
                <div className="space-y-2 text-sm text-slate-300">
                  <p><strong className="text-rose-400">Problem:</strong> <TypewriterText text={patentData.structured_summary?.problem_solution_mapping?.problem || ""} delay={15} /></p>
                  <p><strong className="text-emerald-400">Solution:</strong> <TypewriterText text={patentData.structured_summary?.problem_solution_mapping?.solution || ""} delay={15} /></p>
                </div>
              </div>

              <div className="bg-slate-950/40 border border-slate-800 p-6 rounded-2xl backdrop-blur">
                <h3 className="text-sm font-bold text-indigo-400 uppercase tracking-widest font-mono mb-3">Novelty Claims</h3>
                <ul className="list-disc list-inside text-sm text-slate-300 space-y-1">
                  {patentData.structured_summary?.novelty_points?.map((item: string, idx: number) => (
                    <li key={idx}><TypewriterText text={item} delay={20} /></li>
                  ))}
                </ul>
              </div>
            </div>

            <div className="bg-slate-950/20 border border-slate-800/80 p-8 rounded-2xl">
              <h3 className="text-lg font-bold mb-4">Patent Abstract</h3>
              <p className="text-sm text-slate-300 leading-relaxed">{patentData.abstract}</p>
            </div>
          </div>
        )}

        {step === 2 && patentData && (
          <div className="max-w-2xl mx-auto space-y-6">
            <div>
              <h2 className="text-2xl font-bold mb-1">Select Claims for Invalidity Analysis</h2>
              <p className="text-sm text-slate-400">Choose which claims you want to segment, weight, and check against prior art.</p>
            </div>

            <div className="bg-slate-950/40 border border-slate-800 rounded-2xl p-6 space-y-4">
              {[...(patentData.claims || [])].sort((a: any, b: any) => parseInt(a.claim_number) - parseInt(b.claim_number)).map((claim: any) => (
                <div
                  key={claim.id}
                  onClick={() => toggleClaimSelection(claim.id)}
                  className={`p-4 rounded-xl border cursor-pointer transition-all ${selectedClaims.includes(claim.id)
                    ? "bg-indigo-600/10 border-indigo-500 text-slate-100"
                    : "bg-slate-900/40 border-slate-800 hover:border-slate-700 text-slate-400"
                    }`}
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-5 h-5 rounded-md border flex items-center justify-center ${selectedClaims.includes(claim.id)
                      ? "bg-indigo-600 border-indigo-500 text-white"
                      : "border-slate-700"
                      }`}>
                      {selectedClaims.includes(claim.id) && <Check className="w-3 h-3" />}
                    </div>
                    <span className="font-bold font-mono">Claim {claim.claim_number}</span>
                    <span className="text-xs uppercase px-2 py-0.5 rounded bg-slate-800 text-slate-400 font-semibold">{claim.claim_type}</span>
                    {/* Priority badge */}
                    {claimWeightMap[claim.id] !== undefined && (
                      <span className="ml-2 text-xs uppercase px-2 py-0.5 rounded bg-indigo-600/20 text-indigo-300 font-semibold">
                        {computePriorityFromWeight(claimWeightMap[claim.id])}
                      </span>
                    )}
                  </div>
                  <p className="text-sm mt-2 leading-relaxed">
                    <TypewriterText text={claim.claim_text} startOnView={true} delay={5} />
                  </p>
                </div>
              ))}
            </div>

            <div className="flex justify-between items-center">
              <button onClick={() => setStep(1)} className="text-slate-400 hover:text-white flex items-center gap-2">
                <ArrowLeft className="w-4 h-4" /> Back to summary
              </button>
              <button
                onClick={handleSaveSelectedClaims}
                className="bg-indigo-600 hover:bg-indigo-500 px-6 py-2.5 rounded-xl font-semibold transition"
              >
                Confirm Claim & Split Elements →
              </button>
            </div>
          </div>
        )}

        {step === 3 && elements && (
          <div className="max-w-4xl mx-auto space-y-6">
            <div>
              <h2 className="text-2xl font-bold mb-1">Claim Segmentation & Weight Assignments</h2>
              <p className="text-sm text-slate-400">
                Segmented using `gpt-5-mini`. Customize novelty weights per limitation. Total must equal exactly 100.0%.
              </p>
            </div>

            <div className="bg-slate-950/40 border border-slate-800 rounded-2xl overflow-hidden">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-slate-800 bg-slate-900/60 font-mono text-xs uppercase text-slate-400">
                    <th className="p-4 w-20">ID</th>

                    <th className="p-4">Limitation (Exact Text)</th>
                    <th className="p-4 w-32 text-right">Weight (%)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 text-sm">
                  {elements.map((el, idx) => (
                    <tr key={el.id || idx} className="hover:bg-slate-900/20">
                      <td className="p-4 font-mono font-bold text-indigo-400">
                        {el.is_custom ? (
                          <input type="text" value={el.element_id} onChange={e => handleElementChange(idx, 'element_id', e.target.value)} className="w-16 bg-slate-800 p-1 rounded border border-slate-700" placeholder="ID" />
                        ) : el.element_id}
                      </td>

                      <td className="p-4 text-slate-400 leading-relaxed text-xs">
                        {el.is_custom ? (
                          <textarea value={el.text} onChange={e => handleElementChange(idx, 'text', e.target.value)} className="w-full bg-slate-800 p-2 rounded border border-slate-700 focus:border-indigo-500 focus:outline-none" placeholder="Enter custom limitation text..." rows={3} />
                        ) : (
                          el.text
                        )}
                        <div className="mt-3">
                          <textarea
                            value={el.comment || ''}
                            onChange={e => handleElementChange(idx, 'comment', e.target.value)}
                            placeholder="Add your context or perception here to guide the AI search..."
                            className="w-full bg-indigo-900/10 border border-indigo-500/20 text-indigo-300 p-2.5 rounded-lg text-xs placeholder:text-indigo-400/50 focus:outline-none focus:border-indigo-500 transition-colors"
                            rows={2}
                          />
                        </div>
                      </td>
                      <td className="p-4 text-right align-top pt-6">
                        <div className="flex flex-col items-end gap-2">
                          <WeightInput
                            value={el.weight ?? 0}
                            onChange={(newWeight) => handleWeightChange(idx, newWeight)}
                          />
                          {el.is_custom && (
                            <button
                              onClick={() => handleRemoveCustomLimitation(idx)}
                              className="text-rose-400/70 hover:text-rose-400 transition text-xs mt-2 flex items-center gap-1"
                            >
                              <Trash2 className="w-3 h-3" /> Remove
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="p-4 bg-slate-950/80 border-t border-slate-800 flex justify-between items-center text-xs">
                <button
                  onClick={handleAddCustomLimitation}
                  className="bg-slate-800 hover:bg-slate-700 text-slate-300 px-4 py-2 rounded-lg font-semibold transition flex items-center gap-2 border border-slate-700"
                >
                  <Plus className="w-4 h-4 text-indigo-400" /> Add Custom Limitation
                </button>
                
                {(() => {
                  const total = elements.reduce((sum, el) => sum + (el.weight ?? 0), 0);
                  const is100 = Math.abs(total - 100) <= 0.5;
                  return (
                    <div className="flex items-center gap-4">
                      {!is100 && (
                        <button
                          onClick={handleAutoBalance}
                          className="bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-300 px-3 py-1.5 rounded-lg border border-indigo-500/30 transition flex items-center gap-2"
                        >
                          <Sparkles className="w-3 h-3" /> Auto-Balance
                        </button>
                      )}
                      <div className="flex items-center gap-3 text-sm font-bold bg-slate-900 px-4 py-2 rounded-lg border border-slate-800">
                        <span className="text-slate-400">Total Weight:</span>
                        <span className={is100 ? "text-emerald-400" : "text-rose-400"}>
                          {Math.round(total)}%
                        </span>
                      </div>
                    </div>
                  );
                })()}
              </div>
            </div>

            <div className="flex justify-between items-center">
              <button onClick={() => setStep(2)} className="text-slate-400 hover:text-white flex items-center gap-2">
                <ArrowLeft className="w-4 h-4" /> Back to selection
              </button>
              <button
                onClick={handleSaveWeights}
                className="bg-indigo-600 hover:bg-indigo-500 px-6 py-2.5 rounded-xl font-semibold transition"
              >
                Save Weighting Layout →
              </button>
            </div>
          </div>
        )}

        {step === 4 && (
          <div className="max-w-3xl mx-auto space-y-8">
            <div>
              <h2 className="text-2xl font-bold mb-1">Assemble Prior Art Reference Pool</h2>
              <p className="text-sm text-slate-400">Add reference numbers manually or upload an Excel file column A mapping list.</p>
            </div>

            {uploadMsg && (
              <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-sm">
                {uploadMsg}
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="bg-slate-950/40 border border-slate-800 rounded-2xl p-6 space-y-4">
                <h3 className="font-bold flex items-center gap-2"><Database className="w-5 h-5 text-indigo-400" /> Manual Patent Entry</h3>
                <p className="text-xs text-slate-400">Enter comma-separated patent numbers.</p>
                <textarea
                  value={priorArtInput}
                  onChange={(e) => setPriorArtInput(e.target.value)}
                  placeholder="e.g. US5920859A, US6000000A"
                  rows={4}
                  className="w-full bg-slate-900 border border-slate-800 rounded-xl p-3 focus:outline-none focus:border-indigo-500 font-mono text-sm"
                />
                <button
                  onClick={handleAddManualPriorArt}
                  className="bg-indigo-600 hover:bg-indigo-500 px-5 py-2.5 rounded-xl font-semibold text-sm transition"
                >
                  Add Prior Art Numbers
                </button>
              </div>

              <div className="bg-slate-950/40 border border-slate-800 rounded-2xl p-6 flex flex-col justify-between">
                <div className="space-y-3">
                  <h3 className="font-bold flex items-center gap-2"><Database className="w-5 h-5 text-indigo-400" /> Excel Spreadsheet Upload</h3>
                  <p className="text-xs text-slate-400 leading-relaxed">
                    Upload your spreadsheet list. We securely parse column A matching lists dynamically on the backend.
                  </p>
                </div>

                <div className="border-2 border-dashed border-slate-800 rounded-xl p-6 text-center hover:border-indigo-500 transition cursor-pointer relative mt-4">
                  <input
                    type="file"
                    onChange={handleExcelUpload}
                    accept=".xlsx,.xls"
                    className="absolute inset-0 opacity-0 cursor-pointer"
                  />
                  <FileDown className="w-8 h-8 text-indigo-400 mx-auto mb-2" />
                  <span className="text-xs font-semibold text-slate-400">Choose .xlsx file to upload</span>
                </div>
              </div>
            </div>

            <div className="bg-slate-950/20 border border-slate-800/80 rounded-2xl p-6">
              <h3 className="font-bold mb-4">Ingested Reference Pool ({priorArtList?.length})</h3>

              {priorArtList?.length === 0 ? (
                <p className="text-sm text-slate-500 text-center py-6">No references added yet.</p>
              ) : (
                <div className="divide-y divide-slate-800/60">
                  {priorArtList?.map((art) => {
                    const rawStatus = embedStatuses[art?.patent_number] || art?.fetch_status || "unknown";
                    const embedStatus = rawStatus.toLowerCase();
                    const isProcessing = ["pending", "fetching", "embedding"].includes(embedStatus);

                    let displayText = embedStatus.toUpperCase();
                    if (embedStatus === "done" || embedStatus === "success") displayText = "✅ Ready";
                    else if (embedStatus === "embedding") displayText = "⚙️ AI Processing...";
                    else if (embedStatus === "fetching") displayText = "🌐 Fetching...";
                    else if (embedStatus === "pending") displayText = "🕒 Pending...";
                    else if (embedStatus === "failed") displayText = "❌ Failed";

                    return (
                      <div key={art?.id} className="py-3 flex justify-between items-center">
                        <div>
                          <span
                            onClick={() => !isProcessing && handleEmbedPatent(art?.patent_number)}
                            className={`font-mono font-bold ${isProcessing ? 'text-slate-500 cursor-not-allowed' : 'text-indigo-400 hover:text-indigo-300 hover:underline cursor-pointer'} transition`}
                            title={isProcessing ? "Currently processing..." : "Click to manually re-embed"}
                          >
                            {art?.patent_number}
                          </span>
                          <span className="text-xs text-slate-500 ml-4">{art?.title || "Loading abstract..."}</span>
                        </div>
                        <div className="flex gap-2 items-center">
                          {isProcessing && <Loader2 className="w-3 h-3 text-indigo-400 animate-spin" />}
                          <span className={`text-xs px-2 py-0.5 rounded font-mono font-bold uppercase ${(embedStatus === 'done' || embedStatus === 'success')
                            ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                            : embedStatus === 'failed'
                              ? "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                              : "bg-slate-800 text-slate-400 animate-pulse"
                            }`}>
                            {displayText}
                          </span>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>

            <div className="flex justify-between items-center">
              <button onClick={() => setStep(3)} className="text-slate-400 hover:text-white flex items-center gap-2">
                <ArrowLeft className="w-4 h-4" /> Back to weights
              </button>
              <button
                onClick={handleRunAnalysisAll}
                disabled={priorArtList?.some(art => ["pending", "fetching", "embedding"].includes(embedStatuses[art.patent_number]))}
                className={`px-6 py-2.5 rounded-xl font-semibold transition flex items-center gap-2 ${priorArtList?.some(art => ["pending", "fetching", "embedding"].includes(embedStatuses[art?.patent_number]))
                  ? "bg-slate-800 text-slate-500 cursor-not-allowed"
                  : "bg-indigo-600 hover:bg-indigo-500 shadow-lg shadow-indigo-600/20"
                  }`}
              >
                <Play className="w-4 h-4" /> {priorArtList.some(art => ["pending", "fetching", "embedding"].includes(embedStatuses[art.patent_number])) ? "Processing..." : "Run Deep Obviousness Analysis →"}
              </button>
            </div>
          </div>
        )}

        {step === 5 && (
          <div className="space-y-8">
            {analysisStatus && analysisStatus?.percent_complete < 100 && (
              <div className="bg-slate-950/40 border border-slate-800 rounded-2xl p-6 space-y-3">
                <div className="flex justify-between text-sm">
                  <span className="font-semibold text-indigo-400">Processing Background Analysis...</span>
                  <span className="font-mono">{analysisStatus?.percent_complete}%</span>
                </div>
                <div className="w-full h-2 bg-slate-900 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-indigo-500 transition-all duration-500"
                    style={{ width: `${analysisStatus?.percent_complete}%` }}
                  />
                </div>
                <p className="text-xs text-slate-400 leading-relaxed font-mono">
                  Jobs are running asynchronously on the server and will persist even if this window is closed.
                </p>
              </div>
            )}

            {matrixData && (
              <div className="flex w-full overflow-hidden">
                <FilterSidebar 
                  FilteredMatrix={FilteredMatrix} 
                  matrixFilter={matrixFilter} 
                  setMatrixFilter={setMatrixFilter} 
                />

                <MatrixTable 
                  matrixData={matrixData}
                  filteredRows={filteredRows()}
                  selectedMatrixPatents={selectedMatrixPatents}
                  handleToggleMatrixPatent={handleToggleMatrixPatent}
                  handleCreateMultipleCharts={handleCreateMultipleCharts}
                  chartStatuses={chartStatuses}
                  handleViewChart={handleViewChart}
                  handleDownloadReport={handleDownloadReport}
                />
              </div>
            )}
          </div>
        )}

        {step === 6 && selectedRefPatent && chartData && (
          <div className="space-y-6">
            <div className="flex justify-between items-center flex-wrap gap-4">
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setStep(5)}
                  className="bg-slate-900 hover:bg-slate-800 border border-slate-800 p-2.5 rounded-xl text-slate-400 hover:text-white"
                >
                  <ArrowLeft className="w-4 h-4" />
                </button>
                <div>
                  <h2 className="text-xl font-bold flex items-center gap-2">
                    Claim Chart Summary
                    {(() => {
                      const matrixRow = matrixData?.rows?.find((r: any) => r.reference_patent_id === selectedRefPatent.reference_patent_id);
                      const vectorScore = matrixRow ? matrixRow.score.toFixed(1) : "0.0";
                      const llmScore = chartData?.llm_score !== undefined ? chartData.llm_score.toFixed(1) : "0.0";
                      return (
                        <div className="flex gap-2 ml-4">
                          <div className="bg-slate-900 border border-slate-700 px-3 py-1 rounded-full text-xs flex items-center gap-1">
                            ⚡ <span className="text-slate-400">Vector Score:</span> <span className="text-white font-mono font-bold">{vectorScore}%</span>
                          </div>
                          <div className="bg-indigo-900/40 border border-indigo-500/50 px-3 py-1 rounded-full text-xs flex items-center gap-1">
                            🧠 <span className="text-indigo-300">LLM Score:</span> <span className="text-white font-mono font-bold">{llmScore}%</span>
                          </div>
                        </div>
                      );
                    })()}
                  </h2>
                  <p className="text-xs text-slate-400 font-mono mt-1">Subject: {patentNum} vs Prior Art: {selectedRefPatent.patent_number}</p>
                </div>
              </div>

              <div className="flex flex-col items-end gap-2">
                <div className="flex items-center gap-2">
                  {isEditingChart ? (
                    <React.Fragment>
                      <button
                        onClick={handleSaveChartEdits}
                        className="bg-emerald-600 hover:bg-emerald-500 px-4 py-2.5 rounded-xl font-semibold text-xs transition flex items-center gap-1"
                      >
                        <Check className="w-4 h-4" /> Save Persisted Edits
                      </button>
                      <button
                        onClick={() => {
                          setChartRows(chartData.chart_rows || []);
                          setIsEditingChart(false);
                        }}
                        className="bg-slate-800 hover:bg-slate-700 px-4 py-2.5 rounded-xl text-xs"
                      >
                        Cancel
                      </button>
                    </React.Fragment>
                  ) : (
                    <React.Fragment>
                      <button
                        onClick={() => setIsEditingChart(true)}
                        className="bg-indigo-600 hover:bg-indigo-500 px-4 py-2.5 rounded-xl font-semibold text-xs transition flex items-center gap-1"
                      >
                        <Edit3 className="w-4 h-4" /> Customize Rationale
                      </button>

                      <button
                        onClick={() => handleDownloadReport('docx')}
                        className="bg-slate-800 hover:bg-slate-700 px-3 py-2.5 border border-slate-700 rounded-xl text-xs font-semibold flex items-center gap-1"
                      >
                        Word (.docx)
                      </button>
                      <button
                        onClick={() => handleDownloadReport('xlsx')}
                        className="bg-slate-800 hover:bg-slate-700 px-3 py-2.5 border border-slate-700 rounded-xl text-xs font-semibold flex items-center gap-1"
                      >
                        Excel (.xlsx)
                      </button>
                      <button
                        onClick={() => handleDownloadReport('pdf')}
                        className="bg-slate-800 hover:bg-slate-700 px-3 py-2.5 border border-slate-700 rounded-xl text-xs font-semibold flex items-center gap-1"
                      >
                        PDF (.pdf)
                      </button>
                    </React.Fragment>
                  )}
                </div>
                
                {multiChartData.length > 1 && !isEditingChart && (
                  <div className="flex items-center gap-1 bg-slate-900/60 px-2 py-1 rounded-lg border border-slate-800 shadow-sm mt-1">
                    <button 
                      onClick={() => handleCarouselChange("prev")}
                      disabled={carouselIndex === 0}
                      className="p-1 text-slate-400 disabled:text-slate-700 hover:text-white hover:bg-slate-800 rounded transition"
                    >
                      <ChevronLeft className="w-4 h-4" />
                    </button>
                    
                    <div className="flex items-center gap-1 font-mono text-xs text-indigo-400 mx-1">
                      <input 
                        type="text" 
                        value={carouselInputValue}
                        onChange={(e) => setCarouselInputValue(e.target.value)}
                        onKeyDown={handleCarouselInputSubmit}
                        className="w-6 text-center bg-transparent border-b border-slate-600 hover:border-indigo-500 focus:border-indigo-400 focus:outline-none text-indigo-300 transition-colors"
                      />
                      <span className="text-slate-500">/</span>
                      <span className="text-slate-500">{multiChartData.length}</span>
                    </div>

                    <button 
                      onClick={() => handleCarouselChange("next")}
                      disabled={carouselIndex === multiChartData.length - 1}
                      className="p-1 text-slate-400 disabled:text-slate-700 hover:text-white hover:bg-slate-800 rounded transition"
                    >
                      <ChevronRight className="w-4 h-4" />
                    </button>
                  </div>
                )}
              </div>
            </div>

            <div className="bg-slate-950/40 border border-slate-800 rounded-2xl overflow-hidden">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-slate-800 bg-slate-900/60 font-mono text-xs uppercase text-slate-400">
                    <th className="p-4 w-20">ID</th>
                    <th className="p-4 w-1/4">Claim limitation (Subject)</th>
                    <th className="p-4 w-1/4">Prior Art Citation ({selectedRefPatent.patent_number})</th>
                    <th className="p-4 w-32">Location (Ref)</th>
                    <th className="p-4">Obviousness / Rationale Explanation</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 text-sm">
                  {chartRows.map((row, idx) => (
                    <tr key={idx} className="hover:bg-slate-900/20">
                      <td className="p-4 font-mono font-bold text-indigo-400 align-top">{row.element_id}</td>
                      <td className="p-4 text-slate-300 leading-relaxed text-xs align-top">{row.claim_text}</td>
                      <td className="p-4 align-top">
                        {isEditingChart ? (
                          <textarea
                            value={row.cited_passage}
                            onChange={(e) => handleUpdateChartRow(idx, "cited_passage", e.target.value)}
                            rows={3}
                            className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2 text-xs focus:outline-none focus:border-indigo-500 font-mono text-slate-300"
                          />
                        ) : (
                          <p className="text-slate-400 leading-relaxed text-xs italic">"{row.cited_passage}"</p>
                        )}
                      </td>
                      <td className="p-4 align-top font-mono text-xs space-y-1">
                        {isEditingChart ? (
                          <React.Fragment>
                            <input
                              type="text"
                              value={row.para_ref}
                              onChange={(e) => handleUpdateChartRow(idx, "para_ref", e.target.value)}
                              placeholder="Para"
                              className="w-full bg-slate-900 border border-slate-800 rounded px-1.5 py-1 text-xxs font-bold text-slate-300 focus:outline-none"
                            />
                            <input
                              type="text"
                              value={row.fig_ref}
                              onChange={(e) => handleUpdateChartRow(idx, "fig_ref", e.target.value)}
                              placeholder="Figure"
                              className="w-full bg-slate-900 border border-slate-800 rounded px-1.5 py-1 text-xxs font-bold text-slate-300 focus:outline-none mt-1"
                            />
                          </React.Fragment>
                        ) : (
                          <React.Fragment>
                            <div>Para: {row.para_ref || "N/A"}</div>
                            <div>Fig: {row.fig_ref || "N/A"}</div>
                          </React.Fragment>
                        )}
                      </td>
                      <td className="p-4 align-top">
                        {isEditingChart ? (
                          <textarea
                            value={row.rationale}
                            onChange={(e) => handleUpdateChartRow(idx, "rationale", e.target.value)}
                            rows={4}
                            className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2 text-xs focus:outline-none focus:border-indigo-500 text-slate-300"
                          />
                        ) : (
                          <p className="text-slate-300 leading-relaxed text-xs">{row.rationale}</p>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
