"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Sparkles,
  X,
  Send,
  Bot,
  User,
  ChevronDown,
  Cpu,
  Layers,
  HelpCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface SourceCitation {
  source: string;
  section: string;
  title: string;
  score?: number;
  snippet?: string;
}

interface ChatMessage {
  id: string;
  sender: "user" | "copilot";
  text: string;
  backend?: string;
  sources?: SourceCitation[];
  latency_ms?: number;
  timestamp: string;
}

const suggestedPrompts = [
  "Lookup NPI 1003017351",
  "What are the rates for billing code 99214?",
  "Show top provider specialties and price ranges",
  "Pipeline data record summary across all stages",
  "Why was NLP cosine similarity insufficient in C2?",
  "Explain rule R-C2-03 (restrictive token override)",
  "How does the C4 rate conflict resolution hierarchy work?",
  "Why can't we trust NPPES addresses alone in C5?",
];

function parseInline(text: string): React.ReactNode[] {
  // Normalize common math notations
  const normalized = text
    .replace(/\$\\ge\s*/g, "≥ ")
    .replace(/\$\\le\s*/g, "≤ ")
    .replace(/\$(.*?)\$/g, "$1");

  // Split on bold (**text**) and inline code (`code`)
  const parts = normalized.split(/(\*\*.*?\*\*|`.*?`)/g);

  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={index} className="font-semibold text-foreground">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code
          key={index}
          className="px-1.5 py-0.5 rounded bg-muted text-primary font-mono text-[11px] border border-border/60"
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    return <span key={index}>{part}</span>;
  });
}

