import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Send,
  Upload,
  FileText,
  Mic,
  CheckCircle,
  AlertCircle,
  Download,
  User,
  Loader2,
  RefreshCw,
  MessageSquare,
  ShieldCheck,
  Lock,
  PenLine,
  Paperclip,
  AlertTriangle,
} from "lucide-react";

import MultiSelectQuestion from "./components/MultiSelectQuestion.jsx";
import ChoiceRow from "./components/ChoiceRow.jsx";
import FieldIcon from "./components/FieldIcon.jsx";
import {
  createSession,
  fetchSchema,
  startManual,
  sendMessage,
  uploadDocument,
  downloadPDF,
} from "./api/chatApi.js";

/* =====================================================================
 *  HELPERS
 * =================================================================== */
const nowTime = () =>
  new Date().toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
  });

function formatValue(v) {
  if (v === null || v === undefined) return "";
  if (typeof v === "string" || typeof v === "number" || typeof v === "boolean")
    return String(v);
  if (Array.isArray(v)) return `${v.length} item(s)`;
  if (typeof v === "object") {
    return Object.entries(v)
      .filter(([, val]) => val)
      .map(([k, val]) => `${k.replace(/_/g, " ")}: ${val}`)
      .join(", ");
  }
  return String(v);
}

/* =====================================================================
 *  APP
 * =================================================================== */
