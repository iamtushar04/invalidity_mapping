"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  Sparkles, FileText, Plus, Folder, ArrowRight,
  Lock, Mail, UserPlus, LogIn, Loader2
} from "lucide-react";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL as string;
const AUTH_URL = process.env.NEXT_PUBLIC_AUTH_URL as string;

export default function HomePage() {
  const router = useRouter();

  // Auth state
  const [token, setToken] = useState<string | null>(null);
  const [email, setEmail] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [authError, setAuthError] = useState<string | null>(null);

  // Projects state
  const [projects, setProjects] = useState<any[]>([]);
  const [newProjectName, setNewProjectName] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(() => {
    const storedToken = localStorage.getItem("token");
    if (storedToken) {
      setToken(storedToken);
      fetchProjects(storedToken);
    }
  }, []);

  const fetchProjects = async (authToken: string) => {
    setLoading(true);
    try {
      const res = await fetch(`${BACKEND_URL}/projects`, {
        headers: { Authorization: `Bearer ${authToken}` }
      });
      if (res.ok) {
        const data = await res.json();
        setProjects(data);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setAuthError(null);


    try {
      const res = await fetch(AUTH_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email, password: password })
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Invalid credentials.");
      }
      const data = await res.json();
      localStorage.setItem("token", data.access_token);
      setToken(data.access_token);
      fetchProjects(data.access_token);
    } catch (err: any) {
      setAuthError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectName.trim() || !token) return;
    setLoading(true);
    try {
      const res = await fetch(`${BACKEND_URL}/projects`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ name: newProjectName })
      });
      if (res.ok) {
        const data = await res.json();
        setNewProjectName("");
        router.push(`/project/${data.id}`);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    setToken(null);
    setProjects([]);
  };

  return (
    <div className="min-h-screen bg-[#070b13] text-slate-100 flex flex-col font-sans justify-center items-center p-8">
      <div className="fixed -top-40 -left-40 w-96 h-96 bg-indigo-600/10 rounded-full blur-[100px] pointer-events-none" />
      <div className="fixed -bottom-40 -right-40 w-96 h-96 bg-indigo-500/10 rounded-full blur-[100px] pointer-events-none" />

      <div className="text-center mb-12 max-w-lg relative z-10">
        <div className="inline-flex bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 p-2.5 rounded-2xl mb-4">
          <Sparkles className="w-8 h-8" />
        </div>
        <h1 className="text-4xl font-extrabold tracking-tight bg-gradient-to-r from-indigo-200 via-indigo-100 to-indigo-300 bg-clip-text text-transparent mb-3">
          Antigravity Invalidity Suite
        </h1>
        <p className="text-slate-400 text-sm leading-relaxed">
          Premium legal-tech tooling providing robust mapping segmentations, Obviousness logic routing, and claim chart exports.
        </p>
      </div>

      {loading && (
        <div className="fixed inset-0 bg-slate-950/70 backdrop-blur-sm z-50 flex flex-col items-center justify-center gap-3">
          <Loader2 className="w-12 h-12 text-indigo-500 animate-spin" />
          <p className="text-sm text-slate-300 font-medium">Connecting to secure API Gateway...</p>
        </div>
      )}

      <div className="w-full max-w-lg bg-slate-950/40 border border-slate-800/80 rounded-3xl p-8 backdrop-blur shadow-[0_8px_32px_rgba(0,0,0,0.5)] relative z-10">
        {!token ? (
          <form onSubmit={handleAuth} className="space-y-5">
            <h2 className="text-2xl font-bold text-center text-indigo-100 flex items-center justify-center gap-2">
              <LogIn className="w-6 h-6" />
              Analyst Authentication
            </h2>

            {authError && (
              <div className="p-3.5 rounded-xl bg-indigo-500/10 border border-indigo-500/30 text-indigo-300 text-xs font-semibold text-center leading-relaxed">
                {authError}
              </div>
            )}

            <div className="space-y-4">
              <div>
                <label className="block text-xs font-mono text-slate-400 uppercase tracking-widest mb-1.5">Email Address</label>
                <div className="relative">
                  <Mail className="absolute left-3.5 top-3.5 w-4 h-4 text-slate-500" />
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="analyst@firm.com"
                    className="w-full bg-slate-900 border border-slate-800 rounded-xl pl-11 pr-4 py-3 focus:outline-none focus:border-indigo-500 transition font-mono text-sm"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-mono text-slate-400 uppercase tracking-widest mb-1.5">Secret Key / Password</label>
                <div className="relative">
                  <Lock className="absolute left-3.5 top-3.5 w-4 h-4 text-slate-500" />
                  <input
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    className="w-full bg-slate-900 border border-slate-800 rounded-xl pl-11 pr-4 py-3 focus:outline-none focus:border-indigo-500 transition font-mono text-sm"
                  />
                </div>
              </div>
            </div>

            <button
              type="submit"
              className="w-full bg-indigo-600 hover:bg-indigo-500 py-3 rounded-xl font-bold transition shadow-lg shadow-indigo-600/20 flex items-center justify-center gap-2 mt-6 text-sm"
            >
              Authenticate Session
            </button>
          </form>
        ) : (
          <div className="space-y-6">
            <div className="flex justify-between items-center">
              <div>
                <h2 className="text-xl font-bold">Your Workspace Projects</h2>
                <p className="text-xs text-slate-400 font-mono">Total: {projects.length}</p>
              </div>
              <button
                onClick={handleLogout}
                className="text-xs font-mono text-slate-400 hover:text-white uppercase tracking-widest"
              >
                Logout
              </button>
            </div>

            <form onSubmit={handleCreateProject} className="flex gap-2">
              <input
                type="text"
                required
                value={newProjectName}
                onChange={(e) => setNewProjectName(e.target.value)}
                placeholder="New project title..."
                className="flex-1 bg-slate-900 border border-slate-800 rounded-xl px-4 py-2.5 focus:outline-none focus:border-indigo-500 transition text-sm"
              />
              <button
                type="submit"
                className="bg-indigo-600 hover:bg-indigo-500 px-4 rounded-xl font-semibold text-sm transition flex items-center gap-1.5"
              >
                <Plus className="w-4 h-4" /> Create
              </button>
            </form>

            <div className="space-y-3 max-h-64 overflow-y-auto pr-1">
              {projects.length === 0 ? (
                <p className="text-sm text-slate-500 text-center py-8">No active projects found. Create one to begin!</p>
              ) : (
                projects.map((proj) => (
                  <div
                    key={proj.id}
                    onClick={() => router.push(`/project/${proj.id}`)}
                    className="p-4 rounded-xl border border-slate-800 bg-slate-900/30 hover:bg-indigo-600/5 hover:border-indigo-500/40 transition cursor-pointer flex justify-between items-center group"
                  >
                    <div className="flex items-center gap-3">
                      <Folder className="w-5 h-5 text-indigo-400 group-hover:text-indigo-300" />
                      <div>
                        <div className="text-sm font-semibold text-slate-200 group-hover:text-white">{proj.name}</div>
                        <div className="text-xxs text-slate-500 font-mono">Created: {new Date(proj.created_at).toLocaleDateString()}</div>
                      </div>
                    </div>
                    <ArrowRight className="w-4 h-4 text-slate-600 group-hover:text-indigo-400 group-hover:translate-x-1 transition" />
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
