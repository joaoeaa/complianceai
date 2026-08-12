import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import {
  Shield, Upload, FileText, AlertTriangle, CheckCircle, XCircle,
  Clock, TrendingUp, Settings, BarChart3, ChevronRight, Search,
  Filter, Download, Eye, Trash2, Plus, X, ArrowLeft, Loader2,
  FileUp, Lock, Zap, ChevronDown, LogOut, User, Bell, Menu,
  Edit3, ToggleLeft, ToggleRight, Info, ArrowUpRight, Home,
  Mail, KeyRound, Calendar, SlidersHorizontal, ChevronUp, RefreshCw,
  BookOpen, Scale, Hash, ExternalLink, Users, UserPlus, Building, Crown,
  ThumbsUp, ThumbsDown, Star, MessageSquare, Send, Check,
  Briefcase, Archive, History, ShieldCheck
} from "lucide-react";
import LandingPage from "./LandingPage";

// ── API Configuration ──
// Em produção, defina VITE_API_URL (ex.: https://api.seudominio.com)
const API_ORIGIN = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const API_BASE = `${API_ORIGIN}/api/v1`;

class ApiClient {
  constructor() {
    // Restore tokens from localStorage if available
    this.accessToken = localStorage.getItem("access_token") || null;
    this.refreshToken = localStorage.getItem("refresh_token") || null;
    this.onUnauthorized = null;
  }

  setTokens(access, refresh) {
    this.accessToken = access;
    this.refreshToken = refresh;
    if (access) localStorage.setItem("access_token", access);
    else localStorage.removeItem("access_token");
    if (refresh) localStorage.setItem("refresh_token", refresh);
    else localStorage.removeItem("refresh_token");
  }

  clearTokens() {
    this.accessToken = null;
    this.refreshToken = null;
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
  }

  async request(path, options = {}) {
    const url = `${API_BASE}${path}`;
    const headers = { ...options.headers };

    if (this.accessToken && !options.skipAuth) {
      headers["Authorization"] = `Bearer ${this.accessToken}`;
    }

    if (!(options.body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
    }

    try {
      const res = await fetch(url, { ...options, headers });

      if (res.status === 401 && this.refreshToken && !options._isRetry) {
        const refreshed = await this.tryRefresh();
        if (refreshed) {
          return this.request(path, { ...options, _isRetry: true });
        }
        this.onUnauthorized?.();
        throw new Error("Sessão expirada");
      }

      if (res.status === 204) return null;

      const data = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error(data?.detail || `Erro ${res.status}`);
      }
      return data;
    } catch (err) {
      if (err.message === "Failed to fetch") {
        throw new Error(`Servidor indisponível. Verifique se o backend está acessível em ${API_ORIGIN}`);
      }
      throw err;
    }
  }

  async tryRefresh() {
    try {
      const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: this.refreshToken }),
      });
      if (res.ok) {
        const data = await res.json();
        this.setTokens(data.access_token, data.refresh_token);
        return true;
      }
    } catch {}
    return false;
  }

  // Auth
  async login(email, password) {
    const data = await this.request("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
      skipAuth: true,
    });
    this.setTokens(data.access_token, data.refresh_token);
    return data;
  }

  async getMe() {
    return this.request("/auth/me");
  }

  // Documents
  async uploadDocument(file, clientId = null) {
    const form = new FormData();
    form.append("file", file);
    if (this.scopeOrgId) form.append("organization_id", this.scopeOrgId);
    if (clientId) form.append("client_id", clientId);
    return this.request("/documents/upload", { method: "POST", body: form });
  }

  // Clientes do escritório
  async listClients() {
    const qs = this.scopeOrgId ? `?organization_id=${this.scopeOrgId}` : "";
    return this.request(`/clients${qs}`);
  }

  async createClient(data) {
    const body = this.scopeOrgId ? { ...data, organization_id: this.scopeOrgId } : data;
    return this.request("/clients", { method: "POST", body: JSON.stringify(body) });
  }

  async updateClient(id, data) {
    return this.request(`/clients/${id}`, { method: "PATCH", body: JSON.stringify(data) });
  }

  async deleteClient(id) {
    return this.request(`/clients/${id}`, { method: "DELETE" });
  }

  async listAssignees(clientId) {
    return this.request(`/clients/${clientId}/assignees`);
  }

  async assignUser(clientId, email) {
    return this.request(`/clients/${clientId}/assignees`, {
      method: "POST", body: JSON.stringify({ email }),
    });
  }

  async unassignUser(clientId, userId) {
    return this.request(`/clients/${clientId}/assignees/${userId}`, { method: "DELETE" });
  }

  async listExpired() {
    const qs = this.scopeOrgId ? `?organization_id=${this.scopeOrgId}` : "";
    return this.request(`/clients/retencao/vencidos${qs}`);
  }

  async purgeDocuments(documentIds) {
    const qs = this.scopeOrgId ? `?organization_id=${this.scopeOrgId}` : "";
    return this.request(`/clients/retencao/expurgar${qs}`, {
      method: "POST", body: JSON.stringify({ document_ids: documentIds }),
    });
  }

  async listAccessLogs(clientId = null) {
    const p = new URLSearchParams();
    if (this.scopeOrgId) p.set("organization_id", this.scopeOrgId);
    if (clientId) p.set("client_id", clientId);
    const qs = p.toString();
    return this.request(`/clients/auditoria/acessos${qs ? `?${qs}` : ""}`);
  }

  async listDocuments(params = {}) {
    const qs = new URLSearchParams();
    if (params.status) qs.set("status", params.status);
    if (params.search) qs.set("search", params.search);
    if (params.offset != null) qs.set("offset", params.offset);
    if (params.limit) qs.set("limit", params.limit);
    if (params.clientId) qs.set("client_id", params.clientId);
    if (this.scopeOrgId) qs.set("organization_id", this.scopeOrgId);
    const q = qs.toString();
    return this.request(`/documents${q ? `?${q}` : ""}`);
  }

  async getDocument(id) {
    return this.request(`/documents/${id}`);
  }

  async getReport(id) {
    return this.request(`/documents/${id}/report`);
  }

  async getAnalysisStatus(docId, taskId) {
    const qs = taskId ? `?task_id=${taskId}` : "";
    return this.request(`/documents/${docId}/status${qs}`);
  }

  async deleteDocument(id) {
    return this.request(`/documents/${id}`, { method: "DELETE" });
  }
  async setAlertResolution(docId, alertIndex, resolution, comment) {
    return this.request(`/documents/${docId}/alerts/${alertIndex}`, {
      method: "PATCH",
      body: JSON.stringify({ resolution, comment }),
    });
  }

  async downloadOriginal(docId) {
    return this._downloadFile(`${API_BASE}/documents/${docId}/download`, "documento");
  }

  async downloadReportPdf(docId) {
    return this._downloadFile(`${API_BASE}/documents/${docId}/report/pdf`, "relatorio.pdf");
  }

  // Download autenticado: o navegador nao envia o token num link comum, entao o
  // arquivo vem por fetch e e entregue como blob.
  async _downloadFile(url, fallbackName) {
    const headers = {};
    if (this.accessToken) {
      headers["Authorization"] = `Bearer ${this.accessToken}`;
    }

    let res = await fetch(url, { headers });

    if (res.status === 401 && this.refreshToken) {
      const refreshed = await this.tryRefresh();
      if (refreshed) {
        headers["Authorization"] = `Bearer ${this.accessToken}`;
        res = await fetch(url, { headers });
      } else {
        this.onUnauthorized?.();
        throw new Error("Sessão expirada");
      }
    }

    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail || `Erro ${res.status}`);
    }

    const disposition = res.headers.get("Content-Disposition");
    let filename = fallbackName;
    if (disposition) {
      const match = disposition.match(/filename="?([^";\n]+)"?/);
      if (match) filename = match[1];
    }

    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(a.href);
  }
  // Rules
  // Escopo de trabalho ativo: null = pessoal, uuid = equipe. Vale para documentos,
  // dashboard e regras, para que todas as telas mostrem o mesmo recorte.
  get scopeOrgId() {
    return this._scopeOrgId ?? localStorage.getItem("scope_org_id") ?? null;
  }

  setScope(orgId) {
    this._scopeOrgId = orgId || null;
    if (orgId) localStorage.setItem("scope_org_id", orgId);
    else localStorage.removeItem("scope_org_id");
  }

  async listRules(activeOnly = false, organizationId = null) {
    const p = new URLSearchParams();
    if (activeOnly) p.set("active_only", "true");
    if (organizationId) p.set("organization_id", organizationId);
    const qs = p.toString();
    return this.request(`/rules${qs ? `?${qs}` : ""}`);
  }

  async createRule(data) {
    return this.request("/rules", { method: "POST", body: JSON.stringify(data) });
  }

  async updateRule(id, data) {
    return this.request(`/rules/${id}`, { method: "PATCH", body: JSON.stringify(data) });
  }

  async deleteRule(id) {
    return this.request(`/rules/${id}`, { method: "DELETE" });
  }

  async toggleCategory(category, isActive, organizationId = null) {
    const qs = organizationId ? `?organization_id=${organizationId}` : "";
    return this.request(`/rules/categoria/${encodeURIComponent(category)}${qs}`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: isActive }),
    });
  }

  async toggleRule(id, organizationId = null) {
    const qs = organizationId ? `?organization_id=${organizationId}` : "";
    return this.request(`/rules/${id}/toggle${qs}`, { method: "PATCH" });
  }

  // Dashboard
  async getDashboard() {
    const qs = this.scopeOrgId ? `?organization_id=${this.scopeOrgId}` : "";
    return this.request(`/dashboard${qs}`);
  }

  // Legislation
  async listLegislation(category = null) {
    const qs = category ? `?category=${encodeURIComponent(category)}` : "";
    return this.request(`/legislation${qs}`);
  }

  async getLegislation(id) {
    return this.request(`/legislation/${id}`);
  }

  async searchLegislation(query, topK = 8, category = null) {
    return this.request("/legislation/search", {
      method: "POST",
      body: JSON.stringify({ query, top_k: topK, ...(category ? { category } : {}) }),
    });
  }

  // Auth — Register
  async register(email, password, fullName) {
    return this.request("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, full_name: fullName }),
      skipAuth: true,
    });
  }

  // Organizations
  async listOrganizations() {
    return this.request("/organizations");
  }
  async getOrganization(id) {
    return this.request(`/organizations/${id}`);
  }
  async createOrganization(data) {
    return this.request("/organizations", { method: "POST", body: JSON.stringify(data) });
  }
  async updateOrganization(id, data) {
    return this.request(`/organizations/${id}`, { method: "PATCH", body: JSON.stringify(data) });
  }
  async deleteOrganization(id) {
    return this.request(`/organizations/${id}`, { method: "DELETE" });
  }
  async addOrgMember(orgId, email, role = "member") {
    return this.request(`/organizations/${orgId}/members`, {
      method: "POST", body: JSON.stringify({ email, role }),
    });
  }
  async updateOrgMemberRole(orgId, userId, role) {
    return this.request(`/organizations/${orgId}/members/${userId}`, {
      method: "PATCH", body: JSON.stringify({ role }),
    });
  }
  async removeOrgMember(orgId, userId) {
    return this.request(`/organizations/${orgId}/members/${userId}`, { method: "DELETE" });
  }

  // Feedback (learning loop)
  async submitFeedbackBatch(data) {
    return this.request("/dashboard/feedback/batch", {
      method: "POST", body: JSON.stringify(data),
    });
  }
  async getAlertFeedback(analysisId) {
    return this.request(`/dashboard/feedback/alerts/${analysisId}`);
  }
  async getAnalysisFeedback(analysisId) {
    return this.request(`/dashboard/feedback/${analysisId}`);
  }
}

const api = new ApiClient();

// ── Utilities ──
const formatFileSize = (bytes) => {
  if (!bytes) return "0 B";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1048576).toFixed(1) + " MB";
};
const formatDate = (dateStr) => {
  if (!dateStr) return "—";
  return new Date(dateStr).toLocaleDateString("pt-BR", {
    day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit"
  });
};
const getRiskColor = (score) => score <= 30 ? "#10b981" : score <= 60 ? "#f59e0b" : "#ef4444";
const getRiskLabel = (score) => score <= 30 ? "Baixo" : score <= 60 ? "Moderado" : "Alto";
const getSeverityStyle = (sev) =>
  sev === "high" ? { bg: "#fef2f2", color: "#dc2626", border: "#fecaca", label: "Alta" }
  : sev === "medium" ? { bg: "#fffbeb", color: "#d97706", border: "#fde68a", label: "Média" }
  : { bg: "#f0fdf4", color: "#16a34a", border: "#bbf7d0", label: "Baixa" };
const getStatusStyle = (status) => ({
  analyzed: { bg: "#f0fdf4", color: "#16a34a", label: "Analisado" },
  processing: { bg: "#eff6ff", color: "#2563eb", label: "Processando" },
  error: { bg: "#fef2f2", color: "#dc2626", label: "Erro" },
  uploaded: { bg: "#fefce8", color: "#ca8a04", label: "Enviado" }
}[status] || { bg: "#f9fafb", color: "#6b7280", label: status || "—" });

const F = "'DM Sans', sans-serif";

// ── Shared Components ──
const Modal = ({ open, onClose, title, children, width = 480 }) => {
  if (!open) return null;
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", backdropFilter: "blur(4px)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, padding: 20 }}>
      <div onClick={e => e.stopPropagation()} style={{ background: "white", borderRadius: 20, width: "100%", maxWidth: width, maxHeight: "90vh", overflow: "auto", animation: "fadeSlideUp 0.25s ease" }}>
        {title && <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "18px 22px", borderBottom: "1px solid #f1f5f9" }}><h3 style={{ fontSize: 16, fontWeight: 700, color: "#0f172a", margin: 0, fontFamily: F }}>{title}</h3><button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", padding: 4 }}><X size={18} color="#94a3b8" /></button></div>}
        <div style={{ padding: "18px 22px" }}>{children}</div>
      </div>
    </div>
  );
};

const Toast = ({ message, type = "success", onClose }) => {
  useEffect(() => { const t = setTimeout(onClose, 3200); return () => clearTimeout(t); }, [onClose]);
  const c = { success: { bg: "#f0fdf4", border: "#bbf7d0", color: "#16a34a" }, error: { bg: "#fef2f2", border: "#fecaca", color: "#dc2626" }, info: { bg: "#eff6ff", border: "#bfdbfe", color: "#2563eb" } }[type] || { bg: "#eff6ff", border: "#bfdbfe", color: "#2563eb" };
  return (
    <div style={{ position: "fixed", bottom: 24, right: 24, background: c.bg, border: `1px solid ${c.border}`, borderRadius: 12, padding: "12px 18px", display: "flex", alignItems: "center", gap: 8, zIndex: 2000, animation: "fadeSlideUp 0.3s ease", boxShadow: "0 8px 30px rgba(0,0,0,0.1)", maxWidth: 380 }}>
      {type === "success" ? <CheckCircle size={16} color={c.color} /> : type === "error" ? <XCircle size={16} color={c.color} /> : <Info size={16} color={c.color} />}
      <span style={{ fontSize: 13, fontWeight: 600, color: c.color, fontFamily: F }}>{message}</span>
      <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", marginLeft: 4, padding: 2, flexShrink: 0 }}><X size={14} color={c.color} /></button>
    </div>
  );
};

const RiskGauge = ({ score, size = 140 }) => {
  const r = (size - 20) / 2, circ = Math.PI * r, prog = (score / 100) * circ, col = getRiskColor(score);
  return (
    <div style={{ position: "relative", width: size, height: size / 1.6, overflow: "hidden" }}>
      <svg width={size} height={size} style={{ position: "absolute", top: 0, left: 0 }}>
        <path d={`M 10 ${size/1.6} A ${r} ${r} 0 0 1 ${size-10} ${size/1.6}`} fill="none" stroke="#e5e7eb" strokeWidth="10" strokeLinecap="round" />
        <path d={`M 10 ${size/1.6} A ${r} ${r} 0 0 1 ${size-10} ${size/1.6}`} fill="none" stroke={col} strokeWidth="10" strokeLinecap="round" strokeDasharray={`${prog} ${circ}`} style={{ transition: "stroke-dasharray 1.2s cubic-bezier(0.4,0,0.2,1)" }} />
      </svg>
      <div style={{ position: "absolute", bottom: 0, left: "50%", transform: "translateX(-50%)", textAlign: "center" }}>
        <div style={{ fontSize: size * 0.28, fontWeight: 800, color: col, fontFamily: F, lineHeight: 1 }}>{score}</div>
        <div style={{ fontSize: 11, color: "#6b7280", fontWeight: 600, letterSpacing: "0.05em", textTransform: "uppercase", marginTop: 2 }}>{getRiskLabel(score)}</div>
      </div>
    </div>
  );
};

// ── Login / Register Page ──
const LoginPage = ({ onLogin, initialMode = "login", onVoltar }) => {
  const [mode, setMode] = useState(initialMode); // "login" | "register"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const switchMode = (m) => { setMode(m); setError(""); setSuccess(""); setEmail(""); setPassword(""); };

  const handleLogin = async () => {
    setError("");
    if (!email || !password) { setError("Preencha todos os campos."); return; }
    setLoading(true);
    try {
      await api.login(email, password);
      const user = await api.getMe();
      onLogin(user);
    } catch (err) {
      setError(err.message || "Erro ao fazer login");
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async () => {
    setError(""); setSuccess("");
    if (!email || !password || !fullName) { setError("Preencha todos os campos obrigatórios."); return; }
    if (password.length < 6) { setError("A senha deve ter pelo menos 6 caracteres."); return; }
    if (password !== confirmPassword) { setError("As senhas não coincidem."); return; }
    setLoading(true);
    try {
      await api.register(email, password, fullName);
      setSuccess("Conta criada com sucesso! Faça login para continuar.");
      setTimeout(() => { switchMode("login"); setEmail(email); setPassword(""); }, 1500);
    } catch (err) {
      setError(err.message || "Erro ao criar conta");
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = mode === "login" ? handleLogin : handleRegister;
  const isLogin = mode === "login";

  return (
    <div style={{ minHeight: "100vh", display: "flex", fontFamily: F, flexWrap: "wrap" }}>
      <div style={{ flex: 1, minWidth: 320, display: "flex", flexDirection: "column", justifyContent: "center", padding: "48px clamp(24px,6vw,80px)", position: "relative", overflow: "hidden", background: "#0c0f1a" }}>
        <div style={{ position: "absolute", top: -100, left: -100, width: 500, height: 500, borderRadius: "50%", background: "radial-gradient(circle, rgba(99,102,241,0.15), transparent 70%)" }} />
        <div style={{ position: "absolute", bottom: -150, right: -80, width: 600, height: 600, borderRadius: "50%", background: "radial-gradient(circle, rgba(139,92,246,0.1), transparent 70%)" }} />
        <div style={{ position: "relative", zIndex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 44 }}>
            <div style={{ width: 44, height: 44, borderRadius: 12, background: "linear-gradient(135deg, #6366f1, #8b5cf6)", display: "flex", alignItems: "center", justifyContent: "center" }}><Shield size={24} color="white" /></div>
            <div><div style={{ color: "white", fontWeight: 800, fontSize: 20, letterSpacing: "-0.02em" }}>ComplianceAI</div><div style={{ color: "rgba(255,255,255,0.35)", fontSize: 11, fontWeight: 500 }}>Auditoria Inteligente</div></div>
          </div>
          <h1 style={{ color: "white", fontSize: "clamp(26px,4vw,40px)", fontWeight: 800, lineHeight: 1.15, letterSpacing: "-0.03em", maxWidth: 480, margin: "0 0 16px" }}>Análise de contratos com IA em minutos, não horas.</h1>
          <p style={{ color: "rgba(255,255,255,0.45)", fontSize: 15, lineHeight: 1.7, maxWidth: 440 }}>Identifique riscos, verifique conformidade e gere relatórios automaticamente.</p>
          <div style={{ display: "flex", gap: 28, marginTop: 40, flexWrap: "wrap" }}>
            {[{ val: "< 2min", lbl: "por análise" }, { val: "99%", lbl: "uptime" }, { val: "AES-256", lbl: "criptografia" }].map((s, i) => (
              <div key={i}><div style={{ color: "#818cf8", fontSize: 20, fontWeight: 800 }}>{s.val}</div><div style={{ color: "rgba(255,255,255,0.3)", fontSize: 11, marginTop: 2 }}>{s.lbl}</div></div>
            ))}
          </div>
        </div>
      </div>
      <div style={{ width: "clamp(340px,40vw,480px)", display: "flex", flexDirection: "column", justifyContent: "center", padding: "48px clamp(24px,4vw,56px)", background: "white" }}>
        {onVoltar && (
          <button onClick={onVoltar} style={{ display: "flex", alignItems: "center", gap: 5, background: "none", border: "none", cursor: "pointer", color: "#64748b", fontSize: 12.5, fontWeight: 600, fontFamily: F, padding: 0, marginBottom: 18 }}>
            <ArrowLeft size={14} /> Voltar
          </button>
        )}
        <h2 style={{ fontSize: 22, fontWeight: 800, color: "#0f172a", letterSpacing: "-0.03em", margin: "0 0 4px" }}>{isLogin ? "Bem-vindo de volta" : "Criar nova conta"}</h2>
        <p style={{ color: "#64748b", fontSize: 13, margin: "0 0 28px" }}>{isLogin ? "Faça login para acessar a plataforma" : "Preencha os dados para se registrar"}</p>
        {error && <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 10, padding: "10px 14px", marginBottom: 16, fontSize: 13, color: "#dc2626", fontWeight: 500, display: "flex", alignItems: "center", gap: 8 }}><AlertTriangle size={15} />{error}</div>}
        {success && <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 10, padding: "10px 14px", marginBottom: 16, fontSize: 13, color: "#16a34a", fontWeight: 500, display: "flex", alignItems: "center", gap: 8 }}><CheckCircle size={15} />{success}</div>}
        {!isLogin && (<>
          <label style={{ fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 5, display: "block" }}>Nome completo *</label>
          <div style={{ position: "relative", marginBottom: 16 }}><User size={16} color="#94a3b8" style={{ position: "absolute", left: 12, top: 12 }} /><input value={fullName} onChange={e => setFullName(e.target.value)} placeholder="Seu nome" style={{ width: "100%", padding: "11px 14px 11px 38px", borderRadius: 10, border: "1px solid #d1d5db", fontSize: 13, fontFamily: F, outline: "none", boxSizing: "border-box" }} /></div>
        </>)}
        <label style={{ fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 5, display: "block" }}>Email {!isLogin && "*"}</label>
        <div style={{ position: "relative", marginBottom: 16 }}><Mail size={16} color="#94a3b8" style={{ position: "absolute", left: 12, top: 12 }} /><input value={email} onChange={e => setEmail(e.target.value)} onKeyDown={e => e.key === "Enter" && isLogin && handleSubmit()} placeholder="seu@email.com" style={{ width: "100%", padding: "11px 14px 11px 38px", borderRadius: 10, border: "1px solid #d1d5db", fontSize: 13, fontFamily: F, outline: "none", boxSizing: "border-box" }} /></div>
        <label style={{ fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 5, display: "block" }}>Senha {!isLogin && "* (min. 6 caracteres)"}</label>
        <div style={{ position: "relative", marginBottom: isLogin ? 24 : 16 }}><KeyRound size={16} color="#94a3b8" style={{ position: "absolute", left: 12, top: 12 }} /><input value={password} onChange={e => setPassword(e.target.value)} onKeyDown={e => e.key === "Enter" && handleSubmit()} type="password" placeholder={isLogin ? "" : "Mínimo 6 caracteres"} style={{ width: "100%", padding: "11px 14px 11px 38px", borderRadius: 10, border: "1px solid #d1d5db", fontSize: 13, fontFamily: F, outline: "none", boxSizing: "border-box" }} /></div>
        {!isLogin && (<>
          <label style={{ fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 5, display: "block" }}>Confirmar senha *</label>
          <div style={{ position: "relative", marginBottom: 24 }}><KeyRound size={16} color="#94a3b8" style={{ position: "absolute", left: 12, top: 12 }} /><input value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} onKeyDown={e => e.key === "Enter" && handleSubmit()} type="password" placeholder="Repita a senha" style={{ width: "100%", padding: "11px 14px 11px 38px", borderRadius: 10, border: "1px solid #d1d5db", fontSize: 13, fontFamily: F, outline: "none", boxSizing: "border-box" }} /></div>
        </>)}
        <button onClick={handleSubmit} disabled={loading} style={{ width: "100%", padding: "13px", borderRadius: 12, border: "none", cursor: loading ? "wait" : "pointer", background: "linear-gradient(135deg, #6366f1, #8b5cf6)", color: "white", fontSize: 14, fontWeight: 700, fontFamily: F, display: "flex", alignItems: "center", justifyContent: "center", gap: 8, opacity: loading ? 0.7 : 1 }}>
          {loading && <Loader2 size={18} style={{ animation: "spin 1s linear infinite" }} />}{loading ? (isLogin ? "Entrando..." : "Criando conta...") : (isLogin ? "Entrar" : "Criar conta")}
        </button>
        <div style={{ textAlign: "center", marginTop: 18 }}>
          <span style={{ fontSize: 13, color: "#64748b" }}>{isLogin ? "Não tem conta?" : "Já tem conta?"} </span>
          <button onClick={() => switchMode(isLogin ? "register" : "login")} style={{ background: "none", border: "none", color: "#6366f1", fontWeight: 700, fontSize: 13, cursor: "pointer", fontFamily: F, textDecoration: "underline" }}>{isLogin ? "Criar conta" : "Fazer login"}</button>
        </div>
      </div>
    </div>
  );
};