export default function App() {
  const [schema, setSchema] = useState(null);
  const [sessionId, setSessionId] = useState(null);
  const [stage, setStage] = useState("AWAITING_UPLOAD");
  const [messages, setMessages] = useState([]);
  const [extracted, setExtracted] = useState({});
  const [missing, setMissing] = useState([]);
  const [currentField, setCurrentField] = useState(null);
  const [activeOptions, setActiveOptions] = useState(null);
  const [showProfile, setShowProfile] = useState(false);
  const [inputMessage, setInputMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState(null);

  const endRef = useRef(null);
  const fileRef = useRef(null);
  const inputRef = useRef(null);

  /* -------- Bootstrap -------- */
  useEffect(() => {
    boot();
  }, []);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, activeOptions, isLoading, isUploading]);

  /* Keep the chatbox focused whenever the bot finishes responding */
  useEffect(() => {
    if (!isLoading && !isUploading && sessionId) {
      // small timeout so DOM has settled after the message renders
      const t = setTimeout(() => inputRef.current?.focus(), 50);
      return () => clearTimeout(t);
    }
  }, [isLoading, isUploading, sessionId, messages.length]);

  async function boot() {
    try {
      // 1) Fetch schema + session in parallel
      const [schemaData, sessionData] = await Promise.all([
        fetchSchema(),
        createSession(),
      ]);
      setSchema(schemaData);
      setSessionId(sessionData.session_id);
      setStage(sessionData.stage || "AWAITING_UPLOAD");
      setMessages([
        { type: "ai", content: sessionData.bot_message, timestamp: nowTime() },
      ]);
      setError(null);
    } catch (err) {
      console.error(err);
      setError("Failed to reach the backend. Is FastAPI running on :8000?");
    }
  }

  async function handleReset() {
    setSessionId(null);
    setMessages([]);
    setExtracted({});
    setMissing([]);
    setCurrentField(null);
    setActiveOptions(null);
    setStage("AWAITING_UPLOAD");
    setError(null);
    await boot();
  }

  /* -------- Schema-driven helpers -------- */
  const fieldMeta = useMemo(() => {
    if (!schema) return {};
    const map = {};
    for (const f of schema.primary_fields || []) map[f.field] = f;
    for (const f of schema.followup_fields || []) map[f.field] = f;
    return map;
  }, [schema]);

  const primaryFields = useMemo(
    () => (schema?.primary_fields || []).map((f) => f.field),
    [schema],
  );

  function optionsFor(field) {
    const meta = fieldMeta[field];
    return meta?.options?.length ? meta.options : null;
  }

  /* -------- Apply backend response -------- */
  function applyResponse(data) {
    if (!data) return;
    if (data.bot_message) {
      setMessages((prev) => [
        ...prev,
        { type: "ai", content: data.bot_message, timestamp: nowTime() },
      ]);
    }
    if (data.extracted_data) setExtracted(data.extracted_data);
    if (data.missing_fields) setMissing(data.missing_fields);
    if (data.stage) setStage(data.stage);

    const field =
      data.current_field ??
      (data.missing_fields?.length ? data.missing_fields[0] : null);
    setCurrentField(field);
    setActiveOptions(field ? optionsFor(field) : null);
  }

  /* -------- Upload -------- */
  async function handleUpload(file) {
    if (!file || !sessionId) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      alert("Only PDF files are accepted.");
      return;
    }
    setMessages((prev) => [
      ...prev,
      {
        type: "user",
        content: `📎 Uploaded: ${file.name}`,
        timestamp: nowTime(),
      },
    ]);
    setIsUploading(true);
    setError(null);
    try {
      const data = await uploadDocument(sessionId, file);
      applyResponse(data);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        {
          type: "ai",
          content: `⚠️ Upload failed: ${e?.response?.data?.detail || e.message}`,
          timestamp: nowTime(),
        },
      ]);
    } finally {
      setIsUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  /* -------- Manual start -------- */
  async function handleManual() {
    if (!sessionId) return;
    setMessages((prev) => [
      ...prev,
      {
        type: "user",
        content: "✍️ I'll type my details",
        timestamp: nowTime(),
      },
    ]);
    setIsLoading(true);
    try {
      const data = await startManual(sessionId);
      applyResponse(data);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        {
          type: "ai",
          content: `⚠️ ${e?.response?.data?.detail || e.message}`,
          timestamp: nowTime(),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  }

  /* -------- Send text -------- */
  async function handleSend(textOverride) {
    const text = (textOverride ?? inputMessage).trim();
    if (!text || !sessionId) return;

    setMessages((prev) => [
      ...prev,
      { type: "user", content: text, timestamp: nowTime() },
    ]);
    setInputMessage("");
    setActiveOptions(null);
    setIsLoading(true);
    setError(null);
    inputRef.current?.focus();
    try {
      const data = await sendMessage(sessionId, text);
      applyResponse(data);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        {
          type: "ai",
          content: `⚠️ ${e?.response?.data?.detail || e.message}`,
          timestamp: nowTime(),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  }

  function handleMultiSubmit(selections) {
    if (selections === "skip") return handleSend("skip");
    const parts = Object.entries(selections).map(([k, v]) =>
      v ? `${k}: ${v}` : k,
    );
    handleSend(parts.join(", ") || "skip");
  }

  function renderMarkdown(text = "") {
    return (
      String(text)
        // 1) Escape HTML first so nothing can inject markup
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        // 2) Bold: **text**
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        // 3) Italic: *text* (not preceded/followed by another *)
        .replace(/(^|[^*])\*([^*\n]+?)\*(?!\*)/g, "$1<em>$2</em>")
        // 4) Inline code: `code`
        .replace(
          /`([^`]+)`/g,
          '<code class="rounded bg-slate-100 px-1 py-0.5 text-[0.85em]">$1</code>',
        )
        // 5) Auto-link URLs
        .replace(
          /(https?:\/\/[^\s<]+)/g,
          '<a href="$1" target="_blank" rel="noopener" class="underline text-teal-700">$1</a>',
        )
        // 6) Preserve line breaks
        .replace(/\n/g, "<br/>")
    );
  }

  /* -------- Download PDF -------- */
  async function handleDownload() {
    if (!sessionId) return;
    setIsGenerating(true);
    try {
      const blob = await downloadPDF(sessionId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${(extracted.full_name || "questionnaire").toString().replace(/\s+/g, "_")}_${sessionId}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setMessages((prev) => [
        ...prev,
        {
          type: "ai",
          content: "✅ PDF downloaded successfully.",
          timestamp: nowTime(),
        },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          type: "ai",
          content: "⚠️ PDF download failed.",
          timestamp: nowTime(),
        },
      ]);
    } finally {
      setIsGenerating(false);
    }
  }

  /* -------- Derived -------- */
  const filledCount = useMemo(
    () =>
      primaryFields.filter(
        (f) => extracted[f] != null && String(extracted[f]).trim() !== "",
      ).length,
    [primaryFields, extracted],
  );
  const totalCount = primaryFields.length;
  const allMet = totalCount > 0 && filledCount === totalCount;
  const progressPct =
    totalCount > 0 ? Math.round((filledCount / totalCount) * 100) : 0;

  const capturedList = primaryFields
    .filter((f) => extracted[f] != null && String(extracted[f]).trim() !== "")
    .map((f) => ({ field: f, meta: fieldMeta[f], value: extracted[f] }));

  const pendingList = primaryFields
    .filter((f) => extracted[f] == null || String(extracted[f]).trim() === "")
    .map((f) => ({ field: f, meta: fieldMeta[f] }));

  const showChooser = stage === "AWAITING_UPLOAD" && !isUploading;

  /* ================================================================
   *  RENDER
   * ============================================================== */
  if (error && !sessionId) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-slate-50 p-5 text-slate-900">
        <AlertCircle size={48} className="text-rose-500" />
        <h2 className="mt-5 text-lg font-semibold text-rose-500">
          Something went wrong
        </h2>
        <p className="mt-2 max-w-[500px] text-center text-sm text-slate-500">
          {error}
        </p>
        <button
          onClick={boot}
          className="mt-5 rounded-lg bg-teal-600 px-6 py-2.5 text-sm font-medium text-white transition hover:bg-teal-700"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!schema) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <div className="flex items-center gap-3 text-slate-500">
          <Loader2 className="animate-spin" size={20} />
          Loading schema…
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      {/* ============== HEADER ============== */}
      <header className="sticky top-0 z-30 w-full bg-[#0f766e] text-white shadow-md">
        <div className="mx-auto flex w-full max-w-[1400px] items-center justify-between px-6 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-white/15 backdrop-blur">
              <ShieldCheck size={22} />
            </div>
            <div className="leading-tight">
              <h1 className="text-lg font-bold tracking-tight">
                {schema.title}
              </h1>
              <p className="text-xs text-teal-100">{schema.subtitle}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowProfile((v) => !v)}
              className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition ${
                showProfile
                  ? "bg-white text-teal-700"
                  : "bg-white/10 text-white hover:bg-white/20"
              }`}
            >
              <User size={16} />
              <span>Profile</span>
            </button>
            <button
              onClick={handleReset}
              className="inline-flex items-center gap-2 rounded-lg bg-white/10 px-3 py-2 text-sm font-medium transition hover:bg-white/20"
            >
              <RefreshCw size={14} />
              <span>Reset Session</span>
            </button>
          </div>
        </div>
      </header>

      {/* ============== MAIN GRID ============== */}
      <main className="mx-auto grid w-full max-w-[1400px] grid-cols-1 gap-5 px-6 py-5 lg:grid-cols-[minmax(0,1fr)_440px]">
        {/* ---------------- LEFT: CHAT ---------------- */}
        <div className="flex h-[calc(100vh-120px)] min-w-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
            <div className="flex items-center gap-2">
              <MessageSquare size={18} className="text-teal-700" />
              <h2 className="text-sm font-semibold text-slate-800">
                Concierge Intake Assistant
              </h2>
            </div>
            {/* <span className="rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-600">
              KYC &amp; Medical Underwriting Mode
            </span> */}
          </div>

          {/* Messages */}
          <div className="scroll-thin flex-1 space-y-4 overflow-y-auto bg-slate-50/50 p-5">
            {messages.map((msg, i) => {
              const isUser = msg.type === "user";
              const isLast = i === messages.length - 1;
              return (
                <React.Fragment key={i}>
                  <div
                    className={`flex w-full ${isUser ? "justify-end" : "justify-start"}`}
                  >
                    <div
                      className={`flex max-w-[85%] items-start gap-3 ${isUser ? "flex-row-reverse" : ""}`}
                    >
                      {!isUser && (
                        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-teal-600 text-[10px] font-bold text-white">
                          AI
                        </div>
                      )}
                      <div className="min-w-0">
                        <div
                          className={`whitespace-pre-wrap rounded-2xl px-4 py-3 text-sm leading-6 shadow-sm ${
                            isUser
                              ? "rounded-tr-md bg-teal-600 text-white"
                              : "rounded-tl-md border border-slate-200 bg-white text-slate-800"
                          }`}
                          dangerouslySetInnerHTML={{
                            __html: renderMarkdown(msg.content),
                          }}
                        />
                        <div
                          className={`mt-1 px-1 text-[10px] text-slate-400 ${isUser ? "text-right" : ""}`}
                        >
                          {msg.timestamp}
                        </div>
                      </div>
                      {isUser && (
                        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-rose-500">
                          <User size={16} color="white" />
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Inline options from schema */}
                  {!isUser && isLast && activeOptions && !isLoading && (
                    <ChoiceRow
                      options={activeOptions}
                      onSelect={handleSend}
                      disabled={isLoading}
                    />
                  )}
                </React.Fragment>
              );
            })}

            {/* Chooser card */}
            {showChooser && (
              <div className="grid grid-cols-1 gap-3 pt-1 sm:grid-cols-2 animate-fade-in">
                <button
                  onClick={() => fileRef.current?.click()}
                  className="group flex items-center gap-3 rounded-xl border-2 border-dashed border-teal-200 bg-white p-4 text-left transition hover:border-teal-400 hover:bg-teal-50"
                >
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-teal-50 text-teal-700 transition group-hover:bg-teal-100">
                    <Upload size={18} />
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-slate-800">
                      Upload PDF
                    </div>
                    <div className="text-xs text-slate-500">
                      Auto-extract &amp; fill
                    </div>
                  </div>
                </button>

                <button
                  onClick={handleManual}
                  className="group flex items-center gap-3 rounded-xl border-2 border-dashed border-slate-200 bg-white p-4 text-left transition hover:border-teal-400 hover:bg-teal-50"
                >
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-100 text-slate-700 transition group-hover:bg-teal-100 group-hover:text-teal-700">
                    <PenLine size={18} />
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-slate-800">
                      Start manually
                    </div>
                    <div className="text-xs text-slate-500">
                      Type your details
                    </div>
                  </div>
                </button>
              </div>
            )}

            {/* Typing */}
            {(isLoading || isUploading) && (
              <div className="flex justify-start animate-fade-in">
                <div className="flex items-start gap-3">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-teal-600 text-[10px] font-bold text-white">
                    AI
                  </div>
                  <div className="flex gap-1 rounded-2xl rounded-tl-md bg-white px-4 py-3 shadow-sm">
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:0.15s]" />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:0.3s]" />
                  </div>
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>

          {/* Quick actions */}
          <div className="border-t border-slate-100 bg-slate-50 px-4 pt-3">
            <div className="flex flex-wrap gap-2 pb-3">
              <button
                onClick={() => fileRef.current?.click()}
                disabled={isUploading || !sessionId}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:border-teal-300 hover:bg-teal-50 disabled:opacity-50"
              >
                {isUploading ? (
                  <Loader2 size={14} className="animate-spin text-teal-700" />
                ) : (
                  <Upload size={14} className="text-teal-700" />
                )}
                Upload KYC (PAN/Aadhaar)
              </button>
              <button
                onClick={() => fileRef.current?.click()}
                disabled={isUploading || !sessionId}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:border-rose-300 hover:bg-rose-50 disabled:opacity-50"
              >
                <FileText size={14} className="text-rose-600" />
                Upload Old Policy
              </button>
              {/* <button
                disabled={!sessionId}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:border-teal-300 hover:bg-teal-50 disabled:opacity-50"
              >
                <Mic size={14} className="text-teal-700" />
                Voice Note
              </button> */}
              <input
                type="file"
                ref={fileRef}
                onChange={(e) => handleUpload(e.target.files?.[0])}
                accept=".pdf"
                style={{ display: "none" }}
              />
            </div>
          </div>

          {/* Composer */}
          <div className="border-t border-slate-100 bg-white p-4">
            <div className="flex items-end gap-2 rounded-xl border border-slate-200 bg-slate-50 p-1.5 focus-within:border-teal-400 focus-within:ring-2 focus-within:ring-teal-100">
              <button
                onClick={() => fileRef.current?.click()}
                disabled={!sessionId || isUploading}
                title="Attach PDF"
                className="mb-0.5 flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 transition hover:bg-white hover:text-teal-700 disabled:opacity-40"
              >
                <Paperclip size={17} />
              </button>
              <textarea
                value={inputMessage}
                ref={inputRef}
                onChange={(e) => setInputMessage(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                rows={1}
                placeholder={
                  !sessionId
                    ? "Connecting…"
                    : stage === "AWAITING_UPLOAD"
                      ? "Upload a PDF, or type your details to begin…"
                      : "Type your reply…"
                }
                disabled={!sessionId || isLoading || isUploading}
                className="max-h-32 min-h-10 flex-1 resize-none border-0 bg-transparent px-2 py-2 text-sm text-slate-700 outline-none placeholder:text-slate-400 disabled:opacity-60"
              />
              <button
                onClick={() => handleSend()}
                disabled={
                  !inputMessage.trim() || isLoading || isUploading || !sessionId
                }
                className="mb-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-teal-600 text-white transition hover:bg-teal-700 disabled:cursor-not-allowed disabled:bg-slate-300"
              >
                {isLoading ? (
                  <Loader2 size={17} className="animate-spin" />
                ) : (
                  <Send size={17} />
                )}
              </button>
            </div>
          </div>
        </div>

        {/* ---------------- RIGHT: SIDEBAR ---------------- */}
        <div className="scroll-thin flex h-[calc(100vh-120px)] min-w-0 flex-col gap-5 overflow-y-auto">
          {/* Readiness */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-start justify-between gap-3">
              <div className="flex items-center gap-2">
                <ShieldCheck size={18} className="text-teal-700" />
                <h2 className="text-sm font-bold tracking-wide text-slate-800">
                  UNDERWRITING SUBMISSION READINESS
                </h2>
              </div>
              <span
                className={`shrink-0 rounded-full px-3 py-1 text-xs font-semibold ${
                  allMet
                    ? "bg-emerald-100 text-emerald-800"
                    : "bg-amber-100 text-amber-800"
                }`}
              >
                {allMet ? "Complete" : `Incomplete (${progressPct}%)`}
              </span>
            </div>

            <div className="mb-5 h-2 w-full overflow-hidden rounded-full bg-slate-100">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  allMet ? "bg-emerald-500" : "bg-amber-500"
                }`}
                style={{ width: `${Math.max(progressPct, 3)}%` }}
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              {/* Captured */}
              <div className="rounded-lg border border-emerald-200 bg-emerald-50/50 p-3">
                <div className="mb-2 flex items-center gap-1.5">
                  <CheckCircle size={14} className="text-emerald-600" />
                  <h3 className="text-[11px] font-bold uppercase tracking-wide text-emerald-800">
                    Captured Underwriting Data
                  </h3>
                </div>
                {capturedList.length === 0 ? (
                  <p className="text-xs italic text-emerald-700/80">
                    Waiting for details…
                  </p>
                ) : (
                  <ul className="max-h-40 space-y-1.5 overflow-y-auto">
                    {capturedList.map(({ field, meta, value }) => (
                      <li
                        key={field}
                        className="text-xs leading-snug text-emerald-800"
                      >
                        <span className="font-medium">
                          {meta?.label || field}
                        </span>
                        <span className="block text-emerald-700/80">
                          {formatValue(value)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {/* Pending */}
              <div className="rounded-lg border border-rose-200 bg-rose-50/50 p-3">
                <div className="mb-2 flex items-center gap-1.5">
                  <AlertTriangle size={14} className="text-rose-600" />
                  <h3 className="text-[11px] font-bold uppercase tracking-wide text-rose-800">
                    Pending Requirements
                  </h3>
                </div>
                {pendingList.length === 0 ? (
                  <p className="text-xs italic text-emerald-700">
                    All requirements satisfied.
                  </p>
                ) : (
                  <ul className="max-h-40 space-y-1.5 overflow-y-auto">
                    {pendingList.map(({ field, meta }) => (
                      <li
                        key={field}
                        className="flex items-start gap-1.5 text-xs leading-snug text-rose-700"
                      >
                        <span className="mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-rose-500" />
                        <span>{meta?.label || field}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </div>

          {/* Extracted Profile */}
          {showProfile && (
            <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
              <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
                <div className="flex items-center gap-2">
                  <User size={16} className="text-teal-700" />
                  <h3 className="text-sm font-semibold text-slate-800">
                    Extracted Profile Data
                  </h3>
                </div>
                <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">
                  {filledCount}/{totalCount}
                </span>
              </div>
              <div className="scroll-thin max-h-[50vh] space-y-1 overflow-y-auto p-4">
                {Object.entries(extracted).length === 0 ? (
                  <p className="text-xs italic text-slate-400">
                    Nothing captured yet.
                  </p>
                ) : (
                  Object.entries(extracted).map(([field, value]) => (
                    <div
                      key={field}
                      className="flex items-start gap-2 rounded-lg px-2.5 py-2 text-sm text-slate-600"
                    >
                      <FieldIcon
                        name={fieldMeta[field]?.icon || "user"}
                        size={16}
                      />
                      <div className="flex-1">
                        <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                          {fieldMeta[field]?.label || field.replace(/_/g, " ")}
                        </div>
                        <div className="text-slate-700">
                          {formatValue(value)}
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {/* Insurance Passport — locked/unlocked */}
          {allMet ? (
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="mb-4 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <ShieldCheck size={18} className="text-teal-700" />
                  <h3 className="text-sm font-bold text-slate-800">
                    PERSONAL INSURANCE PASSPORT
                  </h3>
                </div>
                <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-800">
                  Unlocked
                </span>
              </div>

              <p className="mb-4 text-sm text-slate-500">
                Your underwriting record is verified. You can now download the
                proposal PDF.
              </p>

              <button
                onClick={handleDownload}
                disabled={isGenerating}
                className="inline-flex items-center gap-2 rounded-lg bg-teal-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-teal-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isGenerating ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <Download size={16} />
                )}
                <span>Download Proposal PDF</span>
              </button>
            </div>
          ) : (
            <div className="flex min-h-[280px] flex-1 flex-col items-center justify-center rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-xl bg-slate-100">
                <Lock size={26} className="text-slate-400" />
              </div>
              <h3 className="text-base font-semibold text-slate-700">
                Personal Insurance Passport is locked.
              </h3>
              <p className="mt-2 max-w-[320px] text-sm leading-6 text-slate-500">
                Answer the remaining {pendingList.length} question
                {pendingList.length === 1 ? "" : "s"} in the chat to unlock the
                download.
              </p>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
