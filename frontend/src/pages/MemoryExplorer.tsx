import React, { useState } from 'react';
import { searchMemory } from '../api/client';
import type { MemoryRecord } from '../types/aegis';
import {
  Database,
  Search,
  SlidersHorizontal,
  RefreshCw,
  AlertCircle,
  Tag,
  Sparkles,
} from 'lucide-react';

export const MemoryExplorer: React.FC = () => {
  const [queryText, setQueryText] = useState<string>('agent security policies and compliance constraints');
  const [memoryType, setMemoryType] = useState<string>('all');
  const [limit, setLimit] = useState<number>(10);
  const [scoreThreshold, setScoreThreshold] = useState<number>(0.0);
  const [results, setResults] = useState<MemoryRecord[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState<boolean>(false);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!queryText.trim()) return;

    setLoading(true);
    setError(null);
    setHasSearched(true);

    try {
      const res = await searchMemory({
        query_text: queryText.trim(),
        memory_type: memoryType === 'all' ? null : memoryType,
        limit,
        score_threshold: scoreThreshold > 0 ? scoreThreshold : undefined,
      });
      setResults(res.matches || []);
      setTotalCount(res.count ?? res.matches?.length ?? 0);
    } catch (err: unknown) {
      const e = err as Error;
      setError(e.message || 'Failed to query AEGIS memory subsystem');
    } finally {
      setLoading(false);
    }
  };

  const getTypeBadge = (type: string) => {
    switch (type.toLowerCase()) {
      case 'procedural':
        return (
          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-cyan-950 text-cyan-400 border border-cyan-800">
            Procedural
          </span>
        );
      case 'episodic':
        return (
          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-purple-950 text-purple-400 border border-purple-800">
            Episodic
          </span>
        );
      case 'semantic':
        return (
          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-950 text-emerald-400 border border-emerald-800">
            Semantic
          </span>
        );
      default:
        return (
          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-gray-800 text-gray-300 border border-gray-700">
            {type}
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="border-b border-gray-800 pb-5">
        <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
          <Database className="w-6 h-6 text-cyan-400" />
          Multi-Tier Memory & Knowledge Retrieval
        </h1>
        <p className="text-xs text-gray-400 mt-1">
          Unified vector search across Episodic (past executions), Semantic (facts & context), and Procedural (learned skills) stores.
        </p>
      </div>

      {/* Search Input Box & Controls */}
      <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-5 space-y-4">
        <form onSubmit={handleSearch} className="space-y-4">
          <div className="flex gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3.5 top-2.5 w-4 h-4 text-gray-400" />
              <input
                type="text"
                required
                value={queryText}
                onChange={(e) => setQueryText(e.target.value)}
                placeholder="Query memory system by natural language query or task context..."
                className="w-full rounded-xl border border-gray-700 bg-gray-950 pl-10 pr-4 py-2 text-xs text-gray-100 placeholder-gray-500 focus:border-cyan-500 focus:outline-none"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="flex items-center space-x-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 px-5 py-2 text-xs font-medium text-white transition-colors disabled:opacity-50"
            >
              {loading ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Searching Vector Store...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>Search Memory</span>
                </>
              )}
            </button>
          </div>

          {/* Filter Row */}
          <div className="flex flex-wrap items-center gap-6 pt-1 text-xs text-gray-400">
            <div className="flex items-center space-x-2">
              <Tag className="w-3.5 h-3.5 text-cyan-400" />
              <span>Memory Tier:</span>
              <select
                value={memoryType}
                onChange={(e) => setMemoryType(e.target.value)}
                className="rounded-lg border border-gray-700 bg-gray-950 px-2 py-1 text-xs text-gray-200 focus:border-cyan-500 focus:outline-none"
              >
                <option value="all">All Tiers</option>
                <option value="episodic">Episodic (Traversing logs)</option>
                <option value="semantic">Semantic (Embeddings/Facts)</option>
                <option value="procedural">Procedural (Learned skills)</option>
              </select>
            </div>

            <div className="flex items-center space-x-2">
              <SlidersHorizontal className="w-3.5 h-3.5 text-cyan-400" />
              <span>Limit:</span>
              <select
                value={limit}
                onChange={(e) => setLimit(Number(e.target.value))}
                className="rounded-lg border border-gray-700 bg-gray-950 px-2 py-1 text-xs text-gray-200 focus:border-cyan-500 focus:outline-none"
              >
                <option value={5}>5 records</option>
                <option value={10}>10 records</option>
                <option value={25}>25 records</option>
                <option value={50}>50 records</option>
              </select>
            </div>

            <div className="flex items-center space-x-2">
              <span>Threshold:</span>
              <input
                type="range"
                min={0.0}
                max={1.0}
                step={0.05}
                value={scoreThreshold}
                onChange={(e) => setScoreThreshold(Number(e.target.value))}
                className="w-24 accent-cyan-500"
              />
              <span className="font-mono text-cyan-400 text-[11px] w-8">
                {scoreThreshold.toFixed(2)}
              </span>
            </div>
          </div>
        </form>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-950/20 p-4 text-xs text-rose-300 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
          <span>{error}</span>
        </div>
      )}

      {/* Results Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-400">
          Search Matches {hasSearched && `(${totalCount} found)`}
        </h2>
      </div>

      {/* Results List */}
      {results.length === 0 ? (
        <div className="rounded-xl border border-gray-800 bg-gray-900/20 p-12 text-center text-gray-500 text-xs">
          {hasSearched ? (
            <div>
              <Database className="w-8 h-8 mx-auto mb-2 opacity-30 text-cyan-400" />
              <p>No matching memory records found for this query and threshold.</p>
              <p className="text-[11px] text-gray-600 mt-1">
                Try lowering the similarity threshold or searching with broader keywords.
              </p>
            </div>
          ) : (
            <div>
              <Database className="w-8 h-8 mx-auto mb-2 opacity-30" />
              <p>Submit a search query to explore vectorized memory records.</p>
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {results.map((rec) => {
            const pct = Math.min(100, Math.max(0, Math.round(rec.score * 100)));
            return (
              <div
                key={rec.record_id}
                className="rounded-xl border border-gray-800 bg-gray-900/40 p-4 hover:border-gray-700 transition-colors space-y-3"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div className="flex items-center space-x-2.5">
                    {getTypeBadge(rec.memory_type)}
                    <span className="font-mono text-xs font-medium text-white">
                      {rec.record_id}
                    </span>
                  </div>

                  {/* Similarity Gauge */}
                  <div className="flex items-center space-x-2">
                    <span className="text-[11px] text-gray-400 font-mono">
                      Relevance: {rec.score.toFixed(3)}
                    </span>
                    <div className="w-20 h-2 bg-gray-800 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-cyan-500 to-emerald-400 rounded-full"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                </div>

                <div className="rounded-lg bg-gray-950/80 border border-gray-800/80 p-3 text-xs text-gray-200 font-mono whitespace-pre-wrap leading-relaxed">
                  {rec.content}
                </div>

                {rec.metadata && Object.keys(rec.metadata).length > 0 && (
                  <div className="text-[11px] text-gray-400">
                    <span className="text-gray-500 font-semibold">Metadata: </span>
                    <span className="font-mono text-gray-300">
                      {JSON.stringify(rec.metadata)}
                    </span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