// ── Sidebar ──
const Sidebar = ({ currentPage, onNavigate, collapsed, onToggle, user, onLogout, isMobile, mobileOpen, onMobileClose }) => {
  const navItems = [{ id: "dashboard", icon: Home, label: "Dashboard" }, { id: "upload", icon: Upload, label: "Nova Análise" }, { id: "history", icon: Clock, label: "Histórico" }, { id: "legislation", icon: BookOpen, label: "Base Legal" }, { id: "rules", icon: Settings, label: "Regras" }, { id: "clients", icon: Briefcase, label: "Clientes" }, { id: "team", icon: Users, label: "Equipe" }];
  const w = collapsed && !isMobile ? 72 : 260;
  const show = isMobile || !collapsed;
  const handleNav = (id) => { onNavigate(id); if (isMobile) onMobileClose(); };
  return (
    <>
      {isMobile && mobileOpen && <div onClick={onMobileClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 199 }} />}
      <div style={{ width: isMobile ? 270 : w, minHeight: "100vh", background: "#0c0f1a", display: "flex", flexDirection: "column", position: "fixed", left: 0, top: 0, zIndex: 200, overflow: "hidden", ...(isMobile ? { transform: mobileOpen ? "translateX(0)" : "translateX(-100%)", transition: "transform 0.3s ease" } : { transition: "width 0.3s ease" }) }}>
        <div style={{ padding: show ? "22px 22px" : "22px 16px", display: "flex", alignItems: "center", gap: 10, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
          <div style={{ width: 34, height: 34, borderRadius: 9, background: "linear-gradient(135deg, #6366f1, #8b5cf6)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}><Shield size={18} color="white" /></div>
          {show && <div><div style={{ color: "white", fontWeight: 700, fontSize: 15, fontFamily: F }}>ComplianceAI</div><div style={{ color: "rgba(255,255,255,0.35)", fontSize: 10 }}>Auditoria Inteligente</div></div>}
        </div>
        <nav style={{ flex: 1, padding: "14px 10px", display: "flex", flexDirection: "column", gap: 3 }}>
          {navItems.map(item => { const a = currentPage === item.id; return (
            <button key={item.id} onClick={() => handleNav(item.id)} style={{ display: "flex", alignItems: "center", gap: 10, padding: show ? "11px 14px" : "11px", borderRadius: 9, border: "none", cursor: "pointer", justifyContent: show ? "flex-start" : "center", background: a ? "rgba(99,102,241,0.15)" : "transparent", transition: "all 0.2s" }}
              onMouseEnter={e => { if (!a) e.currentTarget.style.background = "rgba(255,255,255,0.05)"; }} onMouseLeave={e => { if (!a) e.currentTarget.style.background = a ? "rgba(99,102,241,0.15)" : "transparent"; }}>
              <item.icon size={18} color={a ? "#818cf8" : "rgba(255,255,255,0.4)"} />{show && <span style={{ color: a ? "#c7d2fe" : "rgba(255,255,255,0.5)", fontSize: 13, fontWeight: a ? 600 : 500, fontFamily: F }}>{item.label}</span>}
            </button>
          ); })}
        </nav>
        <div style={{ padding: "10px", borderTop: "1px solid rgba(255,255,255,0.06)" }}>
          {show && user && <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", marginBottom: 6 }}><div style={{ width: 28, height: 28, borderRadius: 7, background: "linear-gradient(135deg, #6366f1, #8b5cf6)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}><User size={13} color="white" /></div><div style={{ minWidth: 0 }}><div style={{ color: "rgba(255,255,255,0.7)", fontSize: 12, fontWeight: 600 }}>{user.full_name}</div><div style={{ color: "rgba(255,255,255,0.25)", fontSize: 10, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{user.email}</div></div></div>}
          <button onClick={onLogout} style={{ display: "flex", alignItems: "center", gap: 10, padding: show ? "9px 14px" : "9px", borderRadius: 9, border: "none", cursor: "pointer", background: "transparent", justifyContent: show ? "flex-start" : "center", width: "100%" }} onMouseEnter={e => e.currentTarget.style.background = "rgba(239,68,68,0.1)"} onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
            <LogOut size={16} color="rgba(255,255,255,0.3)" />{show && <span style={{ color: "rgba(255,255,255,0.3)", fontSize: 12, fontFamily: F }}>Sair</span>}
          </button>
          {!isMobile && <button onClick={onToggle} style={{ display: "flex", alignItems: "center", gap: 10, padding: show ? "9px 14px" : "9px", borderRadius: 9, border: "none", cursor: "pointer", background: "transparent", justifyContent: show ? "flex-start" : "center", width: "100%", marginTop: 3 }}><Menu size={16} color="rgba(255,255,255,0.3)" />{show && <span style={{ color: "rgba(255,255,255,0.3)", fontSize: 12, fontFamily: F }}>Recolher</span>}</button>}
        </div>
      </div>
    </>
  );
};

// ── SVG Chart Components ──
const DonutChart = ({ high = 0, medium = 0, low = 0, size = 180 }) => {
  const total = high + medium + low;
  if (total === 0) return (
    <div style={{ width: size, height: size, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={size/2} cy={size/2} r={size/2 - 20} fill="none" stroke="#e5e7eb" strokeWidth="22" />
        <text x={size/2} y={size/2} textAnchor="middle" dominantBaseline="middle" fill="#94a3b8" fontSize="13" fontFamily="'DM Sans', sans-serif">Sem dados</text>
      </svg>
    </div>
  );

  const cx = size / 2, cy = size / 2, r = size / 2 - 20;
  const circumference = 2 * Math.PI * r;
  const segments = [
    { value: high, color: "#ef4444", label: "Alto" },
    { value: medium, color: "#f59e0b", label: "Médio" },
    { value: low, color: "#10b981", label: "Baixo" },
  ].filter(s => s.value > 0);

  let offset = 0;
  const paths = segments.map(seg => {
    const pct = seg.value / total;
    const dash = pct * circumference;
    const gap = circumference - dash;
    const rotation = (offset / total) * 360 - 90;
    offset += seg.value;
    return { ...seg, dash, gap, rotation };
  });

  return (
    <div style={{ position: "relative", width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {paths.map((p, i) => (
          <circle key={i} cx={cx} cy={cy} r={r} fill="none" stroke={p.color} strokeWidth="22" strokeDasharray={`${p.dash} ${p.gap}`} strokeLinecap="butt" transform={`rotate(${p.rotation} ${cx} ${cy})`} style={{ transition: "stroke-dasharray 0.8s ease" }} />
        ))}
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <div style={{ fontSize: 28, fontWeight: 800, color: "#0f172a", fontFamily: F, lineHeight: 1 }}>{total}</div>
        <div style={{ fontSize: 10, color: "#94a3b8", fontWeight: 600, marginTop: 2, textTransform: "uppercase", letterSpacing: "0.05em" }}>análises</div>
      </div>
    </div>
  );
};

const TrendLineChart = ({ data = [], width = 500, height = 200 }) => {
  if (data.length === 0) return (
    <div style={{ width: "100%", height, display: "flex", alignItems: "center", justifyContent: "center", color: "#94a3b8", fontSize: 13 }}>Sem dados de tendência</div>
  );

  const pad = { top: 20, right: 20, bottom: 35, left: 40 };
  const cw = width - pad.left - pad.right;
  const ch = height - pad.top - pad.bottom;
  const scores = data.map(d => d.avg_risk_score || 0);
  const maxScore = Math.max(100, ...scores);
  const minScore = 0;

  const points = data.map((d, i) => ({
    x: pad.left + (data.length === 1 ? cw / 2 : (i / (data.length - 1)) * cw),
    y: pad.top + ch - ((d.avg_risk_score - minScore) / (maxScore - minScore)) * ch,
    score: d.avg_risk_score,
    count: d.document_count,
    period: d.period,
  }));

  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
  const areaPath = `${linePath} L ${points[points.length-1].x} ${pad.top + ch} L ${points[0].x} ${pad.top + ch} Z`;
  const gridLines = [0, 25, 50, 75, 100].map(v => pad.top + ch - (v / maxScore) * ch);
  const fmtMonth = (p) => { const parts = (p || "").split("-"); return parts.length === 2 ? `${parts[1]}/${parts[0].slice(2)}` : p; };

  return (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet">
      {gridLines.map((y, i) => (
        <g key={i}>
          <line x1={pad.left} y1={y} x2={width - pad.right} y2={y} stroke="#f1f5f9" strokeWidth="1" />
          <text x={pad.left - 6} y={y + 4} textAnchor="end" fill="#94a3b8" fontSize="10" fontFamily="'DM Sans', sans-serif">{[0,25,50,75,100][i]}</text>
        </g>
      ))}
      <defs>
        <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#6366f1" stopOpacity="0.2" />
          <stop offset="100%" stopColor="#6366f1" stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill="url(#areaGrad)" />
      <path d={linePath} fill="none" stroke="#6366f1" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      {points.map((p, i) => (
        <g key={i}>
          <circle cx={p.x} cy={p.y} r="4" fill="white" stroke="#6366f1" strokeWidth="2" />
          <text x={p.x} y={p.y - 10} textAnchor="middle" fill="#6366f1" fontSize="10" fontWeight="700" fontFamily="'DM Sans', sans-serif">{p.score}</text>
          <text x={p.x} y={height - 8} textAnchor="middle" fill="#94a3b8" fontSize="9" fontFamily="'DM Sans', sans-serif">{fmtMonth(p.period)}</text>
        </g>
      ))}
    </svg>
  );
};

const AlertsBarChart = ({ data = [], maxBars = 6, height = 200 }) => {
  const items = data.slice(0, maxBars);
  if (items.length === 0) return (
    <div style={{ height, display: "flex", alignItems: "center", justifyContent: "center", color: "#94a3b8", fontSize: 13 }}>Nenhum alerta registrado</div>
  );

  const maxCount = Math.max(...items.map(d => d.count), 1);
  const barH = Math.min(28, (height - 10) / items.length - 6);
  const sevColor = (w) => w >= 2.5 ? "#ef4444" : w >= 1.5 ? "#f59e0b" : "#10b981";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {items.map((item, i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, animation: `fadeSlideUp 0.4s ease ${i * 0.06}s both` }}>
          <div style={{ width: 140, fontSize: 11, color: "#374151", fontWeight: 500, fontFamily: F, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flexShrink: 0 }} title={item.rule_name}>{item.rule_name}</div>
          <div style={{ flex: 1, height: barH, background: "#f1f5f9", borderRadius: 6, overflow: "hidden", position: "relative" }}>
            <div style={{ height: "100%", width: `${(item.count / maxCount) * 100}%`, background: `linear-gradient(90deg, ${sevColor(item.avg_severity_weight)}cc, ${sevColor(item.avg_severity_weight)})`, borderRadius: 6, transition: "width 0.8s ease", minWidth: 20 }} />
          </div>
          <div style={{ fontSize: 12, fontWeight: 700, color: "#0f172a", fontFamily: F, width: 28, textAlign: "right", flexShrink: 0 }}>{item.count}</div>
        </div>
      ))}
    </div>
  );
};

// ── Dashboard ──
const DashboardPage = ({ onNavigate, onViewReport }) => {
  const [dashboard, setDashboard] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([
      api.getDashboard().catch(() => null),
      api.listDocuments({ limit: 5 }).catch(() => ({ documents: [] })),
    ]).then(([dash, docs]) => {
      setDashboard(dash);
      setDocuments(docs?.documents || []);
    }).catch(() => setError("Erro ao carregar dashboard"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ display: "flex", justifyContent: "center", padding: 60 }}><Loader2 size={28} color="#6366f1" style={{ animation: "spin 1s linear infinite" }} /></div>;

  const ov = dashboard?.overview || {};
  const stats = [
    { label: "Total de Docs", value: ov.total_documents || 0, icon: FileText, color: "#6366f1", bg: "#eef2ff" },
    { label: "Analisados", value: ov.total_analyzed || 0, icon: CheckCircle, color: "#10b981", bg: "#f0fdf4" },
    { label: "Score Médio", value: ov.avg_risk_score != null ? ov.avg_risk_score : "—", icon: BarChart3, color: ov.avg_risk_score > 60 ? "#ef4444" : ov.avg_risk_score > 30 ? "#f59e0b" : "#10b981", bg: ov.avg_risk_score > 60 ? "#fef2f2" : ov.avg_risk_score > 30 ? "#fffbeb" : "#f0fdf4" },
    { label: "Alto Risco", value: ov.high_risk_count || 0, icon: AlertTriangle, color: "#ef4444", bg: "#fef2f2" },
    { label: "Risco Médio", value: ov.medium_risk_count || 0, icon: TrendingUp, color: "#f59e0b", bg: "#fffbeb" },
    { label: "Processando", value: ov.total_pending || 0, icon: Loader2, color: "#2563eb", bg: "#eff6ff" },
  ];

  return (
    <div>
      <div style={{ marginBottom: 28, display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: 10 }}>
        <div><h1 style={{ fontSize: 24, fontWeight: 800, color: "#0f172a", fontFamily: F, letterSpacing: "-0.03em", margin: 0 }}>Dashboard</h1><p style={{ color: "#64748b", fontSize: 13, marginTop: 3, fontFamily: F }}>Visão geral das análises de compliance</p></div>
        <button onClick={() => { setLoading(true); Promise.all([api.getDashboard().catch(() => null), api.listDocuments({ limit: 5 }).catch(() => ({ documents: [] }))]).then(([d, docs]) => { setDashboard(d); setDocuments(docs?.documents || []); }).finally(() => setLoading(false)); }} style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 14px", borderRadius: 9, border: "1px solid #e2e8f0", background: "white", cursor: "pointer", fontSize: 12, fontWeight: 600, color: "#64748b", fontFamily: F }}><RefreshCw size={14} />Atualizar</button>
      </div>

      {/* Stat Cards */}
      <div className="stats-grid" style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 12, marginBottom: 24 }}>
        {stats.map((s, i) => (
          <div key={i} style={{ background: "white", borderRadius: 13, padding: "16px", border: "1px solid #e2e8f0", animation: `fadeSlideUp 0.5s ease ${i*0.07}s both` }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
              <div style={{ width: 34, height: 34, borderRadius: 9, background: s.bg, display: "flex", alignItems: "center", justifyContent: "center" }}><s.icon size={16} color={s.color} /></div>
            </div>
            <div style={{ fontSize: 22, fontWeight: 800, color: "#0f172a", fontFamily: F, lineHeight: 1 }}>{s.value}</div>
            <div style={{ fontSize: 10, color: "#64748b", fontWeight: 500, marginTop: 4, fontFamily: F }}>{s.label}</div>
          </div>
        ))}
      </div>

      {/* Charts Row */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 20 }} className="dashboard-grid">
        {/* Risk Distribution Donut */}
        <div style={{ background: "white", borderRadius: 14, border: "1px solid #e2e8f0", padding: "20px", animation: "fadeSlideUp 0.5s ease 0.3s both" }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: "0 0 6px", fontFamily: F }}>Distribuição de Risco</h3>
          <p style={{ fontSize: 11, color: "#94a3b8", margin: "0 0 16px", fontFamily: F }}>Classificação dos documentos analisados</p>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 30, flexWrap: "wrap" }}>
            <DonutChart high={ov.high_risk_count || 0} medium={ov.medium_risk_count || 0} low={ov.low_risk_count || 0} size={170} />
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {[{ label: "Alto Risco", value: ov.high_risk_count || 0, color: "#ef4444" }, { label: "Risco Médio", value: ov.medium_risk_count || 0, color: "#f59e0b" }, { label: "Baixo Risco", value: ov.low_risk_count || 0, color: "#10b981" }].map((item, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <div style={{ width: 10, height: 10, borderRadius: 3, background: item.color, flexShrink: 0 }} />
                  <span style={{ fontSize: 12, color: "#374151", fontFamily: F, fontWeight: 500 }}>{item.label}</span>
                  <span style={{ fontSize: 13, fontWeight: 700, color: "#0f172a", fontFamily: F, marginLeft: 4 }}>{item.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Trend Line Chart */}
        <div style={{ background: "white", borderRadius: 14, border: "1px solid #e2e8f0", padding: "20px", animation: "fadeSlideUp 0.5s ease 0.4s both" }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: "0 0 6px", fontFamily: F }}>Tendência de Risco</h3>
          <p style={{ fontSize: 11, color: "#94a3b8", margin: "0 0 12px", fontFamily: F }}>Score médio de risco por mês</p>
          <TrendLineChart data={dashboard?.risk_trend || []} width={460} height={190} />
        </div>
      </div>

      {/* Bottom Row: Top Alerts + Recent Docs + Quick Actions */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }} className="dashboard-grid">
        {/* Top Alerts */}
        <div style={{ background: "white", borderRadius: 14, border: "1px solid #e2e8f0", padding: "20px", animation: "fadeSlideUp 0.5s ease 0.5s both" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
            <div><h3 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: 0, fontFamily: F }}>Alertas Mais Frequentes</h3><p style={{ fontSize: 11, color: "#94a3b8", margin: "3px 0 0", fontFamily: F }}>Top regras violadas nas análises</p></div>
            <button onClick={() => onNavigate("rules")} style={{ fontSize: 11, color: "#6366f1", fontWeight: 600, background: "none", border: "none", cursor: "pointer", display: "flex", alignItems: "center", gap: 3, fontFamily: F }}>Regras <ChevronRight size={12} /></button>
          </div>
          <AlertsBarChart data={dashboard?.top_alerts || []} maxBars={5} height={170} />
        </div>

        {/* Recent Documents + Quick Actions */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={{ background: "white", borderRadius: 14, border: "1px solid #e2e8f0", overflow: "hidden", flex: 1, animation: "fadeSlideUp 0.5s ease 0.6s both" }}>
            <div style={{ padding: "14px 18px", borderBottom: "1px solid #f1f5f9", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h3 style={{ fontSize: 13, fontWeight: 700, color: "#0f172a", margin: 0, fontFamily: F }}>Análises Recentes</h3>
              <button onClick={() => onNavigate("history")} style={{ fontSize: 11, color: "#6366f1", fontWeight: 600, background: "none", border: "none", cursor: "pointer", display: "flex", alignItems: "center", gap: 3, fontFamily: F }}>Ver todas <ChevronRight size={12} /></button>
            </div>
            {documents.length === 0 ? <div style={{ padding: 28, textAlign: "center", color: "#94a3b8", fontSize: 12 }}>Nenhum documento ainda</div> : documents.slice(0, 4).map((doc, i) => { const st = getStatusStyle(doc.status); return (
              <div key={doc.id} onClick={() => doc.status === "analyzed" && onViewReport(doc.id)} style={{ padding: "10px 18px", borderBottom: i < 3 ? "1px solid #f8fafc" : "none", display: "flex", alignItems: "center", justifyContent: "space-between", cursor: doc.status === "analyzed" ? "pointer" : "default", transition: "background 0.15s" }} onMouseEnter={e => e.currentTarget.style.background = "#f8fafc"} onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}><FileText size={14} color="#94a3b8" style={{ flexShrink: 0 }} /><div style={{ minWidth: 0 }}><div style={{ fontSize: 11, fontWeight: 600, color: "#1e293b", fontFamily: F, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{doc.filename}</div></div></div>
                <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>{doc.risk_score != null && <div style={{ fontSize: 11, fontWeight: 700, color: getRiskColor(doc.risk_score), fontFamily: F }}>{doc.risk_score}</div>}<span style={{ fontSize: 9, fontWeight: 600, color: st.color, background: st.bg, padding: "2px 7px", borderRadius: 20, fontFamily: F }}>{st.label}</span></div>
              </div>
            ); })}
          </div>
          <div style={{ display: "flex", gap: 12 }}>
            <div onClick={() => onNavigate("upload")} style={{ flex: 1, background: "linear-gradient(135deg, #6366f1, #8b5cf6)", borderRadius: 13, padding: "18px", cursor: "pointer", transition: "transform 0.2s", position: "relative", overflow: "hidden", animation: "fadeSlideUp 0.5s ease 0.7s both" }} onMouseEnter={e => e.currentTarget.style.transform = "translateY(-2px)"} onMouseLeave={e => e.currentTarget.style.transform = ""}>
              <Upload size={20} color="rgba(255,255,255,0.9)" /><h3 style={{ color: "white", fontSize: 14, fontWeight: 700, marginTop: 8, marginBottom: 2, fontFamily: F }}>Nova Análise</h3><p style={{ color: "rgba(255,255,255,0.7)", fontSize: 11, margin: 0, fontFamily: F }}>Upload PDF ou DOCX</p>
            </div>
            <div onClick={() => onNavigate("rules")} style={{ flex: 1, background: "white", borderRadius: 13, padding: "18px", border: "1px solid #e2e8f0", cursor: "pointer", transition: "all 0.2s", animation: "fadeSlideUp 0.5s ease 0.75s both" }} onMouseEnter={e => e.currentTarget.style.borderColor = "#c7d2fe"} onMouseLeave={e => e.currentTarget.style.borderColor = "#e2e8f0"}>
              <Settings size={20} color="#d97706" /><h3 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", marginTop: 8, marginBottom: 2, fontFamily: F }}>Regras</h3><p style={{ color: "#64748b", fontSize: 11, margin: 0, fontFamily: F }}>Configurar compliance</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// ── Upload ──
const UploadPage = ({ onAnalyzeComplete, showToast }) => {
  const [dragOver, setDragOver] = useState(false);
  const [file, setFile] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState("");
  const fileInputRef = useRef(null);
  const pollRef = useRef(null);
  const [clients, setClients] = useState([]);
  const [clientId, setClientId] = useState("");

  // Amarrar o contrato ao cliente na entrada é o que define quem poderá lê-lo
  // depois. Escolher aqui evita ter que reclassificar o acervo mais tarde.
  useEffect(() => {
    api.listClients().then(setClients).catch(() => setClients([]));
  }, []);

  const handleFile = (f) => {
    if (f && (f.type === "application/pdf" || f.name.endsWith('.pdf') || f.name.endsWith('.docx'))) setFile(f);
    else if (f) showToast("Formato não suportado. Use PDF ou DOCX.", "error");
  };

  const stageLabels = {
    uploaded: "Enviando documento...",
    extracting: "Extraindo texto...",
    loading_rules: "Carregando regras...",
    analyzing: "Analisando com IA...",
    saving: "Salvando resultado...",
  };

  const startAnalysis = async () => {
    setAnalyzing(true);
    setProgress(10);
    setStage("Enviando documento...");
    try {
      const result = await api.uploadDocument(file, clientId || null);
      const docId = result.document_id;
      const taskId = result.task_id;
      setProgress(20);
      setStage("Processando...");

      // Poll for status
      pollRef.current = setInterval(async () => {
        try {
          const status = await api.getAnalysisStatus(docId, taskId);
          if (status.status === "analyzed") {
            clearInterval(pollRef.current);
            setProgress(100);
            setStage("Concluído!");
            setTimeout(() => onAnalyzeComplete(docId), 600);
          } else if (status.status === "error") {
            clearInterval(pollRef.current);
            setAnalyzing(false);
            showToast(status.message || "Erro na análise", "error");
          } else {
            // Parse progress from message
            const msg = status.message || "";
            const stageMatch = msg.match(/Etapa: (\w+) \((\d+)%\)/);
            if (stageMatch) {
              setStage(stageLabels[stageMatch[1]] || stageMatch[1]);
              setProgress(parseInt(stageMatch[2]));
            }
          }
        } catch (e) {
          // Silently continue polling
        }
      }, 2000);
    } catch (err) {
      setAnalyzing(false);
      showToast(err.message || "Erro no upload", "error");
    }
  };

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  return (
    <div>
      <div style={{ marginBottom: 28 }}><h1 style={{ fontSize: 24, fontWeight: 800, color: "#0f172a", fontFamily: F, letterSpacing: "-0.03em", margin: 0 }}>Nova Análise</h1><p style={{ color: "#64748b", fontSize: 13, marginTop: 3, fontFamily: F }}>Upload de contrato para análise automática com IA real (Claude)</p></div>
      {!analyzing ? (
        <div style={{ maxWidth: 600, margin: "0 auto" }}>
          <div onDragOver={e => { e.preventDefault(); setDragOver(true); }} onDragLeave={() => setDragOver(false)} onDrop={e => { e.preventDefault(); setDragOver(false); handleFile(e.dataTransfer.files[0]); }} onClick={() => fileInputRef.current?.click()} style={{ border: `2px dashed ${dragOver ? "#6366f1" : file ? "#10b981" : "#cbd5e1"}`, borderRadius: 18, padding: "48px 28px", textAlign: "center", cursor: "pointer", background: dragOver ? "#eef2ff" : file ? "#f0fdf4" : "#fafbfc", transition: "all 0.3s" }}>
            <input ref={fileInputRef} type="file" accept=".pdf,.docx" style={{ display: "none" }} onChange={e => handleFile(e.target.files[0])} />
            {file ? (<><div style={{ width: 52, height: 52, borderRadius: 13, background: "#dcfce7", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 14px" }}><CheckCircle size={26} color="#16a34a" /></div><div style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", fontFamily: F }}>{file.name}</div><div style={{ color: "#64748b", fontSize: 12, marginTop: 3 }}>{formatFileSize(file.size)}</div><button onClick={e => { e.stopPropagation(); setFile(null); }} style={{ marginTop: 8, background: "none", border: "none", color: "#6366f1", fontSize: 12, fontWeight: 600, cursor: "pointer" }}>Trocar arquivo</button></>) : (<><div style={{ width: 56, height: 56, borderRadius: 16, background: dragOver ? "#c7d2fe" : "#e2e8f0", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 14px", transition: "all 0.3s" }}><FileUp size={26} color={dragOver ? "#6366f1" : "#94a3b8"} /></div><div style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", fontFamily: F }}>Arraste e solte seu documento</div><div style={{ color: "#94a3b8", fontSize: 12, marginTop: 4 }}>ou clique para selecionar • PDF ou DOCX • até 10MB</div></>)}
          </div>
          {file && clients.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: "#374151", marginBottom: 5, fontFamily: F }}>Cliente</label>
              <select value={clientId} onChange={e => setClientId(e.target.value)} style={{ width: "100%", padding: "11px 12px", borderRadius: 11, border: "1px solid #d1d5db", fontSize: 13, fontFamily: F, outline: "none", background: "white", boxSizing: "border-box" }}>
                <option value="">Sem cliente</option>
                {clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <div style={{ fontSize: 10.5, color: "#94a3b8", marginTop: 5, fontFamily: F, lineHeight: 1.5 }}>
                {clientId
                  ? "Só quem estiver designado a este cliente poderá abrir o documento."
                  : "Sem cliente, o documento fica visível a toda a equipe."}
              </div>
            </div>
          )}
          {file && <button onClick={startAnalysis} style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, width: "100%", marginTop: 18, padding: "13px", borderRadius: 11, border: "none", cursor: "pointer", background: "linear-gradient(135deg, #6366f1, #8b5cf6)", color: "white", fontSize: 14, fontWeight: 700, fontFamily: F, boxShadow: "0 4px 20px rgba(99,102,241,0.3)" }}><Zap size={17} /> Iniciar Análise com IA</button>}
          <div className="upload-features" style={{ display: "grid", gap: 10, marginTop: 32 }}>
            {[{ icon: Lock, title: "Criptografia AES-256", desc: "Documentos protegidos" }, { icon: Zap, title: "Análise com Claude AI", desc: "Resultado em minutos" }, { icon: Shield, title: "Multi-legislação", desc: "LGPD, CDC, CC, CLT e mais" }].map((item, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "12px", borderRadius: 9, background: "#f8fafc" }}><item.icon size={15} color="#6366f1" /><div><div style={{ fontSize: 11, fontWeight: 700, color: "#1e293b", fontFamily: F }}>{item.title}</div><div style={{ fontSize: 10, color: "#94a3b8" }}>{item.desc}</div></div></div>
            ))}
          </div>
        </div>
      ) : (
        <div style={{ maxWidth: 440, margin: "48px auto", textAlign: "center" }}>
          <div style={{ width: 64, height: 64, borderRadius: 16, margin: "0 auto 20px", background: "linear-gradient(135deg, #eef2ff, #e0e7ff)", display: "flex", alignItems: "center", justifyContent: "center" }}><Loader2 size={28} color="#6366f1" style={{ animation: "spin 1s linear infinite" }} /></div>
          <div style={{ fontSize: 18, fontWeight: 700, color: "#0f172a", fontFamily: F, marginBottom: 5 }}>Analisando documento</div>
          <div style={{ fontSize: 13, color: "#6366f1", fontWeight: 600, marginBottom: 24, fontFamily: F }}>{stage}</div>
          <div style={{ width: "100%", height: 7, background: "#e2e8f0", borderRadius: 4, overflow: "hidden" }}><div style={{ height: "100%", background: "linear-gradient(90deg, #6366f1, #8b5cf6)", borderRadius: 4, width: `${progress}%`, transition: "width 0.8s cubic-bezier(0.4,0,0.2,1)" }} /></div>
          <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 8 }}>{progress}% concluído</div>
          <div style={{ fontSize: 10, color: "#cbd5e1", marginTop: 16 }}>A análise real com IA pode levar de 30s a 2min</div>
        </div>
      )}
    </div>
  );
};

// ── Severity Distribution Mini-Chart (horizontal stacked bar) ──
const SeverityBar = ({ high, medium, low }) => {
  const total = high + medium + low || 1;
  const hp = (high / total) * 100, mp = (medium / total) * 100, lp = (low / total) * 100;
  return (
    <div style={{ width: "100%" }}>
      <div style={{ display: "flex", height: 10, borderRadius: 5, overflow: "hidden", background: "#f1f5f9" }}>
        {high > 0 && <div style={{ width: `${hp}%`, background: "#ef4444", transition: "width 0.8s ease" }} />}
        {medium > 0 && <div style={{ width: `${mp}%`, background: "#f59e0b", transition: "width 0.8s ease" }} />}
        {low > 0 && <div style={{ width: `${lp}%`, background: "#10b981", transition: "width 0.8s ease" }} />}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8 }}>
        {[{ v: high, c: "#ef4444", l: "Alta" }, { v: medium, c: "#f59e0b", l: "Média" }, { v: low, c: "#10b981", l: "Baixa" }].map((x, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <div style={{ width: 8, height: 8, borderRadius: 2, background: x.c }} />
            <span style={{ fontSize: 11, color: "#64748b", fontFamily: F }}>{x.l}: <strong style={{ color: "#0f172a" }}>{x.v}</strong></span>
          </div>
        ))}
      </div>
    </div>
  );
};

// ── Report ──
const ReportPage = ({ docId, onBack, showToast }) => {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [expandedAlert, setExpandedAlert] = useState(null);

  // Feedback state
  const [alertVotes, setAlertVotes] = useState({});   // { index: true/false }
  const [alertComments, setAlertComments] = useState({}); // { index: "comment" }
  const [overallRating, setOverallRating] = useState(0); // 1-5
  const [overallComment, setOverallComment] = useState("");
  const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);
  const [submittingFeedback, setSubmittingFeedback] = useState(false);
  const [downloadingOriginal, setDownloadingOriginal] = useState(false);
  const [resolutions, setResolutions] = useState({});
  const [savingResolution, setSavingResolution] = useState(null);
  const [existingFeedback, setExistingFeedback] = useState(false);

  const changeResolution = async (index, resolution) => {
    const anterior = resolutions[index] ?? null;
    setResolutions(r => ({ ...r, [index]: resolution }));  // otimista
    setSavingResolution(index);
    try {
      await api.setAlertResolution(docId, index, resolution);
    } catch (err) {
      setResolutions(r => ({ ...r, [index]: anterior }));  // desfaz
      showToast(err.message || "Não foi possível salvar a marcação", "error");
    } finally {
      setSavingResolution(null);
    }
  };

  const downloadOriginal = async () => {
    setDownloadingOriginal(true);
    try {
      await api.downloadOriginal(docId);
    } catch (err) {
      // 410: o arquivo se perdeu antes do volume persistente. A mensagem do
      // backend ja explica isso, entao basta repassar.
      showToast(err.message || "Não foi possível baixar o arquivo", "error");
    } finally {
      setDownloadingOriginal(false);
    }
  };

  const downloadPDF = async () => {
    setDownloadingPdf(true);
    try {
      await api.downloadReportPdf(docId);
      showToast("PDF baixado com sucesso!", "success");
    } catch (err) {
      console.error("Erro ao baixar PDF:", err);
      showToast(err.message || "Erro ao gerar PDF", "error");
    } finally {
      setDownloadingPdf(false);
    }
  };

  useEffect(() => {
    if (!docId) return;
    setLoading(true);
    api.getReport(docId).then(data => {
      setReport(data);
      // O relatorio ja traz a marcacao deste revisor em cada alerta.
      const marcadas = {};
      (data?.analysis?.alerts || []).forEach((a, i) => {
        if (a.resolution) marcadas[i] = a.resolution;
      });
      setResolutions(marcadas);
      // Load existing feedback if any
      if (data?.analysis?.id) {
        api.getAlertFeedback(data.analysis.id).then(fbs => {
          if (fbs && fbs.length > 0) {
            const votes = {}, comments = {};
            fbs.forEach(fb => { votes[fb.alert_index] = fb.is_correct; if (fb.comment) comments[fb.alert_index] = fb.comment; });
            setAlertVotes(votes);
            setAlertComments(comments);
            setExistingFeedback(true);
          }
        }).catch(() => {});
        api.getAnalysisFeedback(data.analysis.id).then(fbs => {
          if (fbs && fbs.length > 0) {
            setOverallRating(fbs[0].rating || 0);
            setOverallComment(fbs[0].comment || "");
            setFeedbackSubmitted(true);
          }
        }).catch(() => {});
      }
    }).catch(err => {
      setError(err.message);
    }).finally(() => setLoading(false));
  }, [docId]);

  const submitFeedback = async () => {
    if (overallRating === 0) { showToast("Selecione uma nota de 1 a 5", "error"); return; }
    setSubmittingFeedback(true);
    try {
      const alertsPayload = Object.keys(alertVotes).map(idx => ({
        analysis_id: report.analysis.id,
        alert_index: parseInt(idx),
        rule_name: alerts[parseInt(idx)]?.rule_name || "Desconhecida",
        severity: alerts[parseInt(idx)]?.severity || null,
        is_correct: alertVotes[idx],
        comment: alertComments[idx] || null,
      }));
      await api.submitFeedbackBatch({
        analysis_id: report.analysis.id,
        rating: overallRating,
        comment: overallComment || null,
        adjusted_score: null,
        alerts: alertsPayload,
      });
      setFeedbackSubmitted(true);
      setExistingFeedback(true);
      showToast("Feedback enviado! A IA vai aprender com sua avaliação.", "success");
    } catch (err) {
      showToast(err.message || "Erro ao enviar feedback", "error");
    } finally {
      setSubmittingFeedback(false);
    }
  };

  if (loading) return <div style={{ display: "flex", justifyContent: "center", alignItems: "center", padding: 80, flexDirection: "column", gap: 12 }}><Loader2 size={32} color="#6366f1" style={{ animation: "spin 1s linear infinite" }} /><span style={{ fontSize: 13, color: "#64748b", fontFamily: F }}>Carregando relatório...</span></div>;
  if (error) return <div style={{ padding: 40, textAlign: "center" }}><button onClick={onBack} style={{ display: "flex", alignItems: "center", gap: 5, background: "none", border: "none", cursor: "pointer", color: "#6366f1", fontWeight: 600, fontSize: 12, marginBottom: 18, padding: 0, fontFamily: F }}><ArrowLeft size={15} /> Voltar</button><p style={{ color: "#ef4444" }}>{error}</p></div>;
  if (!report) return null;

  const { document: doc, analysis, rules_checked } = report;
  const alerts = (analysis.alerts || []).map(a => ({
    ...a,
    legal_basis: a.legal_basis || a.legal_base || a.base_legal || null
  }));
  const hc = alerts.filter(a => a.severity === "high").length;
  const mc = alerts.filter(a => a.severity === "medium").length;
  const lc2 = alerts.filter(a => a.severity === "low").length;
  const activeRules = (rules_checked || []).filter(r => r.is_active);
  const passedRules = activeRules.filter(r => !alerts.some(a => a.rule_name === r.name));
  const failedRules = activeRules.filter(r => alerts.some(a => a.rule_name === r.name));
  const complianceRate = activeRules.length > 0 ? Math.round((passedRules.length / activeRules.length) * 100) : 100;
  const riskCol = getRiskColor(analysis.risk_score);

  return (
    <div>
      {/* Header */}
      <button onClick={onBack} style={{ display: "flex", alignItems: "center", gap: 5, background: "none", border: "none", cursor: "pointer", color: "#6366f1", fontWeight: 600, fontSize: 12, marginBottom: 18, padding: 0, fontFamily: F }}><ArrowLeft size={15} /> Voltar aos documentos</button>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 28, flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, color: "#0f172a", fontFamily: F, letterSpacing: "-0.03em", margin: 0 }}>Relatório de Conformidade</h1>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6, flexWrap: "wrap" }}>
            <FileText size={14} color="#94a3b8" />
            <span style={{ color: "#475569", fontSize: 13, fontWeight: 500, fontFamily: F }}>{doc.filename}</span>
            <span style={{ color: "#d1d5db" }}>|</span>
            <Clock size={12} color="#94a3b8" />
            <span style={{ color: "#94a3b8", fontSize: 11, fontFamily: F }}>{formatDate(analysis.analyzed_at || doc.uploaded_at)}</span>
          </div>
        </div>
        <button
          onClick={downloadPDF}
          disabled={downloadingPdf}
          style={{ display: "inline-flex", alignItems: "center", gap: 8, background: downloadingPdf ? "#94a3b8" : "linear-gradient(135deg, #0f172a, #1e293b)", color: "white", padding: "10px 20px", borderRadius: 10, border: "none", cursor: downloadingPdf ? "not-allowed" : "pointer", fontSize: 13, fontWeight: 600, fontFamily: F, boxShadow: "0 2px 8px rgba(15,23,42,0.15)" }}
          onMouseOver={(e) => !downloadingPdf && (e.currentTarget.style.opacity = "0.9")}
          onMouseOut={(e) => (e.currentTarget.style.opacity = "1")}
        >
          {downloadingPdf ? <Loader2 size={15} style={{ animation: "spin 1s linear infinite" }} /> : <Download size={15} />}
          {downloadingPdf ? "Gerando..." : "Exportar PDF"}
        </button>
        <button
          onClick={downloadOriginal}
          disabled={downloadingOriginal}
          title="Baixar o arquivo exatamente como foi enviado"
          style={{ display: "inline-flex", alignItems: "center", gap: 7, background: "white", color: "#475569", padding: "10px 16px", borderRadius: 10, border: "1px solid #e2e8f0", cursor: downloadingOriginal ? "not-allowed" : "pointer", fontSize: 13, fontWeight: 600, fontFamily: F }}
        >
          {downloadingOriginal ? <Loader2 size={15} style={{ animation: "spin 1s linear infinite" }} /> : <FileText size={15} />}
          {downloadingOriginal ? "Baixando..." : "Original"}
        </button>
      </div>

      {/* Top Stats Row */}
      <div className="report-stats" style={{ display: "grid", gap: 14, marginBottom: 22 }}>
        {[
          { label: "Score de Risco", value: analysis.risk_score + "/100", icon: Shield, color: riskCol, bg: analysis.risk_score <= 30 ? "#f0fdf4" : analysis.risk_score <= 60 ? "#fffbeb" : "#fef2f2" },
          { label: "Total de Alertas", value: alerts.length, icon: AlertTriangle, color: "#f59e0b", bg: "#fffbeb" },
          { label: "Conformidade", value: complianceRate + "%", icon: CheckCircle, color: "#10b981", bg: "#f0fdf4" },
          { label: "Regras Analisadas", value: activeRules.length, icon: Scale, color: "#6366f1", bg: "#eef2ff" },
        ].map((stat, i) => (
          <div key={i} style={{ background: "white", borderRadius: 14, border: "1px solid #e2e8f0", padding: "16px 18px", display: "flex", alignItems: "center", gap: 14 }}>
            <div style={{ width: 42, height: 42, borderRadius: 11, background: stat.bg, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
              <stat.icon size={20} color={stat.color} />
            </div>
            <div>
              <div style={{ fontSize: 10, fontWeight: 600, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em", fontFamily: F }}>{stat.label}</div>
              <div style={{ fontSize: 20, fontWeight: 800, color: "#0f172a", fontFamily: F, letterSpacing: "-0.02em" }}>{stat.value}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Main Report Grid */}
      <div className="report-grid" style={{ display: "grid", gap: 18, marginBottom: 22 }}>
        {/* Left: Gauge + Severity Distribution */}
        <div style={{ background: "white", borderRadius: 14, border: "1px solid #e2e8f0", padding: "24px", display: "flex", flexDirection: "column", alignItems: "center" }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 16, fontFamily: F }}>Nível de Risco</div>
          <RiskGauge score={analysis.risk_score} size={170} />
          <div style={{ width: "100%", marginTop: 24, paddingTop: 20, borderTop: "1px solid #f1f5f9" }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 12, fontFamily: F }}>Distribuição de Severidade</div>
            <SeverityBar high={hc} medium={mc} low={lc2} />
          </div>
          {/* Compliance mini ring */}
          <div style={{ width: "100%", marginTop: 20, paddingTop: 20, borderTop: "1px solid #f1f5f9", display: "flex", alignItems: "center", gap: 14 }}>
            <div style={{ position: "relative", width: 52, height: 52, flexShrink: 0 }}>
              <svg width={52} height={52} style={{ transform: "rotate(-90deg)" }}>
                <circle cx={26} cy={26} r={22} fill="none" stroke="#e5e7eb" strokeWidth={5} />
                <circle cx={26} cy={26} r={22} fill="none" stroke="#10b981" strokeWidth={5} strokeDasharray={`${(complianceRate / 100) * 138.2} 138.2`} strokeLinecap="round" style={{ transition: "stroke-dasharray 1s ease" }} />
              </svg>
              <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 800, color: "#0f172a", fontFamily: F }}>{complianceRate}%</div>
            </div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: "#0f172a", fontFamily: F }}>Taxa de Conformidade</div>
              <div style={{ fontSize: 11, color: "#64748b", fontFamily: F }}>{passedRules.length} de {activeRules.length} regras aprovadas</div>
            </div>
          </div>
        </div>

        {/* Right: Executive Summary + Checklist */}
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          {/* Executive Summary Card */}
          <div style={{ background: "white", borderRadius: 14, border: "1px solid #e2e8f0", padding: "24px", flex: 1 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
              <div style={{ width: 28, height: 28, borderRadius: 7, background: "#eef2ff", display: "flex", alignItems: "center", justifyContent: "center" }}><FileText size={14} color="#6366f1" /></div>
              <div style={{ fontSize: 13, fontWeight: 700, color: "#0f172a", fontFamily: F }}>Resumo Executivo</div>
            </div>
            <p style={{ fontSize: 13, color: "#334155", lineHeight: 1.8, margin: 0, fontFamily: F }}>{analysis.summary}</p>
          </div>

          {/* Checklist Card */}
          <div style={{ background: "white", borderRadius: 14, border: "1px solid #e2e8f0", padding: "24px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
              <div style={{ width: 28, height: 28, borderRadius: 7, background: "#f0fdf4", display: "flex", alignItems: "center", justifyContent: "center" }}><CheckCircle size={14} color="#10b981" /></div>
              <div style={{ fontSize: 13, fontWeight: 700, color: "#0f172a", fontFamily: F }}>Checklist de Regras</div>
              <span style={{ fontSize: 11, color: "#94a3b8", fontFamily: F, marginLeft: "auto" }}>{passedRules.length}/{activeRules.length} aprovadas</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
              {failedRules.map(rule => (
                <div key={rule.id} style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 10px", borderRadius: 8, background: "#fef2f2", border: "1px solid #fecaca" }}>
                  <XCircle size={14} color="#ef4444" style={{ flexShrink: 0 }} />
                  <span style={{ fontSize: 11, color: "#991b1b", fontWeight: 600, fontFamily: F }}>{rule.name}</span>
                </div>
              ))}
              {passedRules.map(rule => (
                <div key={rule.id} style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 10px", borderRadius: 8, background: "#f0fdf4", border: "1px solid #bbf7d0" }}>
                  <CheckCircle size={14} color="#10b981" style={{ flexShrink: 0 }} />
                  <span style={{ fontSize: 11, color: "#166534", fontWeight: 500, fontFamily: F }}>{rule.name}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Alerts Section */}
      <div style={{ background: "white", borderRadius: 14, border: "1px solid #e2e8f0", overflow: "hidden" }}>
        <div style={{ padding: "18px 24px", borderBottom: "1px solid #f1f5f9", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 32, height: 32, borderRadius: 8, background: "#fffbeb", display: "flex", alignItems: "center", justifyContent: "center" }}><AlertTriangle size={16} color="#f59e0b" /></div>
            <div>
              <h3 style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", margin: 0, fontFamily: F }}>Alertas de Conformidade</h3>
              <span style={{ fontSize: 11, color: "#94a3b8", fontFamily: F }}>{alerts.length} {alerts.length === 1 ? "item encontrado" : "itens encontrados"}</span>
            </div>
          </div>
          {alerts.length > 0 && (
            <div style={{ display: "flex", gap: 6 }}>
              {hc > 0 && <span style={{ fontSize: 10, fontWeight: 700, color: "#dc2626", background: "#fef2f2", padding: "3px 10px", borderRadius: 20, border: "1px solid #fecaca", fontFamily: F }}>{hc} alta{hc > 1 ? "s" : ""}</span>}
              {mc > 0 && <span style={{ fontSize: 10, fontWeight: 700, color: "#d97706", background: "#fffbeb", padding: "3px 10px", borderRadius: 20, border: "1px solid #fde68a", fontFamily: F }}>{mc} média{mc > 1 ? "s" : ""}</span>}
              {lc2 > 0 && <span style={{ fontSize: 10, fontWeight: 700, color: "#16a34a", background: "#f0fdf4", padding: "3px 10px", borderRadius: 20, border: "1px solid #bbf7d0", fontFamily: F }}>{lc2} baixa{lc2 > 1 ? "s" : ""}</span>}
            </div>
          )}
        </div>

        {alerts.length === 0 ? (
          <div style={{ padding: 48, textAlign: "center" }}>
            <div style={{ width: 56, height: 56, borderRadius: 14, background: "#f0fdf4", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 14px" }}><CheckCircle size={28} color="#10b981" /></div>
            <div style={{ fontSize: 15, fontWeight: 700, color: "#10b981", fontFamily: F, marginBottom: 4 }}>Documento em Conformidade</div>
            <div style={{ fontSize: 12, color: "#64748b", fontFamily: F }}>Nenhum alerta foi identificado na análise.</div>
          </div>
        ) : alerts.map((alert, i) => {
          const sev = getSeverityStyle(alert.severity);
          const isExpanded = expandedAlert === i;
          return (
            <div key={i} style={{ borderBottom: i < alerts.length - 1 ? "1px solid #f1f5f9" : "none" }}>
              {/* Alert Header — clickable */}
              <div
                onClick={() => setExpandedAlert(isExpanded ? null : i)}
                style={{ padding: "16px 24px", cursor: "pointer", display: "flex", alignItems: "center", gap: 12, transition: "background 0.15s", background: isExpanded ? "#fafbfc" : "white" }}
                onMouseOver={(e) => { if (!isExpanded) e.currentTarget.style.background = "#fafbfc"; }}
                onMouseOut={(e) => { if (!isExpanded) e.currentTarget.style.background = "white"; }}
              >
                {/* Severity indicator */}
                <div style={{ width: 4, height: 36, borderRadius: 2, background: sev.color, flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 10, fontWeight: 700, color: sev.color, background: sev.bg, padding: "2px 10px", borderRadius: 20, border: `1px solid ${sev.border}`, fontFamily: F }}>{sev.label}</span>
                    <span style={{ fontSize: 13, fontWeight: 700, color: "#0f172a", fontFamily: F }}>{alert.rule_name}</span>
                  </div>
                  <div style={{ fontSize: 12, color: "#475569", fontFamily: F, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: isExpanded ? "normal" : "nowrap" }}>{alert.issue}</div>
                </div>
                <ChevronDown size={16} color="#94a3b8" style={{ transform: isExpanded ? "rotate(180deg)" : "none", transition: "transform 0.2s", flexShrink: 0 }} />
              </div>

              {/* Alert Details — expandable */}
              {isExpanded && (
                <div style={{ padding: "0 24px 20px 40px", animation: "fadeSlideUp 0.2s ease" }}>
                  {/* Issue detail */}
                  <div style={{ background: "#f8fafc", borderRadius: 10, padding: "14px 16px", marginBottom: 12, borderLeft: `4px solid ${sev.color}` }}>
                    <div style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 4, fontFamily: F }}>Problema Identificado</div>
                    <div style={{ fontSize: 13, color: "#1e293b", lineHeight: 1.6, fontFamily: F }}>{alert.issue}</div>
                  </div>

                  {/* Excerpt */}
                  {alert.excerpt && alert.excerpt !== "—" && (
                    <div style={{ background: "#fffbeb", borderRadius: 10, padding: "12px 16px", marginBottom: 12, border: "1px solid #fef3c7" }}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 4, flexWrap: "wrap" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                          <div style={{ fontSize: 10, fontWeight: 700, color: "#92400e", textTransform: "uppercase", letterSpacing: "0.05em", fontFamily: F }}>Trecho do Documento</div>
                          {alert.excerpt_page && (
                            <span style={{ fontSize: 10, fontWeight: 600, color: "#92400e", background: "rgba(255,255,255,0.7)", border: "1px solid #fde68a", padding: "1px 7px", borderRadius: 20, fontFamily: F }}>
                              Página {alert.excerpt_page}
                            </span>
                          )}
                        </div>
                        <CheckBadge meta={EXCERPT_CHECK[alert.excerpt_check]} />
                      </div>
                      <div style={{ fontSize: 12, color: "#78350f", fontStyle: "italic", lineHeight: 1.6, fontFamily: F }}>"{alert.excerpt}"</div>
                    </div>
                  )}

                  {/* Legal Basis — prominent card */}
                  {alert.legal_basis && (
                    <div style={{ background: "linear-gradient(135deg, #eef2ff, #e8e0ff)", borderRadius: 10, padding: "14px 16px", marginBottom: 12, border: "1px solid #c7d2fe" }}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 6, flexWrap: "wrap" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <Scale size={13} color="#6366f1" />
                          <span style={{ fontSize: 10, fontWeight: 700, color: "#4338ca", textTransform: "uppercase", letterSpacing: "0.05em", fontFamily: F }}>Fundamentação Legal</span>
                        </div>
                        <CheckBadge meta={LEGAL_CHECK[alert.legal_basis_check]} />
                      </div>
                      <div style={{ fontSize: 12, color: "#312e81", lineHeight: 1.6, fontWeight: 500, fontFamily: F }}>{alert.legal_basis}</div>
                      {alert.legal_source?.content && (
                        <details style={{ marginTop: 8 }}>
                          <summary style={{ fontSize: 11, color: "#4338ca", cursor: "pointer", fontWeight: 600, fontFamily: F }}>
                            Ler o dispositivo
                          </summary>
                          <div style={{ marginTop: 7, padding: "10px 12px", background: "rgba(255,255,255,0.75)", borderRadius: 8, border: "1px solid #c7d2fe" }}>
                            <div style={{ fontSize: 10, fontWeight: 700, color: "#4338ca", marginBottom: 4, fontFamily: F }}>
                              {alert.legal_source.source} {alert.legal_source.article_ref}
                            </div>
                            <div style={{ fontSize: 11.5, color: "#312e81", lineHeight: 1.65, fontFamily: F, whiteSpace: "pre-wrap" }}>
                              {alert.legal_source.content}
                            </div>
                          </div>
                        </details>
                      )}
                    </div>
                  )}

                  {/* Suggestion */}
                  <div style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "12px 16px", background: "#f0fdf4", borderRadius: 10, border: "1px solid #bbf7d0" }}>
                    <div style={{ width: 26, height: 26, borderRadius: 7, background: "#dcfce7", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: 1 }}><Zap size={13} color="#16a34a" /></div>
                    <div>
                      <div style={{ fontSize: 10, fontWeight: 700, color: "#166534", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 3, fontFamily: F }}>Recomendação</div>
                      <div style={{ fontSize: 12, color: "#15803d", lineHeight: 1.6, fontWeight: 500, fontFamily: F }}>{alert.suggestion}</div>
                    </div>
                  </div>

                  {/* Resolucao do revisor */}
                  <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid #f1f5f9", display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 11, color: "#94a3b8", fontWeight: 600, fontFamily: F }}>O que fazer com isto?</span>
                    {Object.entries(RESOLUTION_META).map(([key, m]) => {
                      const ativo = resolutions[i] === key;
                      return (
                        <button
                          key={key}
                          onClick={(e) => { e.stopPropagation(); changeResolution(i, ativo ? null : key); }}
                          disabled={savingResolution === i}
                          style={{ padding: "5px 12px", borderRadius: 8, border: `1.5px solid ${ativo ? m.border : "#e2e8f0"}`, background: ativo ? m.bg : "white", cursor: savingResolution === i ? "wait" : "pointer", fontSize: 11, fontWeight: 600, color: ativo ? m.color : "#64748b", fontFamily: F, transition: "all 0.15s" }}
                        >
                          {m.label}
                        </button>
                      );
                    })}
                  </div>

                  {/* Per-alert feedback */}
                  <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid #f1f5f9", display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 11, color: "#94a3b8", fontWeight: 600, fontFamily: F }}>Este alerta é correto?</span>
                    <button onClick={(e) => { e.stopPropagation(); setAlertVotes(v => ({ ...v, [i]: true })); }} style={{ display: "inline-flex", alignItems: "center", gap: 4, padding: "5px 12px", borderRadius: 8, border: `1.5px solid ${alertVotes[i] === true ? "#10b981" : "#e2e8f0"}`, background: alertVotes[i] === true ? "#f0fdf4" : "white", cursor: "pointer", fontSize: 11, fontWeight: 600, color: alertVotes[i] === true ? "#16a34a" : "#64748b", fontFamily: F, transition: "all 0.15s" }}>
                      <ThumbsUp size={13} /> Sim
                    </button>
                    <button onClick={(e) => { e.stopPropagation(); setAlertVotes(v => ({ ...v, [i]: false })); }} style={{ display: "inline-flex", alignItems: "center", gap: 4, padding: "5px 12px", borderRadius: 8, border: `1.5px solid ${alertVotes[i] === false ? "#ef4444" : "#e2e8f0"}`, background: alertVotes[i] === false ? "#fef2f2" : "white", cursor: "pointer", fontSize: 11, fontWeight: 600, color: alertVotes[i] === false ? "#dc2626" : "#64748b", fontFamily: F, transition: "all 0.15s" }}>
                      <ThumbsDown size={13} /> Não
                    </button>
                    {alertVotes[i] === false && (
                      <input value={alertComments[i] || ""} onChange={(e) => setAlertComments(c => ({ ...c, [i]: e.target.value }))} onClick={(e) => e.stopPropagation()} placeholder="Por que é incorreto? (opcional)" style={{ flex: 1, minWidth: 180, padding: "5px 10px", borderRadius: 8, border: "1px solid #fecaca", fontSize: 11, fontFamily: F, outline: "none", background: "#fff5f5" }} />
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* ── Overall Feedback Panel ── */}
      <div style={{ background: "white", borderRadius: 16, padding: 28, boxShadow: "0 1px 3px rgba(0,0,0,0.06)", border: "1px solid #e2e8f0", marginTop: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 18 }}>
          <div style={{ width: 36, height: 36, borderRadius: 10, background: "linear-gradient(135deg, #8b5cf6, #6d28d9)", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <MessageSquare size={18} color="white" />
          </div>
          <div>
            <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: "#1e293b", fontFamily: F }}>Avaliação da Análise</h3>
            <p style={{ margin: 0, fontSize: 11, color: "#94a3b8", fontFamily: F }}>Seu feedback melhora as análises futuras da IA</p>
          </div>
        </div>

        {feedbackSubmitted || existingFeedback ? (
          <div style={{ textAlign: "center", padding: "20px 0" }}>
            <div style={{ width: 52, height: 52, borderRadius: "50%", background: "linear-gradient(135deg, #10b981, #059669)", margin: "0 auto 12px", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <ThumbsUp size={24} color="white" />
            </div>
            <p style={{ fontSize: 15, fontWeight: 700, color: "#1e293b", margin: "0 0 4px", fontFamily: F }}>Feedback registrado!</p>
            <p style={{ fontSize: 12, color: "#64748b", margin: 0, fontFamily: F }}>A IA considerará sua avaliação nas próximas análises.</p>
            {overallRating > 0 && (
              <div style={{ display: "flex", justifyContent: "center", gap: 4, marginTop: 12 }}>
                {[1,2,3,4,5].map(s => (
                  <Star key={s} size={20} fill={s <= overallRating ? "#f59e0b" : "none"} color={s <= overallRating ? "#f59e0b" : "#cbd5e1"} />
                ))}
              </div>
            )}
            {Object.keys(alertVotes).length > 0 && (
              <div style={{ display: "flex", justifyContent: "center", gap: 16, marginTop: 12 }}>
                <span style={{ fontSize: 12, color: "#16a34a", fontWeight: 600, fontFamily: F }}>
                  ✓ {Object.values(alertVotes).filter(v => v === true).length} corretos
                </span>
                <span style={{ fontSize: 12, color: "#dc2626", fontWeight: 600, fontFamily: F }}>
                  ✗ {Object.values(alertVotes).filter(v => v === false).length} incorretos
                </span>
              </div>
            )}
          </div>
        ) : (
          <>
            {/* Star Rating */}
            <div style={{ marginBottom: 18 }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#475569", marginBottom: 8, fontFamily: F }}>Nota geral da análise</label>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                {[1,2,3,4,5].map(s => (
                  <button key={s} onClick={() => setOverallRating(s)} style={{ background: "none", border: "none", cursor: "pointer", padding: 2, transition: "transform 0.15s", transform: overallRating >= s ? "scale(1.15)" : "scale(1)" }}>
                    <Star size={28} fill={overallRating >= s ? "#f59e0b" : "none"} color={overallRating >= s ? "#f59e0b" : "#cbd5e1"} strokeWidth={1.5} />
                  </button>
                ))}
                {overallRating > 0 && (
                  <span style={{ marginLeft: 8, fontSize: 13, fontWeight: 600, color: "#f59e0b", fontFamily: F }}>
                    {overallRating === 1 ? "Ruim" : overallRating === 2 ? "Regular" : overallRating === 3 ? "Bom" : overallRating === 4 ? "Muito bom" : "Excelente"}
                  </span>
                )}
              </div>
            </div>

            {/* Vote Summary */}
            {Object.keys(alertVotes).length > 0 && (
              <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
                <div style={{ flex: 1, padding: "10px 14px", borderRadius: 10, background: "#f0fdf4", border: "1px solid #bbf7d0", display: "flex", alignItems: "center", gap: 8 }}>
                  <ThumbsUp size={14} color="#16a34a" />
                  <span style={{ fontSize: 12, fontWeight: 600, color: "#16a34a", fontFamily: F }}>
                    {Object.values(alertVotes).filter(v => v === true).length} alertas corretos
                  </span>
                </div>
                <div style={{ flex: 1, padding: "10px 14px", borderRadius: 10, background: "#fef2f2", border: "1px solid #fecaca", display: "flex", alignItems: "center", gap: 8 }}>
                  <ThumbsDown size={14} color="#dc2626" />
                  <span style={{ fontSize: 12, fontWeight: 600, color: "#dc2626", fontFamily: F }}>
                    {Object.values(alertVotes).filter(v => v === false).length} alertas incorretos
                  </span>
                </div>
              </div>
            )}

            {/* Comment */}
            <div style={{ marginBottom: 18 }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#475569", marginBottom: 6, fontFamily: F }}>Comentário geral (opcional)</label>
              <textarea value={overallComment} onChange={(e) => setOverallComment(e.target.value)} placeholder="Ex: A análise identificou bem os riscos, mas faltou mencionar a cláusula de rescisão..." rows={3} style={{ width: "100%", padding: "10px 14px", borderRadius: 10, border: "1px solid #e2e8f0", fontSize: 13, fontFamily: F, resize: "vertical", outline: "none", background: "#f8fafc", transition: "border-color 0.2s", boxSizing: "border-box" }} onFocus={(e) => e.target.style.borderColor = "#8b5cf6"} onBlur={(e) => e.target.style.borderColor = "#e2e8f0"} />
            </div>

            {/* Submit Button */}
            <button onClick={submitFeedback} disabled={submittingFeedback || overallRating === 0} style={{ width: "100%", padding: "12px 20px", borderRadius: 12, border: "none", background: overallRating === 0 ? "#e2e8f0" : "linear-gradient(135deg, #8b5cf6, #6d28d9)", color: overallRating === 0 ? "#94a3b8" : "white", fontSize: 14, fontWeight: 700, fontFamily: F, cursor: overallRating === 0 ? "not-allowed" : "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, transition: "all 0.2s", opacity: submittingFeedback ? 0.7 : 1 }}>
              {submittingFeedback ? (
                <>
                  <div style={{ width: 16, height: 16, border: "2px solid rgba(255,255,255,0.3)", borderTopColor: "white", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
                  Enviando...
                </>
              ) : (
                <>
                  <Send size={16} />
                  Enviar Feedback
                </>
              )}
            </button>
            {overallRating === 0 && (
              <p style={{ textAlign: "center", fontSize: 11, color: "#94a3b8", marginTop: 8, fontFamily: F }}>Selecione uma nota de 1 a 5 estrelas para enviar</p>
            )}
          </>
        )}

        <div style={{ marginTop: 26, padding: "14px 18px", background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 11 }}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 9 }}>
            <Info size={15} color="#94a3b8" style={{ flexShrink: 0, marginTop: 1 }} />
            <div>
              <div style={{ fontSize: 12, color: "#475569", lineHeight: 1.65, fontFamily: F }}>
                Esta análise é gerada por inteligência artificial e serve como apoio à revisão contratual.
                Ela <strong>não substitui parecer jurídico</strong>. Confira os trechos citados no documento
                original e os dispositivos legais antes de tomar qualquer decisão.
              </div>
              {(analysis.model || analysis.analyzed_at) && (
                <div style={{ fontSize: 10.5, color: "#94a3b8", marginTop: 7, fontFamily: F }}>
                  {analysis.analyzed_at && <>Analisado em {new Date(analysis.analyzed_at).toLocaleString("pt-BR")}</>}
                  {analysis.model && <> · modelo {analysis.model}</>}
                  {analysis.prompt_version && <> · critérios v{analysis.prompt_version}</>}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// ── History ──
const HistoryPage = ({ onViewReport, showToast }) => {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sf, setSf] = useState("all");
  const [search, setSearch] = useState("");
  const [showF, setShowF] = useState(false);
  const [delC, setDelC] = useState(null);
  const [clients, setClients] = useState([]);
  const [clientFilter, setClientFilter] = useState("");

  useEffect(() => {
    api.listClients().then(c => setClients(c || [])).catch(() => setClients([]));
  }, []);

  const fetchDocs = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: 100 };
      if (sf !== "all") params.status = sf;
      if (search) params.search = search;
      if (clientFilter) params.clientId = clientFilter;
      const data = await api.listDocuments(params);
      setDocuments(data.documents || []);
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      setLoading(false);
    }
  }, [sf, search, clientFilter, showToast]);

  useEffect(() => { fetchDocs(); }, [fetchDocs]);

  const handleDelete = async (id) => {
    try {
      await api.deleteDocument(id);
      setDocuments(documents.filter(d => d.id !== id));
      setDelC(null);
      showToast("Documento excluído.", "success");
    } catch (err) {
      showToast(err.message, "error");
    }
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20, flexWrap: "wrap", gap: 10 }}>
        <div><h1 style={{ fontSize: 24, fontWeight: 800, color: "#0f172a", fontFamily: F, letterSpacing: "-0.03em", margin: 0 }}>Histórico de Análises</h1><p style={{ color: "#64748b", fontSize: 13, marginTop: 3, fontFamily: F }}>{documents.length} documentos</p></div>
        <button onClick={fetchDocs} style={{ display: "flex", alignItems: "center", gap: 5, padding: "8px 14px", borderRadius: 9, border: "1px solid #e2e8f0", background: "white", cursor: "pointer", fontSize: 12, fontWeight: 600, color: "#64748b", fontFamily: F }}><RefreshCw size={13} /> Atualizar</button>
      </div>
      <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
        <div style={{ position: "relative", flex: 1, minWidth: 180 }}><Search size={15} color="#94a3b8" style={{ position: "absolute", left: 11, top: 10 }} /><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar documento..." style={{ width: "100%", padding: "9px 12px 9px 34px", borderRadius: 9, border: "1px solid #e2e8f0", fontSize: 12, fontFamily: F, outline: "none", boxSizing: "border-box" }} /></div>
        <button onClick={() => setShowF(!showF)} style={{ display: "flex", alignItems: "center", gap: 5, padding: "9px 14px", borderRadius: 9, border: "1px solid #e2e8f0", background: showF ? "#eef2ff" : "white", cursor: "pointer", fontSize: 12, fontWeight: 600, color: showF ? "#6366f1" : "#64748b", fontFamily: F }}><SlidersHorizontal size={14} /> Filtros</button>
      </div>
      {showF && (
        <div style={{ display: "flex", gap: 14, marginBottom: 16, padding: "14px 18px", background: "white", borderRadius: 11, border: "1px solid #e2e8f0", flexWrap: "wrap", animation: "fadeSlideUp 0.2s ease" }}>
          <div><div style={{ fontSize: 10, fontWeight: 600, color: "#64748b", marginBottom: 5, textTransform: "uppercase", letterSpacing: "0.05em", fontFamily: F }}>Status</div><div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>{[{ k: "all", l: "Todos" },{ k: "analyzed", l: "Analisados" },{ k: "processing", l: "Processando" },{ k: "error", l: "Erro" }].map(f => <button key={f.k} onClick={() => setSf(f.k)} style={{ padding: "4px 10px", borderRadius: 14, border: "1px solid", borderColor: sf === f.k ? "#6366f1" : "#e2e8f0", background: sf === f.k ? "#eef2ff" : "white", color: sf === f.k ? "#6366f1" : "#64748b", fontSize: 11, fontWeight: 600, cursor: "pointer", fontFamily: F }}>{f.l}</button>)}</div></div>
          {clients.length > 0 && (
            <div>
              <div style={{ fontSize: 10, fontWeight: 600, color: "#64748b", marginBottom: 5, textTransform: "uppercase", letterSpacing: "0.05em", fontFamily: F }}>Cliente</div>
              <select value={clientFilter} onChange={e => setClientFilter(e.target.value)} style={{ padding: "5px 10px", borderRadius: 14, border: "1px solid", borderColor: clientFilter ? "#6366f1" : "#e2e8f0", background: clientFilter ? "#eef2ff" : "white", color: clientFilter ? "#6366f1" : "#64748b", fontSize: 11, fontWeight: 600, cursor: "pointer", fontFamily: F, outline: "none" }}>
                <option value="">Todos os clientes</option>
                {clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
          )}
        </div>
      )}
      <div style={{ background: "white", borderRadius: 14, border: "1px solid #e2e8f0", overflow: "hidden" }}>
        <div className="history-header" style={{ display: "grid", padding: "11px 18px", borderBottom: "1px solid #f1f5f9", background: "#f8fafc" }}>{["Documento","Data","Score","Status","Ações"].map(h => <div key={h} style={{ fontSize: 10, fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.05em", fontFamily: F }}>{h}</div>)}</div>
        {loading ? <div style={{ padding: 36, textAlign: "center" }}><Loader2 size={20} color="#6366f1" style={{ animation: "spin 1s linear infinite" }} /></div> : documents.length === 0 ? <div style={{ padding: 36, textAlign: "center", color: "#94a3b8", fontSize: 13 }}>Nenhum documento encontrado.</div> : documents.map((doc, i) => { const st = getStatusStyle(doc.status); return (
          <div key={doc.id} className="history-row" style={{ display: "grid", padding: "12px 18px", borderBottom: i < documents.length - 1 ? "1px solid #f8fafc" : "none", alignItems: "center", transition: "background 0.15s" }} onMouseEnter={e => e.currentTarget.style.background = "#fafbfc"} onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}><FileText size={15} color="#94a3b8" style={{ flexShrink: 0 }} /><div style={{ minWidth: 0 }}><div style={{ fontSize: 12, fontWeight: 600, color: "#1e293b", fontFamily: F, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{doc.filename}</div><div style={{ fontSize: 10, color: "#94a3b8" }}>{formatFileSize(doc.file_size)}</div></div></div>
            <div style={{ fontSize: 11, color: "#64748b", fontFamily: F }}>{formatDate(doc.uploaded_at)}</div>
            <div>{doc.risk_score != null ? <div style={{ display: "flex", alignItems: "center", gap: 5 }}><div style={{ width: 32, height: 4, background: "#e5e7eb", borderRadius: 2, overflow: "hidden" }}><div style={{ width: `${doc.risk_score}%`, height: "100%", background: getRiskColor(doc.risk_score), borderRadius: 2 }} /></div><span style={{ fontSize: 12, fontWeight: 700, color: getRiskColor(doc.risk_score), fontFamily: F }}>{doc.risk_score}</span></div> : <span style={{ color: "#cbd5e1", fontSize: 11 }}>—</span>}</div>
            <div><span style={{ fontSize: 10, fontWeight: 600, color: st.color, background: st.bg, padding: "2px 9px", borderRadius: 20, fontFamily: F }}>{st.label}</span></div>
            <div style={{ display: "flex", gap: 3 }}>
              {doc.status === "analyzed" && <button onClick={() => onViewReport(doc.id)} style={{ width: 30, height: 30, borderRadius: 7, border: "1px solid #e2e8f0", background: "white", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }} title="Ver relatório"><Eye size={13} color="#6366f1" /></button>}
              <button onClick={() => setDelC(doc.id)} style={{ width: 30, height: 30, borderRadius: 7, border: "1px solid #e2e8f0", background: "white", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }} title="Deletar"><Trash2 size={13} color="#ef4444" /></button>
            </div>
          </div>
        ); })}
      </div>
      <Modal open={!!delC} onClose={() => setDelC(null)} title="Confirmar exclusão" width={400}>
        <div style={{ display: "flex", alignItems: "flex-start", gap: 12, marginBottom: 18 }}>
          <div style={{ width: 36, height: 36, borderRadius: 9, background: "#fef2f2", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}><AlertTriangle size={18} color="#ef4444" /></div>
          <div><p style={{ fontSize: 13, color: "#1e293b", margin: "0 0 4px", fontWeight: 600, fontFamily: F }}>Excluir este documento?</p><p style={{ fontSize: 12, color: "#64748b", margin: 0, fontFamily: F, lineHeight: 1.5 }}>O documento e sua análise serão removidos permanentemente.</p></div>
        </div>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button onClick={() => setDelC(null)} style={{ padding: "8px 16px", borderRadius: 9, border: "1px solid #e2e8f0", background: "white", cursor: "pointer", fontSize: 12, fontWeight: 600, color: "#64748b", fontFamily: F }}>Cancelar</button>
          <button onClick={() => handleDelete(delC)} style={{ padding: "8px 16px", borderRadius: 9, border: "none", background: "#ef4444", cursor: "pointer", fontSize: 12, fontWeight: 600, color: "white", fontFamily: F }}>Excluir</button>
        </div>
      </Modal>
    </div>
  );
};

// ── Legislation / Base Legal ──
const CATEGORY_META = {
  "proteção_de_dados": { label: "Proteção de Dados", color: "#6366f1", bg: "#eef2ff", icon: Lock },
  "consumidor": { label: "Consumidor", color: "#0891b2", bg: "#ecfeff", icon: Shield },
  "civil": { label: "Civil", color: "#7c3aed", bg: "#f5f3ff", icon: Scale },
  "trabalhista": { label: "Trabalhista", color: "#ea580c", bg: "#fff7ed", icon: FileText },
  "internet": { label: "Internet", color: "#2563eb", bg: "#eff6ff", icon: Zap },
  "anticorrupção": { label: "Anticorrupção", color: "#dc2626", bg: "#fef2f2", icon: AlertTriangle },
  "licitações": { label: "Licitações", color: "#059669", bg: "#ecfdf5", icon: BarChart3 },
  // As leis ingeridas do Planalto gravam a categoria sem acento.
  "protecao_de_dados": { label: "Proteção de Dados", color: "#6366f1", bg: "#eef2ff", icon: Lock },
  "anticorrupcao": { label: "Anticorrupção", color: "#dc2626", bg: "#fef2f2", icon: AlertTriangle },
  "licitacoes": { label: "Licitações", color: "#059669", bg: "#ecfdf5", icon: BarChart3 },
  "locacao": { label: "Locação", color: "#b45309", bg: "#fffbeb", icon: FileText },
  "societario": { label: "Societário", color: "#0f766e", bg: "#f0fdfa", icon: BarChart3 },
  "propriedade_industrial": { label: "Propriedade Industrial", color: "#9333ea", bg: "#faf5ff", icon: Shield },
};
const getCatMeta = (cat) => CATEGORY_META[cat] || { label: cat || "Geral", color: "#64748b", bg: "#f8fafc", icon: FileText };

const LegislationPage = ({ showToast }) => {
  const [laws, setLaws] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedLaw, setSelectedLaw] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState(null);
  const [searching, setSearching] = useState(false);
  const [filterCat, setFilterCat] = useState("");

  useEffect(() => {
    api.listLegislation().then(data => setLaws(data || [])).catch(() => showToast("Erro ao carregar legislação", "error")).finally(() => setLoading(false));
  }, []);

  const openLaw = async (law) => {
    setSelectedLaw(law);
    setDetailLoading(true);
    setSearchResults(null);
    try {
      const d = await api.getLegislation(law.id);
      setDetail(d);
    } catch { showToast("Erro ao carregar detalhes", "error"); }
    finally { setDetailLoading(false); }
  };

  const doSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    setSelectedLaw(null);
    setDetail(null);
    try {
      const res = await api.searchLegislation(searchQuery.trim(), 10, filterCat || null);
      setSearchResults(res);
    } catch { showToast("Erro na busca semântica", "error"); }
    finally { setSearching(false); }
  };

  const goBack = () => { setSelectedLaw(null); setDetail(null); };

  const categories = [...new Set(laws.map(l => l.category))];
  const filtered = filterCat ? laws.filter(l => l.category === filterCat) : laws;

  if (loading) return <div style={{ display: "flex", justifyContent: "center", padding: 60 }}><Loader2 size={28} color="#6366f1" style={{ animation: "spin 1s linear infinite" }} /></div>;

  // ── Detail view ──
  if (selectedLaw && detail) {
    const meta = getCatMeta(detail.category);
    return (
      <div>
        <button onClick={goBack} style={{ display: "flex", alignItems: "center", gap: 5, background: "none", border: "none", cursor: "pointer", color: "#6366f1", fontWeight: 600, fontSize: 12, marginBottom: 18, padding: 0, fontFamily: F }}><ArrowLeft size={15} /> Voltar à Base Legal</button>
        <div style={{ background: "white", borderRadius: 14, border: "1px solid #e2e8f0", overflow: "hidden", animation: "fadeSlideUp 0.4s ease" }}>
          <div style={{ padding: "22px 26px", borderBottom: "1px solid #f1f5f9", background: `linear-gradient(135deg, ${meta.bg}, white)` }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
              <div style={{ width: 38, height: 38, borderRadius: 10, background: meta.bg, border: `1px solid ${meta.color}22`, display: "flex", alignItems: "center", justifyContent: "center" }}><meta.icon size={18} color={meta.color} /></div>
              <div>
                <h2 style={{ fontSize: 18, fontWeight: 800, color: "#0f172a", margin: 0, fontFamily: F }}>{detail.title}</h2>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 3 }}>
                  <span style={{ fontSize: 10, fontWeight: 600, color: meta.color, background: `${meta.color}15`, padding: "2px 9px", borderRadius: 20, fontFamily: F }}>{meta.label}</span>
                  <span style={{ fontSize: 11, color: "#64748b", fontFamily: F }}>{detail.source}</span>
                  <span style={{ fontSize: 11, color: "#94a3b8", fontFamily: F }}>{detail.chunks?.length || 0} artigos</span>
                </div>
              </div>
            </div>
          </div>
          <div style={{ padding: "16px 26px", maxHeight: "65vh", overflowY: "auto" }}>
            {detail.chunks?.length === 0 && <div style={{ textAlign: "center", color: "#94a3b8", padding: 30, fontSize: 13 }}>Nenhum artigo indexado</div>}
            {detail.chunks?.map((chunk, i) => (
              <div key={chunk.id} style={{ padding: "14px 0", borderBottom: i < detail.chunks.length - 1 ? "1px solid #f1f5f9" : "none", animation: `fadeSlideUp 0.3s ease ${i * 0.03}s both` }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                  {chunk.article_ref && <span style={{ fontSize: 11, fontWeight: 700, color: meta.color, background: meta.bg, padding: "2px 10px", borderRadius: 6, fontFamily: F }}>{chunk.article_ref}</span>}
                  <span style={{ fontSize: 10, color: "#94a3b8", fontFamily: F }}>Trecho {chunk.chunk_index + 1}</span>
                </div>
                <p style={{ fontSize: 13, color: "#374151", lineHeight: 1.7, margin: 0, fontFamily: F, whiteSpace: "pre-wrap" }}>{chunk.content}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // ── Search results view ──
  if (searchResults) {
    return (
      <div>
        <button onClick={() => setSearchResults(null)} style={{ display: "flex", alignItems: "center", gap: 5, background: "none", border: "none", cursor: "pointer", color: "#6366f1", fontWeight: 600, fontSize: 12, marginBottom: 18, padding: 0, fontFamily: F }}><ArrowLeft size={15} /> Voltar à Base Legal</button>
        <div style={{ marginBottom: 20 }}>
          <h2 style={{ fontSize: 18, fontWeight: 800, color: "#0f172a", margin: "0 0 4px", fontFamily: F }}>Resultados da Busca</h2>
          <p style={{ color: "#64748b", fontSize: 12, margin: 0, fontFamily: F }}>"{searchQuery}" — {searchResults.total} resultado{searchResults.total !== 1 ? "s" : ""} encontrado{searchResults.total !== 1 ? "s" : ""}</p>
        </div>
        {searchResults.results.length === 0 ? <div style={{ background: "white", borderRadius: 14, border: "1px solid #e2e8f0", padding: 40, textAlign: "center", color: "#94a3b8", fontSize: 13 }}>Nenhum resultado encontrado para esta busca.</div> :
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {searchResults.results.map((r, i) => {
              const meta = getCatMeta(laws.find(l => l.title === r.document_title)?.category);
              return (
                <div key={r.id} style={{ background: "white", borderRadius: 12, border: "1px solid #e2e8f0", padding: "16px 20px", animation: `fadeSlideUp 0.3s ease ${i * 0.05}s both` }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                    {r.article_ref && <span style={{ fontSize: 10, fontWeight: 700, color: meta.color, background: meta.bg, padding: "2px 9px", borderRadius: 6, fontFamily: F }}>{r.article_ref}</span>}
                    <span style={{ fontSize: 11, fontWeight: 600, color: "#374151", fontFamily: F }}>{r.document_title}</span>
                    <span style={{ fontSize: 10, color: "#94a3b8", fontFamily: F }}>• {r.document_source}</span>
                    <span style={{ marginLeft: "auto", fontSize: 10, fontWeight: 600, color: r.similarity > 0.8 ? "#10b981" : r.similarity > 0.5 ? "#f59e0b" : "#94a3b8", background: r.similarity > 0.8 ? "#f0fdf4" : r.similarity > 0.5 ? "#fffbeb" : "#f9fafb", padding: "2px 8px", borderRadius: 20, fontFamily: F }}>{Math.round(r.similarity * 100)}% relevante</span>
                  </div>
                  <p style={{ fontSize: 12, color: "#475569", lineHeight: 1.65, margin: 0, fontFamily: F }}>{r.content.length > 300 ? r.content.slice(0, 300) + "…" : r.content}</p>
                </div>
              );
            })}
          </div>
        }
      </div>
    );
  }

  // ── Main list view ──
  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 800, color: "#0f172a", fontFamily: F, letterSpacing: "-0.03em", margin: 0 }}>Base Legal</h1>
        <p style={{ color: "#64748b", fontSize: 13, marginTop: 3, fontFamily: F }}>Legislação indexada para análise de compliance via IA</p>
      </div>

      {/* Search bar */}
      <div style={{ display: "flex", gap: 10, marginBottom: 20, flexWrap: "wrap" }}>
        <div style={{ flex: 1, minWidth: 220, position: "relative" }}>
          <Search size={16} color="#94a3b8" style={{ position: "absolute", left: 12, top: 11 }} />
          <input value={searchQuery} onChange={e => setSearchQuery(e.target.value)} onKeyDown={e => e.key === "Enter" && doSearch()} placeholder="Busca semântica na legislação... ex: 'direito ao esquecimento'" style={{ width: "100%", padding: "10px 14px 10px 38px", borderRadius: 10, border: "1px solid #d1d5db", fontSize: 13, fontFamily: F, outline: "none", boxSizing: "border-box" }} />
        </div>
        <select value={filterCat} onChange={e => setFilterCat(e.target.value)} style={{ padding: "10px 14px", borderRadius: 10, border: "1px solid #d1d5db", fontSize: 12, fontFamily: F, outline: "none", background: "white", minWidth: 150 }}>
          <option value="">Todas as categorias</option>
          {categories.map(c => <option key={c} value={c}>{getCatMeta(c).label}</option>)}
        </select>
        <button onClick={doSearch} disabled={searching || !searchQuery.trim()} style={{ padding: "10px 20px", borderRadius: 10, border: "none", background: "linear-gradient(135deg, #6366f1, #8b5cf6)", color: "white", fontSize: 12, fontWeight: 600, fontFamily: F, cursor: "pointer", display: "flex", alignItems: "center", gap: 6, opacity: searching ? 0.7 : 1 }}>
          {searching ? <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} /> : <Search size={14} />}Buscar
        </button>
      </div>

      {/* Stats strip */}
      <div style={{ display: "flex", gap: 10, marginBottom: 20, flexWrap: "wrap" }}>
        <div style={{ background: "white", borderRadius: 10, border: "1px solid #e2e8f0", padding: "10px 16px", display: "flex", alignItems: "center", gap: 8 }}>
          <BookOpen size={16} color="#6366f1" />
          <span style={{ fontSize: 12, color: "#64748b", fontFamily: F }}><strong style={{ color: "#0f172a" }}>{laws.length}</strong> legislações</span>
        </div>
        <div style={{ background: "white", borderRadius: 10, border: "1px solid #e2e8f0", padding: "10px 16px", display: "flex", alignItems: "center", gap: 8 }}>
          <Hash size={16} color="#8b5cf6" />
          <span style={{ fontSize: 12, color: "#64748b", fontFamily: F }}><strong style={{ color: "#0f172a" }}>{laws.reduce((s, l) => s + (l.chunk_count || 0), 0)}</strong> artigos indexados</span>
        </div>
        <div style={{ background: "white", borderRadius: 10, border: "1px solid #e2e8f0", padding: "10px 16px", display: "flex", alignItems: "center", gap: 8 }}>
          <Filter size={16} color="#f59e0b" />
          <span style={{ fontSize: 12, color: "#64748b", fontFamily: F }}><strong style={{ color: "#0f172a" }}>{categories.length}</strong> categorias</span>
        </div>
      </div>

      {/* Law cards */}
      {filtered.length === 0 ? (
        <div style={{ background: "white", borderRadius: 14, border: "1px solid #e2e8f0", padding: 40, textAlign: "center" }}>
          <BookOpen size={36} color="#d1d5db" style={{ marginBottom: 10 }} />
          <p style={{ color: "#94a3b8", fontSize: 13, fontFamily: F }}>Nenhuma legislação encontrada{filterCat ? " nesta categoria" : ""}.</p>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 14 }}>
          {filtered.map((law, i) => {
            const meta = getCatMeta(law.category);
            return (
              <div key={law.id} onClick={() => openLaw(law)} style={{ background: "white", borderRadius: 13, border: "1px solid #e2e8f0", padding: "18px 20px", cursor: "pointer", transition: "all 0.2s", animation: `fadeSlideUp 0.4s ease ${i * 0.05}s both` }} onMouseEnter={e => { e.currentTarget.style.borderColor = meta.color + "55"; e.currentTarget.style.transform = "translateY(-2px)"; e.currentTarget.style.boxShadow = "0 4px 16px rgba(0,0,0,0.06)"; }} onMouseLeave={e => { e.currentTarget.style.borderColor = "#e2e8f0"; e.currentTarget.style.transform = ""; e.currentTarget.style.boxShadow = ""; }}>
                <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                  <div style={{ width: 40, height: 40, borderRadius: 10, background: meta.bg, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}><meta.icon size={18} color={meta.color} /></div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <h3 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: "0 0 4px", fontFamily: F, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{law.title}</h3>
                    <p style={{ fontSize: 11, color: "#64748b", margin: "0 0 8px", fontFamily: F }}>{law.source}</p>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      <span style={{ fontSize: 10, fontWeight: 600, color: meta.color, background: `${meta.color}12`, padding: "2px 8px", borderRadius: 20, fontFamily: F }}>{meta.label}</span>
                      <span style={{ fontSize: 10, color: "#94a3b8", fontFamily: F, display: "flex", alignItems: "center", gap: 3 }}><Hash size={10} />{law.chunk_count} artigos</span>
                    </div>
                  </div>
                  <ChevronRight size={16} color="#c7d2fe" style={{ flexShrink: 0, marginTop: 4 }} />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

// ── Rules ──
// Origem da regra: padrão do sistema, própria do usuário ou da equipe.
// Resultado da conferencia que o backend faz de cada alerta. O objetivo e dizer
// ao leitor onde ele pode confiar e onde precisa abrir a fonte, nao esconder nada.
const EXCERPT_CHECK = {
  exact:       { label: "Trecho conferido",     color: "#15803d", bg: "#f0fdf4", border: "#bbf7d0",
                 hint: "Este trecho foi localizado no documento enviado." },
  approximate: { label: "Trecho aproximado",    color: "#b45309", bg: "#fffbeb", border: "#fde68a",
                 hint: "Parecido com uma passagem do documento, mas não idêntico. Confira no original." },
  not_found:   { label: "Trecho não localizado", color: "#b91c1c", bg: "#fef2f2", border: "#fecaca",
                 hint: "Não encontramos esta passagem no documento. Confira antes de usar." },
};

const LEGAL_CHECK = {
  grounded:    { label: "Artigo conferido",  color: "#15803d", bg: "#f0fdf4", border: "#bbf7d0",
                 hint: "O artigo citado está na base legal consultada nesta análise." },
  in_base:     { label: "Artigo na base",    color: "#15803d", bg: "#f0fdf4", border: "#bbf7d0",
                 hint: "O dispositivo existe na base legal e pode ser lido abaixo, embora não tenha sido usado como contexto desta análise." },
  law_only:    { label: "Lei confere",       color: "#b45309", bg: "#fffbeb", border: "#fde68a",
                 hint: "A lei citada existe na base. O alerta não aponta um artigo específico, ou o artigo não foi localizado." },
  ungrounded:  { label: "Citação sem respaldo", color: "#b91c1c", bg: "#fef2f2", border: "#fecaca",
                 hint: "Nada na base legal consultada sustenta esta citação. Confira antes de usar." },
};

// O que o revisor decidiu sobre o alerta. Serve para percorrer uma lista longa
// sem perder o que ja foi tratado entre uma sessao e outra.
const RESOLUTION_META = {
  to_fix:         { label: "Corrigir",       short: "Corrigir",      color: "#b45309", bg: "#fffbeb", border: "#fde68a" },
  not_applicable: { label: "Não se aplica",  short: "Não se aplica", color: "#64748b", bg: "#f1f5f9", border: "#e2e8f0" },
  resolved:       { label: "Resolvido",      short: "Resolvido",     color: "#15803d", bg: "#f0fdf4", border: "#bbf7d0" },
};

const CheckBadge = ({ meta }) => meta ? (
  <span title={meta.hint} style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 10, fontWeight: 600, color: meta.color, background: meta.bg, border: `1px solid ${meta.border}`, padding: "2px 8px", borderRadius: 20, fontFamily: F, cursor: "help" }}>
    {meta.label}
  </span>
) : null;

const SCOPE_META = {
  global: { label: "Padrão", color: "#64748b", bg: "#f1f5f9", border: "#e2e8f0", hint: "Regra padrão do sistema. Você pode desativá-la para você, mas não editá-la." },
  user: { label: "Minha", color: "#6366f1", bg: "#eef2ff", border: "#c7d2fe", hint: "Regra sua, válida apenas na sua conta." },
  organization: { label: "Equipe", color: "#7c3aed", bg: "#f5f3ff", border: "#ddd6fe", hint: "Regra da equipe, compartilhada com os membros." },
};

// CRUD de regras. Sem `organizationId` opera no escopo pessoal; com ele, no da equipe.
// Explica o modelo de regras a quem chega pela primeira vez. O ponto principal e
// tranquilizador: nada precisa ser configurado para analisar o primeiro contrato.
const RulesIntro = ({ globalCount, ownCount, isTeam, onDismiss }) => (
  <div style={{ background: "linear-gradient(135deg, #eef2ff, #faf5ff)", border: "1px solid #ddd6fe", borderRadius: 13, padding: "18px 20px", marginBottom: 18, position: "relative", animation: "fadeSlideUp 0.4s ease" }}>
    <button onClick={onDismiss} title="Não mostrar novamente" style={{ position: "absolute", top: 12, right: 12, width: 24, height: 24, borderRadius: 6, border: "none", background: "rgba(255,255,255,0.7)", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <X size={13} color="#6b7280" />
    </button>

    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 9 }}>
      <Info size={16} color="#6366f1" />
      <h3 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: 0, fontFamily: F }}>Como funcionam as regras</h3>
    </div>

    <p style={{ fontSize: 12.5, color: "#475569", margin: "0 0 13px", fontFamily: F, lineHeight: 1.6, maxWidth: 620 }}>
      {globalCount > 0
        ? <>Você já tem <strong>{globalCount} regras padrão</strong> ativas, cobrindo LGPD, CDC, Código Civil, CLT e mais. Não precisa configurar nada para analisar seu primeiro contrato: ajuste só se quiser algo diferente do padrão.</>
        : <>As regras definem o que a IA verifica em cada contrato. Crie a primeira para começar.</>}
    </p>

    <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 9 }}>
        <span style={{ fontSize: 10, fontWeight: 600, color: SCOPE_META.global.color, background: "white", padding: "2px 8px", borderRadius: 20, border: `1px solid ${SCOPE_META.global.border}`, fontFamily: F, flexShrink: 0, marginTop: 1 }}>Padrão</span>
        <span style={{ fontSize: 12, color: "#475569", fontFamily: F, lineHeight: 1.5 }}>Vêm com o sistema e não podem ser editadas. Se alguma não se aplica ao seu caso, desative-a: vale só para {isTeam ? "esta equipe" : "você"}.</span>
      </div>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 9 }}>
        <span style={{ fontSize: 10, fontWeight: 600, color: isTeam ? SCOPE_META.organization.color : SCOPE_META.user.color, background: "white", padding: "2px 8px", borderRadius: 20, border: `1px solid ${isTeam ? SCOPE_META.organization.border : SCOPE_META.user.border}`, fontFamily: F, flexShrink: 0, marginTop: 1 }}>{isTeam ? "Equipe" : "Minha"}</span>
        <span style={{ fontSize: 12, color: "#475569", fontFamily: F, lineHeight: 1.5 }}>
          {isTeam
            ? "Criadas aqui e compartilhadas com todos os membros da equipe."
            : <>Suas próprias regras{ownCount > 0 ? <> (você já tem {ownCount})</> : null}. Use para exigências específicas do seu contexto, como um prazo de pagamento mais rígido.</>}
        </span>
      </div>
    </div>
  </div>
);

// ── Camada de escritório: carteira de clientes, retenção e auditoria ──
// Um escritório não organiza o trabalho por arquivo, e sim por cliente: é ele
// que define quem pode ler o material, por quanto tempo fica guardado e o que a
// auditoria precisa reconstruir depois.

const ACTION_META = {
  view: { label: "Leu o relatório", color: "#0891b2", bg: "#ecfeff" },
  download: { label: "Baixou o original", color: "#7c3aed", bg: "#f5f3ff" },
  export: { label: "Exportou", color: "#2563eb", bg: "#eff6ff" },
  analyze: { label: "Enviou para análise", color: "#059669", bg: "#ecfdf5" },
  delete: { label: "Excluiu", color: "#dc2626", bg: "#fef2f2" },
  assign: { label: "Designou", color: "#ea580c", bg: "#fff7ed" },
  unassign: { label: "Retirou designação", color: "#b45309", bg: "#fffbeb" },
  denied: { label: "Acesso negado", color: "#991b1b", bg: "#fef2f2" },
};

const RETENTION_OPTIONS = [
  { value: "", label: "Sem prazo definido" },
  { value: 12, label: "1 ano" },
  { value: 24, label: "2 anos" },
  { value: 60, label: "5 anos" },
  { value: 120, label: "10 anos" },
  { value: 240, label: "20 anos" },
];

const ClientsPage = ({ showToast, scopeOrgId, canManage = true }) => {
  const [aba, setAba] = useState("carteira");
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState(null);
  const [fd, setFd] = useState({ name: "", document: "", notes: "", retention_months: "" });
  const [saving, setSaving] = useState(false);
  const [delC, setDelC] = useState(null);
  const [detalhe, setDetalhe] = useState(null);      // cliente aberto no painel de designações
  const [designados, setDesignados] = useState([]);
  const [novoEmail, setNovoEmail] = useState("");
  const [vencidos, setVencidos] = useState([]);
  const [marcados, setMarcados] = useState({});
  const [confirmaExpurgo, setConfirmaExpurgo] = useState(false);
  const [logs, setLogs] = useState([]);

  const fetchClients = useCallback(async () => {
    setLoading(true);
    try {
      setClients(await api.listClients() || []);
    } catch (err) {
      showToast(err.message, "error");
    } finally { setLoading(false); }
  }, [showToast]);

  useEffect(() => { fetchClients(); }, [fetchClients]);

  useEffect(() => {
    if (aba === "retencao") api.listExpired().then(v => setVencidos(v || [])).catch(() => setVencidos([]));
    if (aba === "auditoria") api.listAccessLogs().then(l => setLogs(l || [])).catch(() => setLogs([]));
  }, [aba, scopeOrgId]);

  const openNew = () => { setFd({ name: "", document: "", notes: "", retention_months: "" }); setEditId(null); setShowForm(true); };
  const openEdit = (c) => {
    setFd({ name: c.name, document: c.document || "", notes: c.notes || "", retention_months: c.retention_months || "" });
    setEditId(c.id);
    setShowForm(true);
  };

  const save = async () => {
    if (!fd.name.trim()) { showToast("O nome do cliente é obrigatório", "error"); return; }
    setSaving(true);
    const payload = {
      name: fd.name.trim(),
      document: fd.document || null,
      notes: fd.notes || null,
      retention_months: fd.retention_months ? Number(fd.retention_months) : null,
    };
    try {
      if (editId) {
        await api.updateClient(editId, payload);
        showToast("Cliente atualizado", "success");
      } else {
        await api.createClient(payload);
        showToast("Cliente criado", "success");
      }
      setShowForm(false);
      setEditId(null);
      fetchClients();
    } catch (err) {
      showToast(err.message, "error");
    } finally { setSaving(false); }
  };

  const remover = async (id) => {
    try {
      await api.deleteClient(id);
      setDelC(null);
      showToast("Cliente excluído. Os documentos foram mantidos.", "success");
      fetchClients();
    } catch (err) { showToast(err.message, "error"); }
  };

  const abrirDesignacoes = async (c) => {
    setDetalhe(c);
    setNovoEmail("");
    try {
      setDesignados(await api.listAssignees(c.id) || []);
    } catch (err) { showToast(err.message, "error"); }
  };

  const designar = async () => {
    if (!novoEmail.trim()) return;
    try {
      const criado = await api.assignUser(detalhe.id, novoEmail.trim());
      setDesignados([...designados, criado]);
      setNovoEmail("");
      showToast("Acesso concedido", "success");
      fetchClients();
    } catch (err) { showToast(err.message, "error"); }
  };

  const retirar = async (userId) => {
    try {
      await api.unassignUser(detalhe.id, userId);
      setDesignados(designados.filter(d => d.user_id !== userId));
      showToast("Acesso retirado", "success");
      fetchClients();
    } catch (err) { showToast(err.message, "error"); }
  };

  const expurgar = async () => {
    const ids = Object.keys(marcados).filter(k => marcados[k]);
    try {
      const r = await api.purgeDocuments(ids);
      setConfirmaExpurgo(false);
      setMarcados({});
      showToast(`${r.deleted} ${r.deleted === 1 ? "documento excluído" : "documentos excluídos"}`, "success");
      setVencidos(await api.listExpired() || []);
      fetchClients();
    } catch (err) { showToast(err.message, "error"); }
  };

  const marcadosCount = Object.values(marcados).filter(Boolean).length;
  const totalVencidos = clients.reduce((n, c) => n + (c.expired_count || 0), 0);

  const abas = [
    { id: "carteira", icon: Briefcase, label: "Carteira", badge: clients.length },
    { id: "retencao", icon: Archive, label: "Retenção", badge: totalVencidos || null },
    { id: "auditoria", icon: History, label: "Auditoria", badge: null },
  ];

  if (loading) return <div style={{ padding: 60, textAlign: "center" }}><Loader2 size={26} style={{ animation: "spin 1s linear infinite" }} color="#6366f1" /></div>;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 18, gap: 12, flexWrap: "wrap" }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 800, color: "#0f172a", margin: 0, fontFamily: F, letterSpacing: "-0.5px" }}>Clientes</h1>
          <p style={{ fontSize: 12, color: "#64748b", margin: "4px 0 0", fontFamily: F }}>
            {scopeOrgId
              ? "Quem é designado a um cliente enxerga os contratos dele. Os demais não."
              : "Sua carteira pessoal. Serve para organizar o acervo e definir o prazo de guarda."}
          </p>
        </div>
        {canManage && aba === "carteira" && (
          <button onClick={() => showForm ? setShowForm(false) : openNew()} style={{ display: "flex", alignItems: "center", gap: 5, padding: "9px 16px", borderRadius: 9, border: "none", cursor: "pointer", fontWeight: 600, fontSize: 12, background: showForm ? "#f1f5f9" : "linear-gradient(135deg, #6366f1, #8b5cf6)", color: showForm ? "#64748b" : "white", fontFamily: F }}>
            {showForm ? <><X size={15} /> Cancelar</> : <><Plus size={15} /> Novo Cliente</>}
          </button>
        )}
      </div>

      <div style={{ display: "flex", gap: 4, borderBottom: "1px solid #e2e8f0", marginBottom: 18 }}>
        {abas.map(a => {
          const ativa = aba === a.id;
          return (
            <button key={a.id} onClick={() => setAba(a.id)} style={{ display: "flex", alignItems: "center", gap: 6, padding: "9px 14px", background: "none", border: "none", borderBottom: `2px solid ${ativa ? "#6366f1" : "transparent"}`, marginBottom: -1, cursor: "pointer", fontSize: 12.5, fontWeight: ativa ? 700 : 600, color: ativa ? "#6366f1" : "#94a3b8", fontFamily: F }}>
              <a.icon size={14} /> {a.label}
              {a.badge != null && a.badge > 0 && (
                <span style={{ fontSize: 10, fontWeight: 700, background: a.id === "retencao" ? "#fef2f2" : "#f1f5f9", color: a.id === "retencao" ? "#dc2626" : "#64748b", padding: "1px 7px", borderRadius: 20 }}>{a.badge}</span>
              )}
            </button>
          );
        })}
      </div>

      {aba === "carteira" && (
        <>
          {showForm && (
            <div style={{ background: "white", borderRadius: 13, border: "1px solid #e2e8f0", padding: 22, marginBottom: 18, animation: "fadeSlideUp 0.3s ease" }}>
              <h3 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: "0 0 16px", fontFamily: F }}>{editId ? "Editar cliente" : "Novo cliente"}</h3>
              <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 12, marginBottom: 12 }}>
                <div>
                  <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: "#374151", marginBottom: 4, fontFamily: F }}>Nome *</label>
                  <input value={fd.name} onChange={e => setFd({ ...fd, name: e.target.value })} placeholder="Ex: Construtora Aurora" style={{ width: "100%", padding: "9px 11px", borderRadius: 9, border: "1px solid #d1d5db", fontSize: 12, fontFamily: F, outline: "none", boxSizing: "border-box" }} />
                </div>
                <div>
                  <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: "#374151", marginBottom: 4, fontFamily: F }}>CNPJ ou CPF</label>
                  <input value={fd.document} onChange={e => setFd({ ...fd, document: e.target.value })} placeholder="Opcional" style={{ width: "100%", padding: "9px 11px", borderRadius: 9, border: "1px solid #d1d5db", fontSize: 12, fontFamily: F, outline: "none", boxSizing: "border-box" }} />
                </div>
              </div>
              <div style={{ marginBottom: 12 }}>
                <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: "#374151", marginBottom: 4, fontFamily: F }}>Prazo de guarda</label>
                <select value={fd.retention_months} onChange={e => setFd({ ...fd, retention_months: e.target.value })} style={{ width: "100%", padding: "9px 11px", borderRadius: 9, border: "1px solid #d1d5db", fontSize: 12, fontFamily: F, outline: "none", background: "white", boxSizing: "border-box" }}>
                  {RETENTION_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
                <div style={{ fontSize: 10.5, color: "#94a3b8", marginTop: 5, fontFamily: F }}>Vencido o prazo, o documento entra na fila de retenção. Nada é apagado sem alguém confirmar.</div>
              </div>
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: "#374151", marginBottom: 4, fontFamily: F }}>Observações</label>
                <textarea value={fd.notes} onChange={e => setFd({ ...fd, notes: e.target.value })} rows={2} style={{ width: "100%", padding: "9px 11px", borderRadius: 9, border: "1px solid #d1d5db", fontSize: 12, fontFamily: F, outline: "none", resize: "vertical", boxSizing: "border-box" }} />
              </div>
              <button onClick={save} disabled={saving} style={{ padding: "9px 20px", borderRadius: 9, border: "none", cursor: "pointer", background: "linear-gradient(135deg, #6366f1, #8b5cf6)", color: "white", fontWeight: 600, fontSize: 12, fontFamily: F, opacity: saving ? 0.7 : 1, display: "flex", alignItems: "center", gap: 6 }}>
                {saving && <Loader2 size={13} style={{ animation: "spin 1s linear infinite" }} />}
                {editId ? "Salvar alterações" : "Criar cliente"}
              </button>
            </div>
          )}

          {clients.length === 0 && !showForm ? (
            <div style={{ background: "white", borderRadius: 13, border: "1px dashed #cbd5e1", padding: "40px 28px", textAlign: "center" }}>
              <div style={{ width: 48, height: 48, borderRadius: 13, background: "#eef2ff", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 14px" }}><Briefcase size={22} color="#6366f1" /></div>
              <div style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", fontFamily: F }}>Nenhum cliente cadastrado</div>
              <p style={{ fontSize: 12, color: "#64748b", margin: "6px auto 0", maxWidth: 420, fontFamily: F, lineHeight: 1.6 }}>
                Enquanto não houver clientes, tudo funciona como antes: os contratos ficam visíveis a toda a equipe. Cadastrar um cliente é o que permite restringir quem lê o quê e definir prazo de guarda.
              </p>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {clients.map((c, i) => (
                <div key={c.id} style={{ background: "white", borderRadius: 11, border: "1px solid #e2e8f0", padding: "16px 18px", animation: `fadeSlideUp 0.4s ease ${i * 0.04}s both` }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontSize: 13.5, fontWeight: 700, color: "#0f172a", fontFamily: F }}>{c.name}</span>
                        {c.document && <span style={{ fontSize: 10.5, color: "#94a3b8", fontFamily: F }}>{c.document}</span>}
                        {c.expired_count > 0 && (
                          <span style={{ fontSize: 10, fontWeight: 700, color: "#dc2626", background: "#fef2f2", padding: "2px 8px", borderRadius: 20, fontFamily: F }}>{c.expired_count} vencido{c.expired_count > 1 ? "s" : ""}</span>
                        )}
                      </div>
                      <div style={{ fontSize: 11, color: "#64748b", marginTop: 3, fontFamily: F }}>
                        {c.document_count} {c.document_count === 1 ? "documento" : "documentos"}
                        {scopeOrgId && ` · ${c.assignee_count} com acesso`}
                        {c.retention_months ? ` · guarda de ${c.retention_months >= 12 ? `${Math.round(c.retention_months / 12)} ano${c.retention_months >= 24 ? "s" : ""}` : `${c.retention_months} meses`}` : " · sem prazo de guarda"}
                      </div>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
                      {scopeOrgId && canManage && (
                        <button onClick={() => abrirDesignacoes(c)} style={{ display: "flex", alignItems: "center", gap: 4, padding: "5px 10px", borderRadius: 7, border: "1px solid #e2e8f0", background: "white", cursor: "pointer", fontSize: 11, fontWeight: 600, color: "#6366f1", fontFamily: F }} title="Quem tem acesso a este cliente"><ShieldCheck size={12} /> Acesso</button>
                      )}
                      {canManage && <>
                        <button onClick={() => openEdit(c)} style={{ width: 28, height: 28, borderRadius: 6, border: "1px solid #e2e8f0", background: "white", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }} title="Editar"><Edit3 size={12} color="#6366f1" /></button>
                        <button onClick={() => setDelC(c.id)} style={{ width: 28, height: 28, borderRadius: 6, border: "1px solid #e2e8f0", background: "white", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }} title="Excluir"><Trash2 size={12} color="#ef4444" /></button>
                      </>}
                    </div>
                  </div>
                  {c.notes && <div style={{ marginTop: 8, padding: "7px 10px", background: "#f8fafc", borderRadius: 5, fontSize: 11, color: "#475569", fontFamily: F }}>{c.notes}</div>}
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {aba === "retencao" && (
        <>
          <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 11, padding: "13px 16px", marginBottom: 14, display: "flex", gap: 10 }}>
            <Info size={15} color="#6366f1" style={{ flexShrink: 0, marginTop: 1 }} />
            <div style={{ fontSize: 11.5, color: "#475569", fontFamily: F, lineHeight: 1.6 }}>
              Aqui ficam os documentos que passaram do prazo de guarda do cliente. Nada é apagado sozinho: um contrato pode estar vencido para a política de guarda e ainda ser prova em processo em curso.
            </div>
          </div>

          {vencidos.length === 0 ? (
            <div style={{ background: "white", borderRadius: 13, border: "1px dashed #cbd5e1", padding: "36px 28px", textAlign: "center" }}>
              <CheckCircle size={22} color="#16a34a" style={{ marginBottom: 10 }} />
              <div style={{ fontSize: 13.5, fontWeight: 700, color: "#0f172a", fontFamily: F }}>Nenhum documento vencido</div>
              <p style={{ fontSize: 11.5, color: "#64748b", margin: "5px 0 0", fontFamily: F }}>Só entram nesta fila os clientes com prazo de guarda definido.</p>
            </div>
          ) : (
            <>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {vencidos.map(v => (
                  <label key={v.document_id} style={{ display: "flex", alignItems: "center", gap: 11, background: "white", borderRadius: 10, border: `1px solid ${marcados[v.document_id] ? "#fca5a5" : "#e2e8f0"}`, padding: "13px 16px", cursor: "pointer" }}>
                    <input type="checkbox" checked={!!marcados[v.document_id]} onChange={e => setMarcados({ ...marcados, [v.document_id]: e.target.checked })} style={{ width: 15, height: 15, accentColor: "#ef4444", cursor: "pointer" }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 12.5, fontWeight: 600, color: "#0f172a", fontFamily: F, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{v.filename}</div>
                      <div style={{ fontSize: 10.5, color: "#64748b", marginTop: 2, fontFamily: F }}>{v.client_name} · enviado em {formatDate(v.uploaded_at)}</div>
                    </div>
                    <span style={{ fontSize: 10.5, fontWeight: 700, color: "#dc2626", background: "#fef2f2", padding: "3px 9px", borderRadius: 20, fontFamily: F, flexShrink: 0 }}>venceu há {v.days_overdue} {v.days_overdue === 1 ? "dia" : "dias"}</span>
                  </label>
                ))}
              </div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 14, gap: 10 }}>
                <button onClick={() => setMarcados(marcadosCount === vencidos.length ? {} : Object.fromEntries(vencidos.map(v => [v.document_id, true])))} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 11.5, fontWeight: 600, color: "#6366f1", fontFamily: F }}>
                  {marcadosCount === vencidos.length ? "Desmarcar todos" : "Marcar todos"}
                </button>
                <button onClick={() => setConfirmaExpurgo(true)} disabled={!marcadosCount} style={{ padding: "9px 18px", borderRadius: 9, border: "none", cursor: marcadosCount ? "pointer" : "default", background: marcadosCount ? "#ef4444" : "#f1f5f9", color: marcadosCount ? "white" : "#94a3b8", fontWeight: 600, fontSize: 12, fontFamily: F, display: "flex", alignItems: "center", gap: 6 }}>
                  <Trash2 size={13} /> Excluir {marcadosCount || ""} {marcadosCount === 1 ? "documento" : "documentos"}
                </button>
              </div>
            </>
          )}
        </>
      )}

      {aba === "auditoria" && (
        <>
          <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 11, padding: "13px 16px", marginBottom: 14, display: "flex", gap: 10 }}>
            <Info size={15} color="#6366f1" style={{ flexShrink: 0, marginTop: 1 }} />
            <div style={{ fontSize: 11.5, color: "#475569", fontFamily: F, lineHeight: 1.6 }}>
              {scopeOrgId
                ? "Quem leu, baixou ou excluiu o quê. O registro fica mesmo depois que o documento é apagado, que é o caso em que a auditoria mais precisa dele."
                : "Seu próprio histórico de acessos. Fica registrado mesmo depois que o documento é apagado."}
            </div>
          </div>

          {logs.length === 0 ? (
            <div style={{ background: "white", borderRadius: 13, border: "1px dashed #cbd5e1", padding: "36px 28px", textAlign: "center" }}>
              <div style={{ fontSize: 13.5, fontWeight: 700, color: "#0f172a", fontFamily: F }}>Nenhum acesso registrado ainda</div>
            </div>
          ) : (
            <div style={{ background: "white", borderRadius: 13, border: "1px solid #e2e8f0", overflow: "hidden" }}>
              {logs.map((l, i) => {
                const meta = ACTION_META[l.action] || { label: l.action, color: "#64748b", bg: "#f8fafc" };
                return (
                  <div key={l.id} style={{ display: "flex", alignItems: "center", gap: 11, padding: "12px 16px", borderTop: i ? "1px solid #f1f5f9" : "none" }}>
                    <span style={{ fontSize: 10, fontWeight: 700, color: meta.color, background: meta.bg, padding: "3px 9px", borderRadius: 20, fontFamily: F, flexShrink: 0, minWidth: 118, textAlign: "center" }}>{meta.label}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 12, color: "#0f172a", fontFamily: F, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{l.detail || "(sem descrição)"}</div>
                      <div style={{ fontSize: 10.5, color: "#94a3b8", marginTop: 2, fontFamily: F }}>
                        {l.user_email || "usuário removido"}{l.client_name ? ` · ${l.client_name}` : ""}
                      </div>
                    </div>
                    <span style={{ fontSize: 10.5, color: "#94a3b8", fontFamily: F, flexShrink: 0 }}>{formatDate(l.created_at)}</span>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      <Modal open={!!detalhe} onClose={() => setDetalhe(null)} title={detalhe ? `Acesso a ${detalhe.name}` : ""} width={460}>
        <p style={{ fontSize: 12, color: "#64748b", margin: "0 0 14px", fontFamily: F, lineHeight: 1.6 }}>
          Só quem estiver nesta lista enxerga os contratos deste cliente. Responsáveis pela equipe enxergam sempre.
        </p>
        <div style={{ display: "flex", gap: 7, marginBottom: 14 }}>
          <input value={novoEmail} onChange={e => setNovoEmail(e.target.value)} onKeyDown={e => e.key === "Enter" && designar()} placeholder="email do advogado" style={{ flex: 1, padding: "9px 11px", borderRadius: 9, border: "1px solid #d1d5db", fontSize: 12, fontFamily: F, outline: "none" }} />
          <button onClick={designar} style={{ padding: "9px 15px", borderRadius: 9, border: "none", background: "linear-gradient(135deg, #6366f1, #8b5cf6)", color: "white", cursor: "pointer", fontSize: 12, fontWeight: 600, fontFamily: F, display: "flex", alignItems: "center", gap: 5 }}><UserPlus size={13} /> Dar acesso</button>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {designados.length === 0 && <div style={{ fontSize: 12, color: "#94a3b8", fontFamily: F, textAlign: "center", padding: 14 }}>Ninguém designado ainda.</div>}
          {designados.map(d => (
            <div key={d.user_id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, padding: "9px 12px", background: "#f8fafc", borderRadius: 8 }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: "#0f172a", fontFamily: F }}>{d.full_name || d.email}</div>
                {d.full_name && <div style={{ fontSize: 10.5, color: "#94a3b8", fontFamily: F }}>{d.email}</div>}
              </div>
              <button onClick={() => retirar(d.user_id)} style={{ background: "none", border: "none", cursor: "pointer", padding: 3 }} title="Retirar acesso"><X size={14} color="#ef4444" /></button>
            </div>
          ))}
        </div>
      </Modal>

      <Modal open={!!delC} onClose={() => setDelC(null)} title="Excluir cliente" width={400}>
        <p style={{ fontSize: 13, color: "#1e293b", margin: "0 0 8px", fontFamily: F }}>Excluir o cadastro deste cliente?</p>
        <p style={{ fontSize: 12, color: "#64748b", margin: "0 0 16px", fontFamily: F, lineHeight: 1.6 }}>Os contratos não são apagados: eles ficam sem cliente e voltam a ficar visíveis a toda a equipe.</p>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button onClick={() => setDelC(null)} style={{ padding: "8px 16px", borderRadius: 9, border: "1px solid #e2e8f0", background: "white", cursor: "pointer", fontSize: 12, fontWeight: 600, color: "#64748b", fontFamily: F }}>Cancelar</button>
          <button onClick={() => remover(delC)} style={{ padding: "8px 16px", borderRadius: 9, border: "none", background: "#ef4444", cursor: "pointer", fontSize: 12, fontWeight: 600, color: "white", fontFamily: F }}>Excluir</button>
        </div>
      </Modal>

      <Modal open={confirmaExpurgo} onClose={() => setConfirmaExpurgo(false)} title="Confirmar exclusão" width={420}>
        <div style={{ display: "flex", alignItems: "flex-start", gap: 12, marginBottom: 16 }}>
          <div style={{ width: 36, height: 36, borderRadius: 9, background: "#fef2f2", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}><AlertTriangle size={18} color="#ef4444" /></div>
          <div>
            <p style={{ fontSize: 13, color: "#1e293b", margin: "0 0 4px", fontWeight: 600, fontFamily: F }}>Excluir {marcadosCount} {marcadosCount === 1 ? "documento" : "documentos"}?</p>
            <p style={{ fontSize: 12, color: "#64748b", margin: 0, fontFamily: F, lineHeight: 1.5 }}>O arquivo e a análise são removidos em definitivo. A exclusão fica registrada no log de acesso.</p>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button onClick={() => setConfirmaExpurgo(false)} style={{ padding: "8px 16px", borderRadius: 9, border: "1px solid #e2e8f0", background: "white", cursor: "pointer", fontSize: 12, fontWeight: 600, color: "#64748b", fontFamily: F }}>Cancelar</button>
          <button onClick={expurgar} style={{ padding: "8px 16px", borderRadius: 9, border: "none", background: "#ef4444", cursor: "pointer", fontSize: 12, fontWeight: 600, color: "white", fontFamily: F }}>Excluir em definitivo</button>
        </div>
      </Modal>
    </div>
  );
};

// Areas do direito. A ordem aqui e a ordem na tela: primeiro o que vale para
// qualquer contrato, depois os conjuntos que so ligam quando o contrato e daquele
// tipo.
const AREA_META = {
  geral: { label: "Estrutura do contrato", hint: "Valem para qualquer contrato" },
  protecao_de_dados: { label: "Proteção de dados", hint: "LGPD, Lei 13.709/2018" },
  civil: { label: "Civil", hint: "Código Civil, Lei 10.406/2002" },
  trabalhista: { label: "Trabalhista", hint: "CLT, Decreto-Lei 5.452/1943" },
  consumidor: { label: "Consumidor", hint: "CDC, Lei 8.078/1990" },
  anticorrupcao: { label: "Anticorrupção", hint: "Lei 12.846/2013" },
  internet: { label: "Internet", hint: "Marco Civil, Lei 12.965/2014" },
  licitacoes: { label: "Licitações", hint: "Lei 14.133/2021" },
  locacao: { label: "Locação", hint: "Lei do Inquilinato, Lei 8.245/1991" },
  societario: { label: "Societário", hint: "Lei das S.A., Lei 6.404/1976" },
  propriedade_industrial: { label: "Propriedade industrial", hint: "Lei 9.279/1996" },
};

const AREA_ORDER = Object.keys(AREA_META);

const areaLabel = (c) => AREA_META[c]?.label || "Outras";

const RulesManager = ({ showToast, organizationId = null, canManage = true, embedded = false }) => {
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState(null);
  const [fd, setFd] = useState({ name: "", description: "", severity: "medium", criteria: "", category: "geral" });
  const [areasFechadas, setAreasFechadas] = useState({});
  const [areaSalvando, setAreaSalvando] = useState(null);
  const [delC, setDelC] = useState(null);
  const [saving, setSaving] = useState(false);
  const [introDismissed, setIntroDismissed] = useState(
    () => localStorage.getItem("rules_intro_dismissed") === "1"
  );

  const dismissIntro = () => {
    localStorage.setItem("rules_intro_dismissed", "1");
    setIntroDismissed(true);
  };

  const fetchRules = useCallback(async () => {
    try {
      const data = await api.listRules(false, organizationId);
      setRules(data || []);
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      setLoading(false);
    }
  }, [showToast, organizationId]);

  useEffect(() => { fetchRules(); }, [fetchRules]);

  const openNew = () => { setFd({ name: "", description: "", severity: "medium", criteria: "", category: "geral" }); setEditId(null); setShowForm(true); };
  const openEdit = (r) => { setFd({ name: r.name, description: r.description || "", severity: r.severity, criteria: r.criteria, category: r.category || "geral" }); setEditId(r.id); setShowForm(true); };

  const save = async () => {
    if (!fd.name || !fd.criteria) { showToast("Nome e critério são obrigatórios", "error"); return; }
    setSaving(true);
    try {
      if (editId) {
        const updated = await api.updateRule(editId, fd);
        setRules(rules.map(r => r.id === editId ? updated : r));
        showToast("Regra atualizada!", "success");
      } else {
        const created = await api.createRule(organizationId ? { ...fd, organization_id: organizationId } : fd);
        setRules([...rules, created]);
        showToast("Regra criada!", "success");
      }
      setShowForm(false);
      setEditId(null);
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      setSaving(false);
    }
  };

  // Agrupa por area e ordena pela ordem de AREA_META, deixando areas
  // desconhecidas no fim em vez de as esconder.
  const grupos = useMemo(() => {
    const mapa = new Map();
    for (const regra of rules) {
      const cat = regra.category || "geral";
      if (!mapa.has(cat)) mapa.set(cat, []);
      mapa.get(cat).push(regra);
    }
    return [...mapa.entries()].sort((a, b) => {
      const ia = AREA_ORDER.indexOf(a[0]);
      const ib = AREA_ORDER.indexOf(b[0]);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    });
  }, [rules]);

  const toggleArea = async (categoria, ativar) => {
    setAreaSalvando(categoria);
    try {
      const atualizadas = await api.toggleCategory(categoria, ativar, organizationId);
      const porId = new Map(atualizadas.map(r => [r.id, r]));
      setRules(rules.map(r => porId.get(r.id) || r));
      showToast(
        `${areaLabel(categoria)}: ${atualizadas.length} ${atualizadas.length === 1 ? "regra" : "regras"} ${ativar ? "ativadas" : "desativadas"}`,
        "success",
      );
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      setAreaSalvando(null);
    }
  };

  const del = async (id) => {
    try {
      await api.deleteRule(id);
      setRules(rules.filter(r => r.id !== id));
      setDelC(null);
      showToast("Regra excluída.", "success");
    } catch (err) {
      showToast(err.message, "error");
    }
  };

  const toggle = async (id) => {
    try {
      const updated = await api.toggleRule(id, organizationId);
      setRules(rules.map(r => r.id === id ? updated : r));
    } catch (err) {
      showToast(err.message, "error");
    }
  };

  if (loading) return <div style={{ display: "flex", justifyContent: "center", padding: 60 }}><Loader2 size={28} color="#6366f1" style={{ animation: "spin 1s linear infinite" }} /></div>;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: embedded ? 14 : 20, flexWrap: "wrap", gap: 10 }}>
        <div>
          {embedded
            ? <h3 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: 0, fontFamily: F }}>Regras da equipe</h3>
            : <h1 style={{ fontSize: 24, fontWeight: 800, color: "#0f172a", fontFamily: F, letterSpacing: "-0.03em", margin: 0 }}>Minhas Regras</h1>}
          <p style={{ color: "#64748b", fontSize: embedded ? 11 : 13, marginTop: 3, fontFamily: F }}>
            {embedded
              ? "Valem para os documentos analisados por esta equipe"
              : "Valem para os documentos que você analisa fora de uma equipe"}
            {" · "}{rules.filter(r => r.is_active).length} ativas de {rules.length}
          </p>
        </div>
        {canManage && (
          <button onClick={() => showForm ? setShowForm(false) : openNew()} style={{ display: "flex", alignItems: "center", gap: 5, padding: "9px 16px", borderRadius: 9, border: "none", cursor: "pointer", fontWeight: 600, fontSize: 12, background: showForm ? "#f1f5f9" : "linear-gradient(135deg, #6366f1, #8b5cf6)", color: showForm ? "#64748b" : "white", fontFamily: F }}>{showForm ? <><X size={15} /> Cancelar</> : <><Plus size={15} /> Nova Regra</>}</button>
        )}
      </div>
      {!introDismissed && !showForm && (
        <RulesIntro
          globalCount={rules.filter(r => r.scope === "global").length}
          ownCount={rules.filter(r => r.scope !== "global").length}
          isTeam={!!organizationId}
          onDismiss={dismissIntro}
        />
      )}
      {showForm && (
        <div style={{ background: "white", borderRadius: 13, border: "1px solid #e2e8f0", padding: "22px", marginBottom: 18, animation: "fadeSlideUp 0.3s ease" }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: "0 0 16px", fontFamily: F }}>{editId ? "Editar Regra" : "Criar Nova Regra"}</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
            <div><label style={{ display: "block", fontSize: 11, fontWeight: 600, color: "#374151", marginBottom: 4, fontFamily: F }}>Nome *</label><input value={fd.name} onChange={e => setFd({...fd, name: e.target.value})} placeholder="Ex: Foro em Pernambuco" style={{ width: "100%", padding: "9px 11px", borderRadius: 9, border: "1px solid #d1d5db", fontSize: 12, fontFamily: F, outline: "none", boxSizing: "border-box" }} /></div>
            <div><label style={{ display: "block", fontSize: 11, fontWeight: 600, color: "#374151", marginBottom: 4, fontFamily: F }}>Severidade *</label><select value={fd.severity} onChange={e => setFd({...fd, severity: e.target.value})} style={{ width: "100%", padding: "9px 11px", borderRadius: 9, border: "1px solid #d1d5db", fontSize: 12, fontFamily: F, outline: "none", background: "white", boxSizing: "border-box" }}><option value="high">Alta</option><option value="medium">Média</option><option value="low">Baixa</option></select></div>
          </div>
          <div style={{ marginBottom: 12 }}><label style={{ display: "block", fontSize: 11, fontWeight: 600, color: "#374151", marginBottom: 4, fontFamily: F }}>Área do direito</label><select value={fd.category} onChange={e => setFd({...fd, category: e.target.value})} style={{ width: "100%", padding: "9px 11px", borderRadius: 9, border: "1px solid #d1d5db", fontSize: 12, fontFamily: F, outline: "none", background: "white", boxSizing: "border-box" }}>{AREA_ORDER.map(c => <option key={c} value={c}>{AREA_META[c].label}</option>)}</select></div>
          <div style={{ marginBottom: 12 }}><label style={{ display: "block", fontSize: 11, fontWeight: 600, color: "#374151", marginBottom: 4, fontFamily: F }}>Descrição</label><input value={fd.description} onChange={e => setFd({...fd, description: e.target.value})} placeholder="Descrição breve" style={{ width: "100%", padding: "9px 11px", borderRadius: 9, border: "1px solid #d1d5db", fontSize: 12, fontFamily: F, outline: "none", boxSizing: "border-box" }} /></div>
          <div style={{ marginBottom: 16 }}><label style={{ display: "block", fontSize: 11, fontWeight: 600, color: "#374151", marginBottom: 4, fontFamily: F }}>Critério de Verificação *</label><textarea value={fd.criteria} onChange={e => setFd({...fd, criteria: e.target.value})} rows={3} placeholder="Descreva o que a IA deve verificar..." style={{ width: "100%", padding: "9px 11px", borderRadius: 9, border: "1px solid #d1d5db", fontSize: 12, fontFamily: F, outline: "none", resize: "vertical", boxSizing: "border-box" }} /></div>
          <button onClick={save} disabled={saving} style={{ padding: "9px 20px", borderRadius: 9, border: "none", cursor: "pointer", background: "linear-gradient(135deg, #6366f1, #8b5cf6)", color: "white", fontWeight: 600, fontSize: 12, fontFamily: F, opacity: saving ? 0.7 : 1, display: "flex", alignItems: "center", gap: 6 }}>{saving && <Loader2 size={13} style={{ animation: "spin 1s linear infinite" }} />}{editId ? "Salvar Alterações" : "Criar Regra"}</button>
        </div>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {grupos.map(([categoria, doGrupo]) => {
        const ativasNaArea = doGrupo.filter(r => r.is_active).length;
        const fechada = !!areasFechadas[categoria];
        const meta = AREA_META[categoria];
        return (
        <div key={categoria}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "0 2px 8px", borderBottom: "1px solid #e2e8f0", marginBottom: 10 }}>
            <button onClick={() => setAreasFechadas({ ...areasFechadas, [categoria]: !fechada })} style={{ display: "flex", alignItems: "center", gap: 6, background: "none", border: "none", cursor: "pointer", padding: 0, flex: 1, minWidth: 0, textAlign: "left" }}>
              {fechada ? <ChevronRight size={14} color="#94a3b8" /> : <ChevronDown size={14} color="#94a3b8" />}
              <span style={{ fontSize: 12, fontWeight: 700, color: "#0f172a", fontFamily: F }}>{areaLabel(categoria)}</span>
              {meta && <span style={{ fontSize: 10, color: "#94a3b8", fontFamily: F }}>{meta.hint}</span>}
              <span style={{ fontSize: 10, fontWeight: 600, color: ativasNaArea ? "#6366f1" : "#94a3b8", background: ativasNaArea ? "#eef2ff" : "#f1f5f9", padding: "2px 8px", borderRadius: 20, fontFamily: F }}>{ativasNaArea} de {doGrupo.length}</span>
            </button>
            {canManage && (
              <button onClick={() => toggleArea(categoria, ativasNaArea < doGrupo.length)} disabled={areaSalvando === categoria} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 11, fontWeight: 600, color: "#6366f1", fontFamily: F, padding: "2px 4px", flexShrink: 0, opacity: areaSalvando === categoria ? 0.5 : 1 }} title={ativasNaArea < doGrupo.length ? "Ativar todas as regras desta área" : "Desativar todas as regras desta área"}>
                {ativasNaArea < doGrupo.length ? "Ativar área" : "Desativar área"}
              </button>
            )}
          </div>
          {!fechada && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {doGrupo.map((rule, i) => { const sev = getSeverityStyle(rule.severity); return (
          <div key={rule.id} style={{ background: "white", borderRadius: 11, border: "1px solid #e2e8f0", padding: "16px 18px", opacity: rule.is_active ? 1 : 0.55, transition: "all 0.3s", animation: `fadeSlideUp 0.4s ease ${i*0.05}s both` }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1, minWidth: 0 }}>
                <span style={{ fontSize: 10, fontWeight: 700, color: sev.color, background: sev.bg, padding: "2px 9px", borderRadius: 20, border: `1px solid ${sev.border}`, fontFamily: F, flexShrink: 0 }}>{sev.label}</span>
                {SCOPE_META[rule.scope] && (
                  <span style={{ fontSize: 10, fontWeight: 600, color: SCOPE_META[rule.scope].color, background: SCOPE_META[rule.scope].bg, padding: "2px 8px", borderRadius: 20, border: `1px solid ${SCOPE_META[rule.scope].border}`, fontFamily: F, flexShrink: 0 }} title={SCOPE_META[rule.scope].hint}>{SCOPE_META[rule.scope].label}</span>
                )}
                <div style={{ minWidth: 0 }}><div style={{ fontSize: 13, fontWeight: 700, color: "#0f172a", fontFamily: F }}>{rule.name}</div><div style={{ fontSize: 11, color: "#64748b", marginTop: 1, fontFamily: F, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{rule.description}</div></div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
                {rule.editable !== false && canManage && (
                  <>
                    <button onClick={() => openEdit(rule)} style={{ width: 28, height: 28, borderRadius: 6, border: "1px solid #e2e8f0", background: "white", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }} title="Editar"><Edit3 size={12} color="#6366f1" /></button>
                    <button onClick={() => setDelC(rule.id)} style={{ width: 28, height: 28, borderRadius: 6, border: "1px solid #e2e8f0", background: "white", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }} title="Excluir"><Trash2 size={12} color="#ef4444" /></button>
                  </>
                )}
                <button onClick={() => canManage && toggle(rule.id)} disabled={!canManage} style={{ background: "none", border: "none", cursor: canManage ? "pointer" : "default", padding: 2, opacity: canManage ? 1 : 0.5 }} title={canManage ? (rule.is_active ? (organizationId ? "Desativar para a equipe" : "Desativar para mim") : (organizationId ? "Ativar para a equipe" : "Ativar para mim")) : "Somente responsáveis pela equipe podem alterar"}>{rule.is_active ? <ToggleRight size={24} color="#6366f1" /> : <ToggleLeft size={24} color="#cbd5e1" />}</button>
              </div>
            </div>
            <div style={{ marginTop: 8, padding: "7px 10px", background: "#f8fafc", borderRadius: 5 }}><div style={{ fontSize: 10, fontWeight: 600, color: "#94a3b8", marginBottom: 2, fontFamily: F }}>Critério:</div><div style={{ fontSize: 11, color: "#475569", fontFamily: F }}>{rule.criteria}</div></div>
          </div>
        ); })}
          </div>
          )}
        </div>
        );
        })}
      </div>
      <Modal open={!!delC} onClose={() => setDelC(null)} title="Excluir regra" width={380}>
        <p style={{ fontSize: 13, color: "#1e293b", margin: "0 0 16px", fontFamily: F }}>Tem certeza? A regra será removida permanentemente.</p>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button onClick={() => setDelC(null)} style={{ padding: "8px 16px", borderRadius: 9, border: "1px solid #e2e8f0", background: "white", cursor: "pointer", fontSize: 12, fontWeight: 600, color: "#64748b", fontFamily: F }}>Cancelar</button>
          <button onClick={() => del(delC)} style={{ padding: "8px 16px", borderRadius: 9, border: "none", background: "#ef4444", cursor: "pointer", fontSize: 12, fontWeight: 600, color: "white", fontFamily: F }}>Excluir</button>
        </div>
      </Modal>
    </div>
  );
};