export function PipelineCopilot() {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "init",
      sender: "copilot",
      text: "👋 Hi! I'm your **Pipeline Copilot** powered by grounded Centene PTD pipeline data.\n\nAsk me any technical question about our stages, rules (`R-C2-01` to `R-C4-SEL-07`), NLP evaluation, or address triangulation.",
      backend: "Local Pipeline Knowledge Base",
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    },
  ]);
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  const sendMessage = async (textToSend?: string) => {
    const query = textToSend || input;
    if (!query.trim() || loading) return;

    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      sender: "user",
      text: query.trim(),
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    if (!textToSend) setInput("");
    setLoading(true);

    try {
      const res = await fetch("/api/copilot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: query }),
      });

      if (!res.ok) throw new Error("Failed to get response");
      const data = await res.json();

      const copilotMsg: ChatMessage = {
        id: `c-${Date.now()}`,
        sender: "copilot",
        text: data.answer || "No response received.",
        backend: data.backend,
        sources: data.sources || [],
        latency_ms: data.latency_ms,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };

      setMessages((prev) => [...prev, copilotMsg]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          sender: "copilot",
          text: "⚠️ Sorry, encountered an issue querying the pipeline knowledge base. Please try again.",
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  // Structured Markdown Parser with Table Support for Clean UI Display
  const renderFormattedText = (raw: string) => {
    const lines = raw.split("\n");
    const elements: React.ReactNode[] = [];
    let currentList: { type: "ul" | "ol"; items: React.ReactNode[] } | null = null;
    let tableLines: string[] = [];

    const flushTable = () => {
      if (tableLines.length >= 2) {
        const rows = tableLines.map((line) =>
          line
            .trim()
            .replace(/^\|/, "")
            .replace(/\|$/, "")
            .split("|")
            .map((c) => c.trim())
        );
        const headers = rows[0];
        // Skip separator row (contains ---)
        const dataRows = rows.slice(1).filter((r) => !r.every((c) => /^:?-+:?$/.test(c)));

        elements.push(
          <div
            key={`tbl-${elements.length}`}
            className="my-2.5 overflow-x-auto rounded-lg border border-border/80 shadow-xs"
          >
            <table className="w-full text-[11px] text-left border-collapse">
              <thead className="bg-muted/80 text-foreground font-semibold border-b border-border">
                <tr>
                  {headers.map((h, hIdx) => (
                    <th key={hIdx} className="px-2.5 py-1.5 whitespace-nowrap">
                      {parseInline(h)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40">
                {dataRows.map((r, rIdx) => (
                  <tr key={rIdx} className={rIdx % 2 === 0 ? "bg-card" : "bg-muted/20"}>
                    {r.map((cell, cIdx) => (
                      <td key={cIdx} className="px-2.5 py-1.5 whitespace-nowrap">
                        {parseInline(cell)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      }
      tableLines = [];
    };

    const flushList = () => {
      if (currentList) {
        if (currentList.type === "ul") {
          elements.push(
            <ul key={`ul-${elements.length}`} className="my-1.5 space-y-1 list-disc pl-4 text-xs">
              {currentList.items.map((item, idx) => (
                <li key={idx} className="leading-relaxed text-foreground/90">
                  {item}
                </li>
              ))}
            </ul>
          );
        } else {
          elements.push(
            <ol key={`ol-${elements.length}`} className="my-1.5 space-y-1 list-decimal pl-4 text-xs">
              {currentList.items.map((item, idx) => (
                <li key={idx} className="leading-relaxed text-foreground/90 font-medium">
                  {item}
                </li>
              ))}
            </ol>
          );
        }
        currentList = null;
      }
    };

    lines.forEach((line, i) => {
      const trimmed = line.trim();

      // Check if line is a table row
      if (trimmed.startsWith("|") && trimmed.endsWith("|")) {
        flushList();
        tableLines.push(trimmed);
        return;
      } else if (tableLines.length > 0) {
        flushTable();
      }

      if (!trimmed) {
        flushList();
        elements.push(<div key={`sp-${i}`} className="h-1.5" />);
        return;
      }

      // Heading 3 / 4
      if (trimmed.startsWith("### ")) {
        flushList();
        elements.push(
          <h4 key={`h-${i}`} className="font-bold text-sm text-primary mt-2.5 mb-1 pb-1 border-b border-border/50">
            {parseInline(trimmed.replace("### ", ""))}
          </h4>
        );
        return;
      }

      // Unordered list item
      if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
        const content = trimmed.replace(/^[-*]\s+/, "");
        if (!currentList || currentList.type !== "ul") {
          flushList();
          currentList = { type: "ul", items: [] };
        }
        currentList.items.push(parseInline(content));
        return;
      }

      // Ordered list item
      const numMatch = trimmed.match(/^(\d+)\.\s+(.*)$/);
      if (numMatch) {
        const content = numMatch[2];
        if (!currentList || currentList.type !== "ol") {
          flushList();
          currentList = { type: "ol", items: [] };
        }
        currentList.items.push(parseInline(content));
        return;
      }

      // Standard paragraph
      flushList();
      elements.push(
        <p key={`p-${i}`} className="text-xs leading-relaxed my-1 text-foreground/90">
          {parseInline(trimmed)}
        </p>
      );
    });

    flushList();
    flushTable();
    return elements;
  };

  return (
    <>
      {/* Floating Action Button */}
      <div className="fixed bottom-20 lg:bottom-6 right-4 sm:right-6 z-40">
        {!isOpen && (
          <motion.div
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            whileHover={{ scale: 1.04 }}
            whileTap={{ scale: 0.96 }}
          >
            <Button
              onClick={() => setIsOpen(true)}
              className="h-11 sm:h-12 px-4 sm:px-5 py-2.5 rounded-full bg-primary hover:bg-primary/90 text-primary-foreground shadow-2xl flex items-center gap-2 sm:gap-2.5 font-bold text-xs sm:text-sm ring-4 ring-primary/20 transition-all cursor-pointer"
            >
              <Sparkles className="h-4 w-4 text-amber-300 animate-pulse flex-shrink-0" />
              <span>Ask Pipeline Copilot</span>
              <Badge className="bg-white/20 text-white text-[10px] px-1.5 py-0 font-mono ml-0.5 sm:ml-1">
                Qwen 2.5
              </Badge>
            </Button>
          </motion.div>
        )}
      </div>

      {/* Floating Chat Modal */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.95 }}
            transition={{ duration: 0.2 }}
            className="fixed bottom-4 sm:bottom-6 right-4 sm:right-6 z-50 w-[calc(100vw-2rem)] sm:w-[470px] h-[540px] max-h-[calc(100vh-5rem)] flex flex-col rounded-2xl border border-border shadow-2xl bg-card overflow-hidden"
          >
            {/* Header - flex-shrink-0 ensures it is NEVER cropped or squeezed */}
            <div className="p-3 bg-gradient-to-r from-primary/10 via-background to-accent/15 border-b border-border flex items-center justify-between flex-shrink-0">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-xl bg-primary text-primary-foreground shadow-sm flex-shrink-0">
                  <Bot className="h-4 w-4" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-sm text-foreground">Pipeline Copilot</span>
                    <Badge variant="outline" className="text-[10px] font-mono border-primary/30 text-primary px-1.5 py-0">
                      Qwen 2.5 / RAG
                    </Badge>
                  </div>
                  <p className="text-[11px] text-muted-foreground flex items-center gap-1.5">
                    <span className="inline-block w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                    Centene PTD Grounded Knowledge Engine
                  </p>
                </div>
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setIsOpen(false)}
                className="h-8 w-8 rounded-full text-muted-foreground hover:text-foreground cursor-pointer flex-shrink-0"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>

            {/* Prompt Chips Bar */}
            <div className="px-3 py-2 bg-muted/20 border-b border-border/60 overflow-x-auto flex gap-1.5 scrollbar-none flex-shrink-0">
              {suggestedPrompts.map((prompt, i) => (
                <button
                  key={i}
                  onClick={() => sendMessage(prompt)}
                  className="whitespace-nowrap px-2.5 py-1 rounded-full text-[11px] font-medium bg-background border border-border/80 hover:border-primary/60 hover:text-primary transition-all text-muted-foreground flex-shrink-0 cursor-pointer shadow-xs"
                >
                  {prompt}
                </button>
              ))}
            </div>

            {/* Messages Scroll Area with custom sleek scrollbar */}
            <div
              ref={scrollRef}
              className="flex-1 p-3.5 overflow-y-auto space-y-3.5 text-xs [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-border hover:[&::-webkit-scrollbar-thumb]:bg-muted-foreground/30 [&::-webkit-scrollbar-thumb]:rounded-full"
            >
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={cn(
                    "flex gap-2 max-w-[94%]",
                    msg.sender === "user" ? "ml-auto flex-row-reverse" : "mr-auto"
                  )}
                >
                  <div
                    className={cn(
                      "w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 text-[10px] font-bold mt-0.5 shadow-xs",
                      msg.sender === "user"
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted text-foreground border border-border"
                    )}
                  >
                    {msg.sender === "user" ? <User className="h-3 w-3" /> : <Bot className="h-3.5 w-3.5 text-primary" />}
                  </div>

                  <div className="space-y-1 overflow-hidden">
                    <div
                      className={cn(
                        "p-3 rounded-2xl shadow-xs leading-relaxed",
                        msg.sender === "user"
                          ? "bg-primary text-primary-foreground rounded-tr-none text-xs"
                          : "bg-muted/40 border border-border/80 text-foreground rounded-tl-none"
                      )}
                    >
                      {msg.sender === "user" ? (
                        <p className="text-xs">{msg.text}</p>
                      ) : (
                        renderFormattedText(msg.text)
                      )}
                    </div>
                    {msg.sources && msg.sources.length > 0 && (
                      <details className="mt-1.5 text-[10px] bg-background/80 rounded-lg border border-border/70 p-2 cursor-pointer transition-all">
                        <summary className="font-semibold text-primary flex items-center justify-between select-none">
                          <span className="flex items-center gap-1.5">
                            <Sparkles className="h-3 w-3 text-amber-500" />
                            Verified Citations & Sources ({msg.sources.length})
                          </span>
                          {msg.latency_ms && (
                            <span className="text-[9px] text-muted-foreground font-mono">
                              {msg.latency_ms}ms
                            </span>
                          )}
                        </summary>
                        <div className="mt-2 space-y-1.5 pt-1.5 border-t border-border/50">
                          {msg.sources.map((s, idx) => (
                            <div key={idx} className="flex items-start justify-between gap-2 p-1 rounded bg-muted/40">
                              <div className="min-w-0 flex-1">
                                <span className="font-medium text-foreground block truncate">{s.title || s.section}</span>
                                <span className="text-[9px] text-muted-foreground font-mono block truncate">{s.source}</span>
                              </div>
                              {s.score !== undefined && (
                                <span className="flex-shrink-0 font-mono text-[9px] px-1.5 py-0.5 rounded bg-primary/10 text-primary font-semibold">
                                  {(s.score * 100).toFixed(1)}% match
                                </span>
                              )}
                            </div>
                          ))}
                        </div>
                      </details>
                    )}
                    {msg.backend && (
                      <div className="text-[10px] text-muted-foreground flex items-center gap-1 px-1">
                        <span>{msg.backend}</span>
                        <span>•</span>
                        <span>{msg.timestamp}</span>
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {loading && (
                <div className="flex gap-2 mr-auto max-w-[85%]">
                  <div className="w-6 h-6 rounded-full bg-muted border border-border flex items-center justify-center flex-shrink-0 mt-0.5">
                    <Bot className="h-3.5 w-3.5 text-primary animate-pulse" />
                  </div>
                  <div className="p-3 rounded-2xl bg-muted/30 border border-border text-foreground rounded-tl-none flex items-center gap-2 text-xs text-muted-foreground">
                    <Sparkles className="h-3.5 w-3.5 animate-spin text-primary" />
                    <span>Analyzing pipeline knowledge base...</span>
                  </div>
                </div>
              )}
            </div>

            {/* Input Bar - flex-shrink-0 ensures it is always visible */}
            <div className="p-2.5 bg-card border-t border-border flex items-center gap-2 flex-shrink-0">
              <Input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask about C1-C6, rules, NLP, rates, addresses..."
                className="text-xs h-9 bg-background border-border shadow-xs"
                disabled={loading}
              />
              <Button
                onClick={() => sendMessage()}
                disabled={loading || !input.trim()}
                size="icon"
                className="h-9 w-9 flex-shrink-0 rounded-xl bg-primary text-primary-foreground cursor-pointer shadow-xs"
              >
                <Send className="h-3.5 w-3.5" />
              </Button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