// Aba "Regras": escopo pessoal. As regras de equipe ficam na aba Equipe,
// junto do restante da configuracao da organizacao.
const RulesPage = ({ showToast, scopeOrgId }) => (
  <RulesManager showToast={showToast} organizationId={scopeOrgId || null} />
);

// ── Team / Organizations Page ──
const ROLE_META = {
  owner: { label: "Proprietário", color: "#7c3aed", bg: "#f5f3ff", border: "#ddd6fe", icon: Crown },
  admin: { label: "Administrador", color: "#2563eb", bg: "#eff6ff", border: "#bfdbfe", icon: Shield },
  member: { label: "Membro", color: "#059669", bg: "#f0fdf4", border: "#bbf7d0", icon: User },
};

const TeamPage = ({ showToast, user, onOrgDeleted, onOrgsChanged }) => {
  const [orgs, setOrgs] = useState([]);
  const [selectedOrg, setSelectedOrg] = useState(null);
  const [orgDetail, setOrgDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [showAddMember, setShowAddMember] = useState(false);
  const [createForm, setCreateForm] = useState({ name: "", slug: "", cnpj: "" });
  const [addForm, setAddForm] = useState({ email: "", role: "member" });
  const [saving, setSaving] = useState(false);
  const [editRole, setEditRole] = useState(null); // { userId, currentRole }
  const [confirmRemove, setConfirmRemove] = useState(null); // userId
  const [confirmDeleteOrg, setConfirmDeleteOrg] = useState(false);
  const [deletingOrg, setDeletingOrg] = useState(false);

  const fetchOrgs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listOrganizations();
      setOrgs(data || []);
    } catch {
      showToast("Erro ao carregar organizações", "error");
    } finally { setLoading(false); }
  }, [showToast]);

  useEffect(() => { fetchOrgs(); }, [fetchOrgs]);

  const loadOrgDetail = async (org) => {
    setSelectedOrg(org);
    setDetailLoading(true);
    try {
      const data = await api.getOrganization(org.id);
      setOrgDetail(data);
    } catch (err) {
      showToast(err.message || "Erro ao carregar detalhes", "error");
    } finally { setDetailLoading(false); }
  };

  const handleCreateOrg = async () => {
    if (!createForm.name || !createForm.slug) { showToast("Nome e slug são obrigatórios", "error"); return; }
    setSaving(true);
    try {
      await api.createOrganization(createForm);
      showToast("Equipe criada. Já aparece no seletor de escopo.", "success");
      setShowCreate(false);
      setCreateForm({ name: "", slug: "", cnpj: "" });
      fetchOrgs();
      onOrgsChanged?.();
    } catch (err) {
      showToast(err.message || "Erro ao criar organização", "error");
    } finally { setSaving(false); }
  };

  const handleAddMember = async () => {
    if (!addForm.email) { showToast("Email é obrigatório", "error"); return; }
    setSaving(true);
    try {
      await api.addOrgMember(selectedOrg.id, addForm.email, addForm.role);
      showToast("Membro adicionado com sucesso!", "success");
      setShowAddMember(false);
      setAddForm({ email: "", role: "member" });
      loadOrgDetail(selectedOrg);
      onOrgsChanged?.();
    } catch (err) {
      showToast(err.message || "Erro ao adicionar membro", "error");
    } finally { setSaving(false); }
  };

  const handleChangeRole = async (userId, newRole) => {
    try {
      await api.updateOrgMemberRole(selectedOrg.id, userId, newRole);
      showToast("Papel atualizado!", "success");
      setEditRole(null);
      loadOrgDetail(selectedOrg);
      onOrgsChanged?.();
    } catch (err) {
      showToast(err.message || "Erro ao atualizar papel", "error");
    }
  };

  const handleDeleteOrg = async () => {
    setDeletingOrg(true);
    try {
      await api.deleteOrganization(selectedOrg.id);
      showToast("Equipe excluída.", "success");
      setConfirmDeleteOrg(false);
      onOrgDeleted?.(selectedOrg.id);
      setSelectedOrg(null);
      setOrgDetail(null);
      fetchOrgs();
    } catch (err) {
      showToast(err.message || "Erro ao excluir equipe", "error");
    } finally {
      setDeletingOrg(false);
    }
  };

  const handleRemoveMember = async (userId) => {
    try {
      await api.removeOrgMember(selectedOrg.id, userId);
      showToast("Membro removido!", "success");
      setConfirmRemove(null);
      loadOrgDetail(selectedOrg);
      onOrgsChanged?.();
    } catch (err) {
      showToast(err.message || "Erro ao remover membro", "error");
    }
  };

  // ── Detail view ──
  if (selectedOrg) {
    const members = orgDetail?.members || [];
    const myMembership = members.find(m => m.user_email === user?.email);
    const isAdmin = myMembership && (myMembership.role === "owner" || myMembership.role === "admin");
    const isOwner = myMembership && myMembership.role === "owner";

    return (
      <div>
        <button onClick={() => { setSelectedOrg(null); setOrgDetail(null); }} style={{ display: "flex", alignItems: "center", gap: 5, background: "none", border: "none", cursor: "pointer", color: "#6366f1", fontWeight: 600, fontSize: 12, marginBottom: 18, padding: 0, fontFamily: F }}><ArrowLeft size={15} /> Voltar</button>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24, flexWrap: "wrap", gap: 12 }}>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 800, color: "#0f172a", fontFamily: F, letterSpacing: "-0.03em", margin: 0 }}>{selectedOrg.name}</h1>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6, flexWrap: "wrap" }}>
              <span style={{ fontSize: 11, color: "#94a3b8", fontFamily: F, background: "#f1f5f9", padding: "2px 8px", borderRadius: 4 }}>/{selectedOrg.slug}</span>
              {selectedOrg.cnpj && <span style={{ fontSize: 11, color: "#64748b", fontFamily: F }}>CNPJ: {selectedOrg.cnpj}</span>}
              <span style={{ fontSize: 10, fontWeight: 600, color: selectedOrg.is_active ? "#16a34a" : "#dc2626", background: selectedOrg.is_active ? "#f0fdf4" : "#fef2f2", padding: "2px 8px", borderRadius: 10 }}>{selectedOrg.is_active ? "Ativa" : "Inativa"}</span>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          {isOwner && (
            <button onClick={() => setConfirmDeleteOrg(true)} style={{ display: "inline-flex", alignItems: "center", gap: 6, background: "white", color: "#dc2626", padding: "9px 15px", borderRadius: 10, border: "1px solid #fecaca", cursor: "pointer", fontSize: 13, fontWeight: 600, fontFamily: F }}>
              <Trash2 size={14} /> Excluir equipe
            </button>
          )}
          {isAdmin && (
            <button onClick={() => setShowAddMember(true)} style={{ display: "inline-flex", alignItems: "center", gap: 6, background: "linear-gradient(135deg, #6366f1, #8b5cf6)", color: "white", padding: "9px 18px", borderRadius: 10, border: "none", cursor: "pointer", fontSize: 13, fontWeight: 600, fontFamily: F }}>
              <UserPlus size={15} /> Adicionar membro
            </button>
          )}
          </div>
        </div>

        {/* Regras da equipe */}
        <div style={{ background: "white", borderRadius: 14, border: "1px solid #e2e8f0", padding: "18px 22px", marginBottom: 18 }}>
          <RulesManager
            showToast={showToast}
            organizationId={selectedOrg.id}
            canManage={isAdmin}
            embedded
          />
        </div>

        {/* Members List */}
        <div style={{ background: "white", borderRadius: 14, border: "1px solid #e2e8f0", overflow: "hidden" }}>
          <div style={{ padding: "16px 22px", borderBottom: "1px solid #f1f5f9", display: "flex", alignItems: "center", gap: 10 }}>
            <Users size={16} color="#6366f1" />
            <h3 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: 0, fontFamily: F }}>Membros ({members.length})</h3>
          </div>

          {detailLoading ? (
            <div style={{ padding: 40, textAlign: "center" }}><Loader2 size={24} color="#6366f1" style={{ animation: "spin 1s linear infinite" }} /></div>
          ) : members.length === 0 ? (
            <div style={{ padding: 40, textAlign: "center", color: "#94a3b8", fontSize: 13 }}>Nenhum membro encontrado</div>
          ) : members.map((member, i) => {
            const rm = ROLE_META[member.role] || ROLE_META.member;
            const RoleIcon = rm.icon;
            const isMe = member.user_email === user?.email;
            return (
              <div key={member.id} style={{ display: "flex", alignItems: "center", gap: 14, padding: "14px 22px", borderBottom: i < members.length - 1 ? "1px solid #f8fafc" : "none" }}>
                <div style={{ width: 40, height: 40, borderRadius: 10, background: rm.bg, border: `1px solid ${rm.border}`, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  <RoleIcon size={18} color={rm.color} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 13, fontWeight: 700, color: "#0f172a", fontFamily: F }}>{member.user_name || "Sem nome"}</span>
                    {isMe && <span style={{ fontSize: 9, fontWeight: 700, color: "#6366f1", background: "#eef2ff", padding: "1px 6px", borderRadius: 6, fontFamily: F }}>VOCÊ</span>}
                  </div>
                  <div style={{ fontSize: 11, color: "#94a3b8", fontFamily: F }}>{member.user_email}</div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  {editRole && editRole.userId === member.user_id ? (
                    <div style={{ display: "flex", gap: 4 }}>
                      {["member", "admin", "owner"].map(r => (
                        <button key={r} onClick={() => handleChangeRole(member.user_id, r)} style={{ fontSize: 10, fontWeight: 700, padding: "4px 10px", borderRadius: 6, border: `1px solid ${ROLE_META[r].border}`, background: r === editRole.currentRole ? ROLE_META[r].bg : "white", color: ROLE_META[r].color, cursor: "pointer", fontFamily: F }}>{ROLE_META[r].label}</button>
                      ))}
                      <button onClick={() => setEditRole(null)} style={{ fontSize: 10, padding: "4px 8px", borderRadius: 6, border: "1px solid #e2e8f0", background: "white", cursor: "pointer", color: "#94a3b8", fontFamily: F }}>
                        <X size={12} />
                      </button>
                    </div>
                  ) : (
                    <span style={{ fontSize: 10, fontWeight: 700, color: rm.color, background: rm.bg, padding: "3px 10px", borderRadius: 20, border: `1px solid ${rm.border}`, fontFamily: F }}>{rm.label}</span>
                  )}
                  {isAdmin && !isMe && !editRole && (
                    <div style={{ display: "flex", gap: 4 }}>
                      <button onClick={() => setEditRole({ userId: member.user_id, currentRole: member.role })} style={{ width: 28, height: 28, borderRadius: 6, border: "1px solid #e2e8f0", background: "white", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }} title="Alterar papel"><Edit3 size={12} color="#64748b" /></button>
                      <button onClick={() => setConfirmRemove(member.user_id)} style={{ width: 28, height: 28, borderRadius: 6, border: "1px solid #fecaca", background: "#fef2f2", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }} title="Remover membro"><Trash2 size={12} color="#ef4444" /></button>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Add Member Modal */}
        <Modal open={showAddMember} onClose={() => setShowAddMember(false)} title="Adicionar membro" width={420}>
          <label style={{ fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 5, display: "block", fontFamily: F }}>Email do usuário *</label>
          <input value={addForm.email} onChange={e => setAddForm({ ...addForm, email: e.target.value })} placeholder="usuario@email.com" style={{ width: "100%", padding: "10px 14px", borderRadius: 10, border: "1px solid #d1d5db", fontSize: 13, fontFamily: F, outline: "none", boxSizing: "border-box", marginBottom: 14 }} />
          <label style={{ fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 5, display: "block", fontFamily: F }}>Papel</label>
          <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
            {["member", "admin"].map(r => (
              <button key={r} onClick={() => setAddForm({ ...addForm, role: r })} style={{ flex: 1, padding: "10px", borderRadius: 10, border: `2px solid ${addForm.role === r ? ROLE_META[r].color : "#e2e8f0"}`, background: addForm.role === r ? ROLE_META[r].bg : "white", cursor: "pointer", textAlign: "center", fontFamily: F, transition: "all 0.15s" }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: addForm.role === r ? ROLE_META[r].color : "#64748b" }}>{ROLE_META[r].label}</div>
                <div style={{ fontSize: 10, color: "#94a3b8", marginTop: 2 }}>{r === "member" ? "Acesso padrão" : "Gerencia membros"}</div>
              </button>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <button onClick={() => setShowAddMember(false)} style={{ padding: "9px 18px", borderRadius: 9, border: "1px solid #e2e8f0", background: "white", cursor: "pointer", fontSize: 12, fontWeight: 600, color: "#64748b", fontFamily: F }}>Cancelar</button>
            <button onClick={handleAddMember} disabled={saving} style={{ padding: "9px 18px", borderRadius: 9, border: "none", background: "#6366f1", cursor: "pointer", fontSize: 12, fontWeight: 600, color: "white", fontFamily: F, opacity: saving ? 0.7 : 1 }}>{saving ? "Adicionando..." : "Adicionar"}</button>
          </div>
        </Modal>

        {/* Confirm Remove Modal */}
        <Modal open={confirmDeleteOrg} onClose={() => setConfirmDeleteOrg(false)} title="Excluir equipe" width={440}>
          <p style={{ fontSize: 13, color: "#1e293b", margin: "0 0 12px", fontFamily: F }}>
            Excluir <strong>{selectedOrg.name}</strong> é permanente. Antes de confirmar:
          </p>
          <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 9, padding: "11px 13px", marginBottom: 11 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#b91c1c", marginBottom: 5, fontFamily: F }}>Será apagado</div>
            <div style={{ fontSize: 12, color: "#7f1d1d", fontFamily: F, lineHeight: 1.5 }}>
              As regras da equipe, os templates de contrato, os webhooks e a lista de membros.
            </div>
          </div>
          <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 9, padding: "11px 13px", marginBottom: 16 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#15803d", marginBottom: 5, fontFamily: F }}>Será preservado</div>
            <div style={{ fontSize: 12, color: "#14532d", fontFamily: F, lineHeight: 1.5 }}>
              Os documentos e suas análises. Cada um volta para o escopo pessoal de quem enviou.
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <button onClick={() => setConfirmDeleteOrg(false)} style={{ padding: "8px 16px", borderRadius: 9, border: "1px solid #e2e8f0", background: "white", cursor: "pointer", fontSize: 12, fontWeight: 600, color: "#64748b", fontFamily: F }}>Cancelar</button>
            <button onClick={handleDeleteOrg} disabled={deletingOrg} style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 16px", borderRadius: 9, border: "none", background: "#ef4444", cursor: deletingOrg ? "default" : "pointer", fontSize: 12, fontWeight: 600, color: "white", fontFamily: F, opacity: deletingOrg ? 0.7 : 1 }}>
              {deletingOrg && <Loader2 size={13} style={{ animation: "spin 1s linear infinite" }} />}
              Excluir equipe
            </button>
          </div>
        </Modal>

        <Modal open={!!confirmRemove} onClose={() => setConfirmRemove(null)} title="Remover membro" width={380}>
          <p style={{ fontSize: 13, color: "#1e293b", margin: "0 0 16px", fontFamily: F }}>Tem certeza? O membro será removido da organização.</p>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <button onClick={() => setConfirmRemove(null)} style={{ padding: "8px 16px", borderRadius: 9, border: "1px solid #e2e8f0", background: "white", cursor: "pointer", fontSize: 12, fontWeight: 600, color: "#64748b", fontFamily: F }}>Cancelar</button>
            <button onClick={() => handleRemoveMember(confirmRemove)} style={{ padding: "8px 16px", borderRadius: 9, border: "none", background: "#ef4444", cursor: "pointer", fontSize: 12, fontWeight: 600, color: "white", fontFamily: F }}>Remover</button>
          </div>
        </Modal>
      </div>
    );
  }

  // ── Organizations list view ──
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24, flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, color: "#0f172a", fontFamily: F, letterSpacing: "-0.03em", margin: 0 }}>Equipe e Organizações</h1>
          <p style={{ color: "#64748b", fontSize: 13, marginTop: 4, fontFamily: F }}>Gerencie suas organizações, membros e permissões</p>
        </div>
        <button onClick={() => setShowCreate(true)} style={{ display: "inline-flex", alignItems: "center", gap: 6, background: "linear-gradient(135deg, #6366f1, #8b5cf6)", color: "white", padding: "10px 20px", borderRadius: 10, border: "none", cursor: "pointer", fontSize: 13, fontWeight: 600, fontFamily: F }}>
          <Plus size={15} /> Nova organização
        </button>
      </div>

      {loading ? (
        <div style={{ padding: 60, textAlign: "center" }}><Loader2 size={28} color="#6366f1" style={{ animation: "spin 1s linear infinite" }} /></div>
      ) : orgs.length === 0 ? (
        <div style={{ background: "white", borderRadius: 16, border: "1px solid #e2e8f0", padding: "56px 32px", textAlign: "center" }}>
          <div style={{ width: 64, height: 64, borderRadius: 16, background: "#eef2ff", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 18px" }}><Building size={28} color="#6366f1" /></div>
          <h3 style={{ fontSize: 16, fontWeight: 700, color: "#0f172a", margin: "0 0 6px", fontFamily: F }}>Nenhuma organização</h3>
          <p style={{ fontSize: 13, color: "#64748b", margin: "0 0 20px", fontFamily: F }}>Crie uma organização para começar a gerenciar sua equipe.</p>
          <button onClick={() => setShowCreate(true)} style={{ display: "inline-flex", alignItems: "center", gap: 6, background: "#6366f1", color: "white", padding: "10px 20px", borderRadius: 10, border: "none", cursor: "pointer", fontSize: 13, fontWeight: 600, fontFamily: F }}><Plus size={15} /> Criar organização</button>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 16 }}>
          {orgs.map(org => (
            <div key={org.id} onClick={() => loadOrgDetail(org)} style={{ background: "white", borderRadius: 14, border: "1px solid #e2e8f0", padding: "22px", cursor: "pointer", transition: "all 0.15s" }} onMouseOver={e => { e.currentTarget.style.borderColor = "#c7d2fe"; e.currentTarget.style.boxShadow = "0 4px 12px rgba(99,102,241,0.08)"; }} onMouseOut={e => { e.currentTarget.style.borderColor = "#e2e8f0"; e.currentTarget.style.boxShadow = "none"; }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
                <div style={{ width: 42, height: 42, borderRadius: 11, background: "#eef2ff", display: "flex", alignItems: "center", justifyContent: "center" }}><Building size={20} color="#6366f1" /></div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", fontFamily: F }}>{org.name}</div>
                  <div style={{ fontSize: 11, color: "#94a3b8", fontFamily: F }}>/{org.slug}</div>
                </div>
                <ChevronRight size={16} color="#cbd5e1" />
              </div>
              <div style={{ display: "flex", gap: 16, paddingTop: 12, borderTop: "1px solid #f1f5f9" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 5 }}><Users size={13} color="#94a3b8" /><span style={{ fontSize: 12, color: "#64748b", fontFamily: F }}>{org.member_count} {org.member_count === 1 ? "membro" : "membros"}</span></div>
                {org.cnpj && <div style={{ fontSize: 11, color: "#94a3b8", fontFamily: F }}>CNPJ: {org.cnpj}</div>}
                <span style={{ fontSize: 10, fontWeight: 600, color: org.is_active ? "#16a34a" : "#dc2626", marginLeft: "auto" }}>{org.is_active ? "Ativa" : "Inativa"}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create Organization Modal */}
      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="Nova organização" width={460}>
        <label style={{ fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 5, display: "block", fontFamily: F }}>Nome da organização *</label>
        <input value={createForm.name} onChange={e => { setCreateForm({ ...createForm, name: e.target.value, slug: e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") }); }} placeholder="Minha Empresa" style={{ width: "100%", padding: "10px 14px", borderRadius: 10, border: "1px solid #d1d5db", fontSize: 13, fontFamily: F, outline: "none", boxSizing: "border-box", marginBottom: 14 }} />
        <label style={{ fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 5, display: "block", fontFamily: F }}>Slug (URL) *</label>
        <div style={{ position: "relative", marginBottom: 14 }}>
          <span style={{ position: "absolute", left: 12, top: 10, fontSize: 13, color: "#94a3b8", fontFamily: F }}>/</span>
          <input value={createForm.slug} onChange={e => setCreateForm({ ...createForm, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "") })} placeholder="minha-empresa" style={{ width: "100%", padding: "10px 14px 10px 22px", borderRadius: 10, border: "1px solid #d1d5db", fontSize: 13, fontFamily: F, outline: "none", boxSizing: "border-box" }} />
        </div>
        <label style={{ fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 5, display: "block", fontFamily: F }}>CNPJ (opcional)</label>
        <input value={createForm.cnpj} onChange={e => setCreateForm({ ...createForm, cnpj: e.target.value })} placeholder="00.000.000/0001-00" style={{ width: "100%", padding: "10px 14px", borderRadius: 10, border: "1px solid #d1d5db", fontSize: 13, fontFamily: F, outline: "none", boxSizing: "border-box", marginBottom: 20 }} />
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button onClick={() => setShowCreate(false)} style={{ padding: "9px 18px", borderRadius: 9, border: "1px solid #e2e8f0", background: "white", cursor: "pointer", fontSize: 12, fontWeight: 600, color: "#64748b", fontFamily: F }}>Cancelar</button>
          <button onClick={handleCreateOrg} disabled={saving} style={{ padding: "9px 18px", borderRadius: 9, border: "none", background: "#6366f1", cursor: "pointer", fontSize: 12, fontWeight: 600, color: "white", fontFamily: F, opacity: saving ? 0.7 : 1 }}>{saving ? "Criando..." : "Criar organização"}</button>
        </div>
      </Modal>
    </div>
  );
};

// ── Main App ──
// Seletor do escopo de trabalho. Trocar aqui muda dashboard, histórico, nova
// análise e regras de uma vez — é o contexto da sessão, não uma opção por tela.
const ScopeSwitcher = ({ scopeOrgId, orgs, onChange, isMobile }) => {
  const [open, setOpen] = useState(false);
  const current = orgs.find(o => o.id === scopeOrgId);
  const label = current ? current.name : "Pessoal";

  return (
    <div style={{ position: "relative" }}>
      <button
        onClick={() => setOpen(!open)}
        style={{ display: "flex", alignItems: "center", gap: 7, padding: "5px 10px", borderRadius: 9, border: "1px solid #e2e8f0", background: "white", cursor: "pointer", fontFamily: F, maxWidth: isMobile ? 150 : 240 }}
        title="Escopo de trabalho"
      >
        <div style={{ width: 22, height: 22, borderRadius: 6, background: current ? "#f5f3ff" : "#eef2ff", border: `1px solid ${current ? "#ddd6fe" : "#c7d2fe"}`, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          {current ? <Users size={12} color="#7c3aed" /> : <User size={12} color="#6366f1" />}
        </div>
        <span style={{ fontSize: 11, fontWeight: 600, color: "#374151", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</span>
        <ChevronDown size={13} color="#94a3b8" style={{ flexShrink: 0 }} />
      </button>

      {open && (
        <>
          <div onClick={() => setOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 60 }} />
          <div style={{ position: "absolute", top: "calc(100% + 6px)", right: 0, minWidth: 220, background: "white", borderRadius: 11, border: "1px solid #e2e8f0", boxShadow: "0 10px 30px -10px rgba(15,23,42,0.25)", zIndex: 61, overflow: "hidden" }}>
            <div style={{ padding: "9px 13px 6px", fontSize: 10, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.06em", textTransform: "uppercase", fontFamily: F }}>Escopo de trabalho</div>

            <button onClick={() => { onChange(null); setOpen(false); }} style={{ width: "100%", display: "flex", alignItems: "center", gap: 9, padding: "9px 13px", border: "none", background: !scopeOrgId ? "#f8fafc" : "white", cursor: "pointer", textAlign: "left", fontFamily: F }}>
              <User size={14} color="#6366f1" />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: "#0f172a" }}>Pessoal</div>
                <div style={{ fontSize: 10, color: "#94a3b8" }}>Seus documentos e regras</div>
              </div>
              {!scopeOrgId && <Check size={14} color="#6366f1" />}
            </button>

            {orgs.map(o => (
              <button key={o.id} onClick={() => { onChange(o.id); setOpen(false); }} style={{ width: "100%", display: "flex", alignItems: "center", gap: 9, padding: "9px 13px", border: "none", borderTop: "1px solid #f8fafc", background: scopeOrgId === o.id ? "#f8fafc" : "white", cursor: "pointer", textAlign: "left", fontFamily: F }}>
                <Users size={14} color="#7c3aed" />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "#0f172a", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{o.name}</div>
                  <div style={{ fontSize: 10, color: "#94a3b8" }}>Compartilhado com a equipe</div>
                </div>
                {scopeOrgId === o.id && <Check size={14} color="#7c3aed" />}
              </button>
            ))}

            {orgs.length === 0 && (
              <div style={{ padding: "9px 13px 12px", fontSize: 11, color: "#94a3b8", fontFamily: F, borderTop: "1px solid #f8fafc" }}>
                Você ainda não participa de equipes. Crie uma na aba Equipe.
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
};

export default function ComplianceApp() {
  const [loggedIn, setLoggedIn] = useState(false);
  const [user, setUser] = useState(null);
  // Area publica: a landing e a porta de entrada, e o formulario de senha so
  // aparece a pedido. Quem chega por indicacao precisa saber o que e a
  // ferramenta antes de decidir criar conta. O hash permite mandar alguem
  // direto para o login (complianceai.app/#entrar).
  const [authView, setAuthView] = useState(() => {
    const h = typeof window !== "undefined" ? window.location.hash : "";
    if (h === "#entrar") return "login";
    if (h === "#criar-conta") return "register";
    return "landing";
  });
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [currentPage, setCurrentPage] = useState("dashboard");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [toastMsg, setToastMsg] = useState(null);
  const [isMobile, setIsMobile] = useState(false);
  const [scopeOrgId, setScopeOrgId] = useState(() => api.scopeOrgId);
  const [myOrgs, setMyOrgs] = useState([]);

  useEffect(() => { const c = () => setIsMobile(window.innerWidth < 768); c(); window.addEventListener("resize", c); return () => window.removeEventListener("resize", c); }, []);

  // Equipes de que o usuário participa, para alimentar o seletor de escopo.
  // Precisa ser recarregável: criar uma equipe, entrar em outra ou mudar de papel
  // altera o seletor, e obrigar a recarregar a página para ver isso é o tipo de
  // atrito que faz parecer que a criação não funcionou.
  const aplicarOrgs = useCallback((orgs) => {
    setMyOrgs(orgs);
    // Escopo salvo que não existe mais (saiu da equipe): volta para o pessoal.
    setScopeOrgId(prev => {
      if (prev && !orgs.some(o => o.id === prev)) {
        api.setScope(null);
        return null;
      }
      return prev;
    });
  }, []);

  const refreshOrgs = useCallback(async () => {
    try {
      const orgs = (await api.listOrganizations()) || [];
      aplicarOrgs(orgs);
      return orgs;
    } catch {
      setMyOrgs([]);
      return [];
    }
  }, [aplicarOrgs]);

  useEffect(() => {
    if (!loggedIn) return;
    let ativo = true;
    api.listOrganizations()
      .then(list => { if (ativo) aplicarOrgs(list || []); })
      .catch(() => { if (ativo) setMyOrgs([]); });
    return () => { ativo = false; };
  }, [loggedIn, aplicarOrgs]);

  // Equipe excluida: some da lista e, se era o escopo ativo, volta para o pessoal.
  const handleOrgDeleted = (orgId) => {
    setMyOrgs(prev => prev.filter(o => o.id !== orgId));
    if (scopeOrgId === orgId) {
      api.setScope(null);
      setScopeOrgId(null);
    }
  };

  const changeScope = (orgId) => {
    api.setScope(orgId);
    setScopeOrgId(orgId);
    setSelectedDoc(null);
  };

  // Restore session from localStorage on mount
  useEffect(() => {
    if (api.accessToken) {
      api.getMe().then(u => {
        setUser(u);
        setLoggedIn(true);
      }).catch(() => {
        api.clearTokens();
      }).finally(() => setCheckingAuth(false));
    } else {
      setCheckingAuth(false);
    }
  }, []);

  const showToast = useCallback((message, type = "success") => setToastMsg({ message, type }), []);
  const navigate = (page) => { setCurrentPage(page); setSelectedDoc(null); };
  const viewReport = (docId) => { setSelectedDoc(docId); setCurrentPage("report"); };

  // Set up unauthorized handler
  useEffect(() => {
    api.onUnauthorized = () => {
      setLoggedIn(false);
      setUser(null);
      api.clearTokens();
      showToast("Sessão expirada. Faça login novamente.", "error");
    };
  }, [showToast]);

  if (checkingAuth) return (<div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "#f5f6fa", fontFamily: F }}><Loader2 size={28} color="#6366f1" style={{ animation: "spin 1s linear infinite" }} /></div>);
  if (!loggedIn) {
    const estiloPublico = (
      <style>{`@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&display=swap'); * { box-sizing: border-box; margin: 0; padding: 0; } @keyframes fadeSlideUp { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } } @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } } input:focus { border-color: #6366f1 !important; box-shadow: 0 0 0 3px rgba(99,102,241,0.1); }`}</style>
    );

    const irPara = (destino) => {
      setAuthView(destino);
      const hash = destino === "landing" ? "" : destino === "login" ? "#entrar" : "#criar-conta";
      window.history.replaceState(null, "", hash || window.location.pathname);
      window.scrollTo(0, 0);
    };

    if (authView === "landing") {
      return (<>{estiloPublico}<LandingPage onEntrar={() => irPara("login")} onCriarConta={() => irPara("register")} /></>);
    }

    return (<>{estiloPublico}<LoginPage
      initialMode={authView}
      onVoltar={() => irPara("landing")}
      onLogin={u => { setUser(u); setLoggedIn(true); }}
    /></>);
  }

  const sidebarW = isMobile ? 0 : (sidebarCollapsed ? 72 : 260);

  // No escopo pessoal cada um manda no que e seu. Na equipe, criar cliente e
  // designar acesso sao de owner e admin.
  const podeGerirEscopo = !scopeOrgId || ["owner", "admin"].includes(
    myOrgs.find(o => o.id === scopeOrgId)?.my_role
  );

  const renderPage = () => {
    switch (currentPage) {
      case "dashboard": return <DashboardPage onNavigate={navigate} onViewReport={viewReport} />;
      case "upload": return <UploadPage onAnalyzeComplete={(id) => { viewReport(id); showToast("Análise concluída!", "success"); }} showToast={showToast} />;
      case "report": return <ReportPage docId={selectedDoc} onBack={() => navigate("history")} showToast={showToast} />;
      case "history": return <HistoryPage onViewReport={viewReport} showToast={showToast} />;
      case "legislation": return <LegislationPage showToast={showToast} />;
      case "rules": return <RulesPage showToast={showToast} scopeOrgId={scopeOrgId} />;
      case "clients": return <ClientsPage showToast={showToast} scopeOrgId={scopeOrgId} canManage={podeGerirEscopo} />;
      case "team": return <TeamPage showToast={showToast} user={user} onOrgDeleted={handleOrgDeleted} onOrgsChanged={refreshOrgs} />;
      default: return <DashboardPage onNavigate={navigate} onViewReport={viewReport} />;
    }
  };

  return (
    <div style={{ minHeight: "100vh", background: "#f5f6fa", fontFamily: F }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        @keyframes fadeSlideUp { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        ::-webkit-scrollbar { width: 5px; } ::-webkit-scrollbar-track { background: transparent; } ::-webkit-scrollbar-thumb { background: #d1d5db; border-radius: 3px; }
        input:focus, select:focus, textarea:focus { border-color: #6366f1 !important; box-shadow: 0 0 0 3px rgba(99,102,241,0.1); }
        .stats-grid { grid-template-columns: repeat(6, 1fr); }
        .dashboard-grid { grid-template-columns: 1fr 1fr; }
        .report-grid { grid-template-columns: 1fr 2fr; }
        .upload-features { grid-template-columns: 1fr 1fr 1fr; }
        .history-header, .history-row { grid-template-columns: 2fr 1fr 1fr 1fr 100px; }
        @media (max-width: 1200px) { .stats-grid { grid-template-columns: repeat(3, 1fr) !important; } }
        .report-stats { grid-template-columns: repeat(4, 1fr); }
        @media (max-width: 1024px) { .stats-grid { grid-template-columns: repeat(3, 1fr) !important; } .dashboard-grid { grid-template-columns: 1fr !important; } .report-grid { grid-template-columns: 1fr !important; } .report-stats { grid-template-columns: repeat(2, 1fr) !important; } }
        @media (max-width: 768px) { .stats-grid { grid-template-columns: repeat(2, 1fr) !important; } .dashboard-grid { grid-template-columns: 1fr !important; } .report-grid { grid-template-columns: 1fr !important; } .report-stats { grid-template-columns: 1fr !important; } .upload-features { grid-template-columns: 1fr !important; } .history-header { display: none !important; } .history-row { grid-template-columns: 1fr !important; gap: 6px !important; } }
      `}</style>
      <Sidebar currentPage={currentPage} onNavigate={navigate} collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed(!sidebarCollapsed)} user={user} onLogout={() => { setLoggedIn(false); setUser(null); setMyOrgs([]); api.setScope(null); setScopeOrgId(null); api.clearTokens(); }} isMobile={isMobile} mobileOpen={mobileMenuOpen} onMobileClose={() => setMobileMenuOpen(false)} />
      <div style={{ marginLeft: sidebarW, transition: "margin-left 0.3s ease", minHeight: "100vh" }}>
        <div style={{ padding: isMobile ? "10px 14px" : "12px 32px", background: "rgba(255,255,255,0.8)", backdropFilter: "blur(12px)", borderBottom: "1px solid #e2e8f0", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, position: "sticky", top: 0, zIndex: 50 }}>
          {isMobile && <button onClick={() => setMobileMenuOpen(true)} style={{ width: 36, height: 36, borderRadius: 9, border: "1px solid #e2e8f0", background: "white", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}><Menu size={17} color="#374151" /></button>}
          <div style={{ flex: 1 }} />
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <ScopeSwitcher scopeOrgId={scopeOrgId} orgs={myOrgs} onChange={changeScope} isMobile={isMobile} />
            {!isMobile && <div style={{ display: "flex", alignItems: "center", gap: 7, padding: "4px 10px 4px 4px", borderRadius: 9, border: "1px solid #e2e8f0", background: "white" }}><div style={{ width: 26, height: 26, borderRadius: 6, background: "linear-gradient(135deg, #6366f1, #8b5cf6)", display: "flex", alignItems: "center", justifyContent: "center" }}><User size={13} color="white" /></div><span style={{ fontSize: 11, fontWeight: 600, color: "#374151", fontFamily: F }}>{user?.full_name}</span></div>}
          </div>
        </div>
        <div key={scopeOrgId || "personal"} style={{ padding: isMobile ? "18px 14px" : "28px 32px", maxWidth: 1160, animation: "fadeSlideUp 0.4s ease" }}>{renderPage()}</div>
      </div>
      {toastMsg && <Toast message={toastMsg.message} type={toastMsg.type} onClose={() => setToastMsg(null)} />}
    </div>
  );
}
