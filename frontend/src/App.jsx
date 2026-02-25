import { useState, useEffect, useRef, useCallback } from "react";

// ===========================
// MIZAN (ميزان) - Quranic AGI System
// Design: Geometric Islamic patterns, deep space dark, gold accents
// Typography: Arabic numerals + Latin + Quranic-inspired layout
// ===========================

const WS_URL = "ws://localhost:8000/ws";
const API_URL = "http://localhost:8000/api";

// ===== ICONS (inline SVG) =====
const Icons = {
  Agent: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-5 h-5">
      <circle cx="12" cy="8" r="4"/>
      <path d="M4 20c0-4 3.58-7 8-7s8 3 8 7"/>
      <path d="M20 12h2M2 12h2M12 2v2M12 20v2"/>
    </svg>
  ),
  Brain: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-5 h-5">
      <path d="M12 5c-2.8 0-5 2.2-5 5 0 1.5.6 2.8 1.5 3.8C7.2 15 6 17 6 19h12c0-2 -1.2-4-2.5-5.2C16.4 12.8 17 11.5 17 10c0-2.8-2.2-5-5-5z"/>
      <path d="M9 10h6M10 13h4"/>
    </svg>
  ),
  Terminal: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-5 h-5">
      <rect x="3" y="4" width="18" height="16" rx="2"/>
      <path d="M7 9l3 3-3 3M13 15h4"/>
    </svg>
  ),
  Memory: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-5 h-5">
      <rect x="2" y="7" width="20" height="10" rx="2"/>
      <path d="M7 7V5M12 7V5M17 7V5M7 17v2M12 17v2M17 17v2"/>
      <circle cx="7" cy="12" r="1.5" fill="currentColor"/>
      <circle cx="12" cy="12" r="1.5" fill="currentColor"/>
      <circle cx="17" cy="12" r="1.5" fill="currentColor"/>
    </svg>
  ),
  Chat: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-5 h-5">
      <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
    </svg>
  ),
  Settings: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-5 h-5">
      <circle cx="12" cy="12" r="3"/>
      <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"/>
    </svg>
  ),
  Plus: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
      <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
    </svg>
  ),
  Send: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
      <line x1="22" y1="2" x2="11" y2="13"/>
      <polygon points="22 2 15 22 11 13 2 9 22 2"/>
    </svg>
  ),
  Trash: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-4 h-4">
      <polyline points="3 6 5 6 21 6"/>
      <path d="M19 6l-1 14H6L5 6M10 11v6M14 11v6M9 6V4h6v2"/>
    </svg>
  ),
  Globe: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-5 h-5">
      <circle cx="12" cy="12" r="10"/>
      <line x1="2" y1="12" x2="22" y2="12"/>
      <path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/>
    </svg>
  ),
  Zap: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-5 h-5">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
    </svg>
  ),
  Scale: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-5 h-5">
      <line x1="12" y1="3" x2="12" y2="21"/>
      <path d="M3 6l9-3 9 3"/>
      <path d="M3 6c0 3.3-2 5-2 5h4s-2-1.7-2-5"/>
      <path d="M21 6c0 3.3-2 5-2 5h4s-2-1.7-2-5"/>
    </svg>
  ),
};

// ===== QURANIC CONCEPTS DISPLAY =====
const NAFS_LEVELS = {
  1: { name: "أمارة", latin: "Ammara", color: "#ef4444", desc: "Raw potential" },
  2: { name: "لوامة", latin: "Lawwama", color: "#f59e0b", desc: "Self-correcting" },
  3: { name: "مطمئنة", latin: "Mutmainna", color: "#10b981", desc: "Perfected" },
};

const AGENT_ROLE_ICONS = {
  rasul: "رسول",
  wakil: "وكيل",
  hafiz: "حافظ",
  shahid: "شاهد",
  wali: "ولي",
  mubashir: "مبشر",
  mundhir: "منذر",
  katib: "كاتب",
  muallim: "معلم",
};

// ===== CSS =====
const styles = `
  @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;500;600;700&family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&family=IBM+Plex+Mono:wght@300;400;500&display=swap');

  :root {
    --void: #030608;
    --abyss: #060c10;
    --depth: #0a1520;
    --dark: #0f2030;
    --mid: #162840;
    --surface: #1e3a55;
    --border: #1e3a55;
    --border-light: #2a4f70;
    
    --gold: #c9a227;
    --gold-light: #e8c547;
    --gold-muted: #8a6e1a;
    --gold-dim: #4a3a0f;
    
    --emerald: #10b981;
    --emerald-dim: #064e3b;
    --ruby: #ef4444;
    --ruby-dim: #7f1d1d;
    --amber: #f59e0b;
    --amber-dim: #78350f;
    --sapphire: #3b82f6;
    --sapphire-dim: #1e3a8a;
    
    --text-primary: #e8d5b0;
    --text-secondary: #8fa8c0;
    --text-muted: #4a6880;
    --text-arabic: #c9a227;
    
    --glow-gold: 0 0 20px rgba(201,162,39,0.3);
    --glow-emerald: 0 0 20px rgba(16,185,129,0.3);
    --font-display: 'Cinzel', serif;
    --font-body: 'Libre Baskerville', serif;
    --font-mono: 'IBM Plex Mono', monospace;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }
  
  html, body { height: 100%; background: var(--void); color: var(--text-primary); }
  
  #root {
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    font-family: var(--font-body);
    font-size: 13px;
    background: var(--void);
  }

  /* Geometric Islamic pattern background */
  .geometric-bg {
    position: fixed;
    inset: 0;
    pointer-events: none;
    z-index: 0;
    overflow: hidden;
  }
  
  .geometric-bg::before {
    content: '';
    position: absolute;
    inset: 0;
    background: 
      radial-gradient(ellipse at 20% 20%, rgba(201,162,39,0.04) 0%, transparent 50%),
      radial-gradient(ellipse at 80% 80%, rgba(16,185,129,0.03) 0%, transparent 50%),
      radial-gradient(ellipse at 50% 50%, rgba(30,58,85,0.2) 0%, transparent 70%);
  }
  
  .geometric-bg svg {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    opacity: 0.025;
  }

  /* Scrollbar */
  ::-webkit-scrollbar { width: 4px; }
  ::-webkit-scrollbar-track { background: var(--abyss); }
  ::-webkit-scrollbar-thumb { background: var(--gold-muted); border-radius: 2px; }

  /* Header */
  .header {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 12px 20px;
    background: linear-gradient(180deg, rgba(6,12,16,0.98) 0%, rgba(6,12,16,0.9) 100%);
    border-bottom: 1px solid rgba(201,162,39,0.2);
    z-index: 100;
    flex-shrink: 0;
    backdrop-filter: blur(12px);
  }
  
  .logo {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  
  .logo-symbol {
    width: 36px;
    height: 36px;
    position: relative;
  }
  
  .logo-text {
    display: flex;
    flex-direction: column;
    gap: 1px;
  }
  
  .logo-arabic {
    font-family: Georgia, serif;
    font-size: 22px;
    color: var(--gold);
    line-height: 1;
    letter-spacing: 0.05em;
  }
  
  .logo-latin {
    font-family: var(--font-display);
    font-size: 9px;
    letter-spacing: 0.3em;
    color: var(--text-muted);
    text-transform: uppercase;
  }
  
  .header-verse {
    flex: 1;
    text-align: center;
    font-style: italic;
    color: var(--text-muted);
    font-size: 11px;
    letter-spacing: 0.05em;
  }
  
  .header-status {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  
  .status-pill {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 20px;
    background: rgba(16,185,129,0.1);
    border: 1px solid rgba(16,185,129,0.2);
    font-size: 11px;
    color: var(--emerald);
    font-family: var(--font-mono);
  }
  
  .status-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--emerald);
    animation: pulse 2s infinite;
  }
  
  @keyframes pulse {
    0%, 100% { opacity: 1; box-shadow: 0 0 6px var(--emerald); }
    50% { opacity: 0.5; box-shadow: none; }
  }

  /* Main layout */
  .main-layout {
    flex: 1;
    display: flex;
    overflow: hidden;
    position: relative;
    z-index: 1;
  }

  /* Sidebar */
  .sidebar {
    width: 220px;
    flex-shrink: 0;
    background: rgba(6,12,16,0.95);
    border-right: 1px solid rgba(30,58,85,0.5);
    display: flex;
    flex-direction: column;
    padding: 12px 0;
    overflow-y: auto;
  }
  
  .nav-section {
    padding: 0 8px;
    margin-bottom: 4px;
  }
  
  .nav-section-label {
    font-family: var(--font-display);
    font-size: 8px;
    letter-spacing: 0.3em;
    color: var(--text-muted);
    text-transform: uppercase;
    padding: 6px 10px 4px;
  }
  
  .nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    border-radius: 6px;
    cursor: pointer;
    color: var(--text-secondary);
    transition: all 0.15s;
    font-size: 12px;
    border: 1px solid transparent;
  }
  
  .nav-item:hover {
    background: rgba(30,58,85,0.4);
    color: var(--text-primary);
    border-color: rgba(201,162,39,0.1);
  }
  
  .nav-item.active {
    background: rgba(201,162,39,0.08);
    color: var(--gold);
    border-color: rgba(201,162,39,0.2);
  }
  
  .nav-item-arabic {
    margin-left: auto;
    font-family: Georgia, serif;
    font-size: 14px;
    color: var(--gold-muted);
    opacity: 0.6;
  }

  /* Content area */
  .content {
    flex: 1;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  /* Agents panel */
  .agents-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 12px;
    padding: 16px;
    overflow-y: auto;
    flex: 1;
  }
  
  .agent-card {
    background: linear-gradient(135deg, rgba(15,32,48,0.9) 0%, rgba(10,21,32,0.9) 100%);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px;
    cursor: pointer;
    transition: all 0.2s;
    position: relative;
    overflow: hidden;
  }
  
  .agent-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, var(--gold), transparent);
    opacity: 0;
    transition: opacity 0.2s;
  }
  
  .agent-card:hover {
    border-color: rgba(201,162,39,0.3);
    transform: translateY(-1px);
    box-shadow: 0 4px 20px rgba(0,0,0,0.4), var(--glow-gold);
  }
  
  .agent-card:hover::before { opacity: 1; }
  
  .agent-card.selected {
    border-color: rgba(201,162,39,0.4);
    background: linear-gradient(135deg, rgba(201,162,39,0.06) 0%, rgba(10,21,32,0.9) 100%);
  }
  
  .agent-header {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    margin-bottom: 12px;
  }
  
  .agent-avatar {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: linear-gradient(135deg, var(--dark) 0%, var(--depth) 100%);
    border: 1px solid var(--border-light);
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: Georgia, serif;
    font-size: 16px;
    color: var(--gold);
    flex-shrink: 0;
  }
  
  .agent-info { flex: 1; min-width: 0; }
  
  .agent-name {
    font-family: var(--font-display);
    font-size: 13px;
    color: var(--text-primary);
    font-weight: 600;
    letter-spacing: 0.05em;
    margin-bottom: 2px;
  }
  
  .agent-role {
    font-size: 10px;
    color: var(--text-muted);
    letter-spacing: 0.1em;
    text-transform: uppercase;
    font-family: var(--font-mono);
  }
  
  .agent-state {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 10px;
    font-family: var(--font-mono);
    padding: 2px 8px;
    border-radius: 10px;
  }
  
  .state-resting { background: rgba(74,104,128,0.2); color: var(--text-muted); border: 1px solid rgba(74,104,128,0.3); }
  .state-thinking { background: rgba(59,130,246,0.15); color: var(--sapphire); border: 1px solid rgba(59,130,246,0.3); }
  .state-acting { background: rgba(201,162,39,0.15); color: var(--gold); border: 1px solid rgba(201,162,39,0.3); }
  .state-learning { background: rgba(16,185,129,0.15); color: var(--emerald); border: 1px solid rgba(16,185,129,0.3); }
  .state-error { background: rgba(239,68,68,0.15); color: var(--ruby); border: 1px solid rgba(239,68,68,0.3); }
  
  .nafs-bar {
    margin: 8px 0;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  
  .nafs-label {
    font-family: Georgia, serif;
    font-size: 11px;
    color: var(--text-muted);
    min-width: 70px;
  }
  
  .nafs-track {
    flex: 1;
    height: 3px;
    background: var(--mid);
    border-radius: 2px;
    overflow: hidden;
  }
  
  .nafs-fill {
    height: 100%;
    border-radius: 2px;
    transition: width 0.3s;
  }
  
  .agent-stats {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 6px;
    margin-top: 10px;
  }
  
  .stat {
    text-align: center;
    padding: 6px 4px;
    background: rgba(6,12,16,0.5);
    border-radius: 4px;
    border: 1px solid rgba(30,58,85,0.3);
  }
  
  .stat-value {
    font-family: var(--font-mono);
    font-size: 13px;
    color: var(--text-primary);
    display: block;
  }
  
  .stat-label {
    font-size: 9px;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    display: block;
    margin-top: 1px;
  }
  
  .agent-tools {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 8px;
  }
  
  .tool-tag {
    font-family: var(--font-mono);
    font-size: 9px;
    padding: 2px 6px;
    background: rgba(30,58,85,0.4);
    border: 1px solid var(--border);
    border-radius: 3px;
    color: var(--text-muted);
  }

  /* Chat area */
  .chat-container {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: var(--abyss);
  }
  
  .chat-header {
    padding: 12px 16px;
    border-bottom: 1px solid rgba(30,58,85,0.5);
    display: flex;
    align-items: center;
    gap: 10px;
    background: rgba(6,12,16,0.8);
  }
  
  .chat-agent-select {
    background: var(--dark);
    border: 1px solid var(--border);
    color: var(--text-primary);
    padding: 5px 10px;
    border-radius: 6px;
    font-family: var(--font-mono);
    font-size: 11px;
    cursor: pointer;
    outline: none;
  }
  
  .chat-messages {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  
  .message {
    display: flex;
    gap: 10px;
    animation: fadeIn 0.2s ease;
  }
  
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(4px); }
    to { opacity: 1; transform: translateY(0); }
  }
  
  .message.user { flex-direction: row-reverse; }
  
  .msg-avatar {
    width: 30px;
    height: 30px;
    border-radius: 50%;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    font-family: Georgia, serif;
  }
  
  .msg-avatar.agent {
    background: linear-gradient(135deg, var(--dark), var(--depth));
    border: 1px solid rgba(201,162,39,0.3);
    color: var(--gold);
  }
  
  .msg-avatar.user {
    background: linear-gradient(135deg, var(--sapphire-dim), var(--dark));
    border: 1px solid rgba(59,130,246,0.3);
    color: var(--sapphire);
  }
  
  .msg-bubble {
    max-width: 75%;
    padding: 10px 14px;
    border-radius: 10px;
    line-height: 1.6;
    font-size: 13px;
  }
  
  .msg-bubble.agent {
    background: rgba(15,32,48,0.8);
    border: 1px solid rgba(30,58,85,0.6);
    color: var(--text-primary);
    border-radius: 2px 10px 10px 10px;
  }
  
  .msg-bubble.user {
    background: rgba(59,130,246,0.1);
    border: 1px solid rgba(59,130,246,0.2);
    color: var(--text-primary);
    border-radius: 10px 2px 10px 10px;
  }
  
  .msg-meta {
    font-size: 10px;
    color: var(--text-muted);
    margin-top: 3px;
    font-family: var(--font-mono);
  }
  
  .streaming-cursor {
    display: inline-block;
    width: 2px;
    height: 14px;
    background: var(--gold);
    margin-left: 2px;
    vertical-align: middle;
    animation: blink 1s infinite;
  }
  
  @keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0; }
  }
  
  .chat-input-area {
    padding: 12px 16px;
    border-top: 1px solid rgba(30,58,85,0.5);
    background: rgba(6,12,16,0.9);
    display: flex;
    gap: 8px;
    align-items: flex-end;
  }
  
  .chat-input {
    flex: 1;
    background: rgba(15,32,48,0.6);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text-primary);
    padding: 10px 14px;
    font-family: var(--font-body);
    font-size: 13px;
    resize: none;
    outline: none;
    max-height: 120px;
    transition: border-color 0.15s;
    line-height: 1.5;
  }
  
  .chat-input:focus {
    border-color: rgba(201,162,39,0.3);
    box-shadow: 0 0 0 2px rgba(201,162,39,0.05);
  }
  
  .chat-input::placeholder { color: var(--text-muted); }
  
  .send-btn {
    width: 38px;
    height: 38px;
    border-radius: 8px;
    background: linear-gradient(135deg, var(--gold-muted), var(--gold));
    border: none;
    color: var(--abyss);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    transition: all 0.15s;
    font-weight: bold;
  }
  
  .send-btn:hover {
    transform: scale(1.05);
    box-shadow: var(--glow-gold);
  }
  
  .send-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
    transform: none;
  }

  /* Terminal / Task panel */
  .terminal {
    background: var(--void);
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid var(--border);
    margin: 12px;
  }
  
  .terminal-header {
    padding: 8px 14px;
    background: rgba(15,32,48,0.8);
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 8px;
  }
  
  .terminal-dots {
    display: flex;
    gap: 5px;
  }
  
  .terminal-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
  }
  
  .terminal-body {
    padding: 12px 14px;
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--emerald);
    min-height: 120px;
    max-height: 300px;
    overflow-y: auto;
    line-height: 1.6;
  }
  
  .terminal-line { margin-bottom: 2px; }
  .terminal-line.error { color: var(--ruby); }
  .terminal-line.warn { color: var(--amber); }
  .terminal-line.info { color: var(--sapphire); }
  .terminal-line.gold { color: var(--gold); }
  
  .terminal-prompt {
    color: var(--gold);
    font-weight: 500;
  }
  
  .terminal-input {
    background: transparent;
    border: none;
    color: var(--emerald);
    font-family: var(--font-mono);
    font-size: 12px;
    outline: none;
    flex: 1;
    padding: 8px 14px;
    width: 100%;
  }
  
  .terminal-input-row {
    display: flex;
    align-items: center;
    border-top: 1px solid rgba(30,58,85,0.3);
    padding: 4px 8px;
  }

  /* Memory panel */
  .memory-panel {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
  }
  
  .memory-item {
    background: rgba(10,21,32,0.8);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 14px;
    margin-bottom: 8px;
    transition: border-color 0.15s;
  }
  
  .memory-item:hover { border-color: rgba(201,162,39,0.2); }
  
  .memory-type-badge {
    font-family: var(--font-mono);
    font-size: 9px;
    padding: 1px 6px;
    border-radius: 3px;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }
  
  .type-episodic { background: rgba(59,130,246,0.15); color: var(--sapphire); border: 1px solid rgba(59,130,246,0.2); }
  .type-semantic { background: rgba(201,162,39,0.15); color: var(--gold); border: 1px solid rgba(201,162,39,0.2); }
  .type-procedural { background: rgba(16,185,129,0.15); color: var(--emerald); border: 1px solid rgba(16,185,129,0.2); }

  /* Tabs */
  .tab-bar {
    display: flex;
    gap: 0;
    border-bottom: 1px solid rgba(30,58,85,0.5);
    background: rgba(6,12,16,0.6);
    padding: 0 16px;
  }
  
  .tab {
    padding: 10px 16px;
    font-size: 11px;
    font-family: var(--font-display);
    letter-spacing: 0.1em;
    color: var(--text-muted);
    cursor: pointer;
    border-bottom: 2px solid transparent;
    transition: all 0.15s;
    text-transform: uppercase;
  }
  
  .tab:hover { color: var(--text-secondary); }
  
  .tab.active {
    color: var(--gold);
    border-bottom-color: var(--gold);
  }

  /* Panel header */
  .panel-header {
    padding: 12px 16px;
    border-bottom: 1px solid rgba(30,58,85,0.5);
    display: flex;
    align-items: center;
    gap: 10px;
    background: rgba(6,12,16,0.6);
  }
  
  .panel-title {
    font-family: var(--font-display);
    font-size: 12px;
    letter-spacing: 0.15em;
    color: var(--gold);
    text-transform: uppercase;
    flex: 1;
  }
  
  .btn {
    padding: 6px 14px;
    border-radius: 6px;
    border: 1px solid var(--border);
    background: rgba(30,58,85,0.3);
    color: var(--text-secondary);
    font-family: var(--font-mono);
    font-size: 11px;
    cursor: pointer;
    transition: all 0.15s;
    display: flex;
    align-items: center;
    gap: 5px;
  }
  
  .btn:hover {
    background: rgba(201,162,39,0.1);
    border-color: rgba(201,162,39,0.3);
    color: var(--gold);
  }
  
  .btn.primary {
    background: rgba(201,162,39,0.15);
    border-color: rgba(201,162,39,0.4);
    color: var(--gold);
  }
  
  .btn.danger:hover {
    background: rgba(239,68,68,0.1);
    border-color: rgba(239,68,68,0.3);
    color: var(--ruby);
  }

  /* Modal */
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(3,6,8,0.85);
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
    backdrop-filter: blur(4px);
  }
  
  .modal {
    background: linear-gradient(135deg, var(--depth) 0%, var(--dark) 100%);
    border: 1px solid rgba(201,162,39,0.3);
    border-radius: 12px;
    padding: 24px;
    width: 460px;
    max-width: 95vw;
    box-shadow: 0 20px 60px rgba(0,0,0,0.8), var(--glow-gold);
  }
  
  .modal-title {
    font-family: var(--font-display);
    font-size: 14px;
    letter-spacing: 0.15em;
    color: var(--gold);
    text-transform: uppercase;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  
  .modal-footer {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
    margin-top: 20px;
  }
  
  .form-group {
    margin-bottom: 14px;
  }
  
  .form-label {
    display: block;
    font-size: 10px;
    letter-spacing: 0.15em;
    color: var(--text-muted);
    text-transform: uppercase;
    font-family: var(--font-display);
    margin-bottom: 6px;
  }
  
  .form-input {
    width: 100%;
    background: rgba(6,12,16,0.8);
    border: 1px solid var(--border);
    color: var(--text-primary);
    padding: 8px 12px;
    border-radius: 6px;
    font-family: var(--font-mono);
    font-size: 12px;
    outline: none;
    transition: border-color 0.15s;
  }
  
  .form-input:focus { border-color: rgba(201,162,39,0.4); }
  
  .form-select {
    width: 100%;
    background: rgba(6,12,16,0.8);
    border: 1px solid var(--border);
    color: var(--text-primary);
    padding: 8px 12px;
    border-radius: 6px;
    font-family: var(--font-mono);
    font-size: 12px;
    outline: none;
    cursor: pointer;
  }

  /* Stats bar */
  .stats-bar {
    display: flex;
    gap: 16px;
    padding: 8px 16px;
    background: rgba(6,12,16,0.6);
    border-bottom: 1px solid rgba(30,58,85,0.3);
    flex-shrink: 0;
  }
  
  .stat-chip {
    display: flex;
    align-items: center;
    gap: 6px;
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--text-muted);
  }
  
  .stat-chip-value {
    color: var(--text-primary);
    font-weight: 500;
  }

  /* Seven Heavens visualization */
  .seven-layers {
    padding: 16px;
    display: flex;
    gap: 8px;
    flex-direction: column;
  }
  
  .layer-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    background: rgba(10,21,32,0.6);
    border-radius: 6px;
    border-left: 3px solid;
    transition: all 0.2s;
  }
  
  .layer-num {
    font-family: var(--font-display);
    font-size: 16px;
    color: var(--text-muted);
    min-width: 20px;
  }
  
  .layer-arabic {
    font-family: Georgia, serif;
    font-size: 18px;
    min-width: 50px;
  }
  
  .layer-latin {
    font-family: var(--font-display);
    font-size: 11px;
    letter-spacing: 0.1em;
    color: var(--text-secondary);
    flex: 1;
  }
  
  .layer-desc {
    font-size: 11px;
    color: var(--text-muted);
    font-style: italic;
  }

  /* Empty state */
  .empty-state {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    color: var(--text-muted);
    padding: 40px;
  }
  
  .empty-arabic {
    font-family: Georgia, serif;
    font-size: 48px;
    color: var(--gold-muted);
    opacity: 0.3;
  }
  
  .empty-text {
    font-family: var(--font-display);
    font-size: 12px;
    letter-spacing: 0.15em;
    text-transform: uppercase;
  }
  
  .empty-sub {
    font-size: 12px;
    font-style: italic;
    opacity: 0.6;
  }
`;

// ===== GEOMETRIC BACKGROUND =====
const GeometricBackground = () => (
  <div className="geometric-bg">
    <svg viewBox="0 0 800 800" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <pattern id="star8" x="0" y="0" width="80" height="80" patternUnits="userSpaceOnUse">
          <g stroke="#c9a227" strokeWidth="0.5" fill="none">
            <polygon points="40,5 52,28 78,28 58,44 66,70 40,55 14,70 22,44 2,28 28,28"/>
            <circle cx="40" cy="40" r="12"/>
            <line x1="40" y1="0" x2="40" y2="80"/>
            <line x1="0" y1="40" x2="80" y2="40"/>
          </g>
        </pattern>
      </defs>
      <rect width="800" height="800" fill="url(#star8)" opacity="0.4"/>
    </svg>
  </div>
);

// ===== AGENT CARD =====
const AgentCard = ({ agent, selected, onClick }) => {
  const nafs = NAFS_LEVELS[agent.nafs_level] || NAFS_LEVELS[1];
  const roleArabic = AGENT_ROLE_ICONS[agent.role] || "وكيل";
  const stateClass = `state-${agent.state}`;
  
  return (
    <div className={`agent-card ${selected ? "selected" : ""}`} onClick={onClick}>
      <div className="agent-header">
        <div className="agent-avatar">{roleArabic[0]}</div>
        <div className="agent-info">
          <div className="agent-name">{agent.name}</div>
          <div className="agent-role">{agent.role} · {roleArabic}</div>
        </div>
        <div className={`agent-state ${stateClass}`}>
          <span>{agent.state}</span>
        </div>
      </div>
      
      <div className="nafs-bar">
        <div className="nafs-label">
          <span style={{ color: nafs.color }}>{nafs.name}</span>
        </div>
        <div className="nafs-track">
          <div className="nafs-fill" style={{
            width: `${(agent.nafs_level / 3) * 100}%`,
            background: nafs.color,
          }}/>
        </div>
        <div style={{ fontSize: 10, color: "var(--text-muted)", fontStyle: "italic", whiteSpace: "nowrap" }}>
          {nafs.desc}
        </div>
      </div>
      
      <div className="agent-stats">
        <div className="stat">
          <span className="stat-value">{agent.total_tasks}</span>
          <span className="stat-label">Tasks</span>
        </div>
        <div className="stat">
          <span className="stat-value" style={{ color: agent.success_rate > 0.7 ? "var(--emerald)" : "var(--ruby)" }}>
            {(agent.success_rate * 100).toFixed(0)}%
          </span>
          <span className="stat-label">Success</span>
        </div>
        <div className="stat">
          <span className="stat-value">{agent.hikmah_count}</span>
          <span className="stat-label">Hikmah</span>
        </div>
      </div>
      
      <div className="agent-tools">
        {(agent.tools || []).slice(0, 4).map(t => (
          <span key={t} className="tool-tag">{t}</span>
        ))}
        {(agent.tools || []).length > 4 && (
          <span className="tool-tag">+{(agent.tools || []).length - 4}</span>
        )}
      </div>
    </div>
  );
};

// ===== SEVEN LAYERS PANEL =====
const SevenLayersPanel = () => {
  const layers = [
    { num: 1, arabic: "سمع", latin: "SAMA'", color: "#3b82f6", desc: "Perception & Input Processing" },
    { num: 2, arabic: "فكر", latin: "FIKR", color: "#8b5cf6", desc: "Cognitive Processing & Analysis" },
    { num: 3, arabic: "ذكر", latin: "DHIKR", color: "#06b6d4", desc: "Memory & Knowledge Storage" },
    { num: 4, arabic: "عقل", latin: "AQL", color: "#c9a227", desc: "Reasoning & Logic Engine" },
    { num: 5, arabic: "حكمة", latin: "HIKMAH", color: "#f59e0b", desc: "Wisdom & Meta-Learning" },
    { num: 6, arabic: "عمل", latin: "AMAL", color: "#10b981", desc: "Action & Execution" },
    { num: 7, arabic: "تفكر", latin: "TAFAKKUR", color: "#ec4899", desc: "Deep Reflection & Self-Improvement" },
  ];
  
  return (
    <div className="seven-layers">
      <div style={{ padding: "0 0 8px", fontFamily: "var(--font-display)", fontSize: 10, letterSpacing: "0.2em", color: "var(--text-muted)", textTransform: "uppercase" }}>
        سبع سماوات · Seven-Layer Architecture
      </div>
      {layers.map(layer => (
        <div key={layer.num} className="layer-item" style={{ borderLeftColor: layer.color }}>
          <div className="layer-num" style={{ color: layer.color }}>{layer.num}</div>
          <div className="layer-arabic" style={{ color: layer.color }}>{layer.arabic}</div>
          <div>
            <div className="layer-latin" style={{ color: layer.color }}>{layer.latin}</div>
            <div className="layer-desc">{layer.desc}</div>
          </div>
        </div>
      ))}
      <div style={{ marginTop: 12, padding: 10, background: "rgba(201,162,39,0.05)", border: "1px solid rgba(201,162,39,0.15)", borderRadius: 6, fontSize: 11, color: "var(--text-muted)", fontStyle: "italic" }}>
        "And the heaven He raised and imposed the balance (Mizan), that you not transgress within the balance." — Quran 55:7-8
      </div>
    </div>
  );
};

// ===== MAIN APP =====
export default function App() {
  const [activeTab, setActiveTab] = useState("agents");
  const [agents, setAgents] = useState([]);
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [ws, setWs] = useState(null);
  const [wsStatus, setWsStatus] = useState("disconnected");
  const [terminalLines, setTerminalLines] = useState([
    { text: "بسم الله الرحمن الرحيم", type: "gold" },
    { text: "MIZAN (ميزان) System Initializing...", type: "" },
    { text: "Architecture: Seven-Layer Quranic AGI", type: "info" },
    { text: "Connecting to backend...", type: "" },
  ]);
  const [taskInput, setTaskInput] = useState("");
  const [sessionId] = useState(() => `session_${Date.now()}`);
  const [showCreateAgent, setShowCreateAgent] = useState(false);
  const [showIntegration, setShowIntegration] = useState(false);
  const [memories, setMemories] = useState([]);
  const [memoryQuery, setMemoryQuery] = useState("");
  const [status, setStatus] = useState(null);
  const [integrations, setIntegrations] = useState([]);
  const [newAgent, setNewAgent] = useState({ name: "", type: "general", model: "claude-opus-4-6", anthropic_api_key: "" });
  const [newIntegration, setNewIntegration] = useState({ name: "", type: "anthropic", config: {} });
  
  const messagesEndRef = useRef(null);
  const clientId = useRef(`client_${Date.now()}`);
  
  const addTerminalLine = useCallback((text, type = "") => {
    setTerminalLines(prev => [...prev.slice(-100), { text, type, ts: Date.now() }]);
  }, []);
  
  // Connect WebSocket
  useEffect(() => {
    const connect = () => {
      try {
        const socket = new WebSocket(`${WS_URL}/${clientId.current}`);
        
        socket.onopen = () => {
          setWsStatus("connected");
          setWs(socket);
          addTerminalLine("✓ WebSocket connected", "gold");
        };
        
        socket.onmessage = (event) => {
          const data = JSON.parse(event.data);
          handleWsMessage(data);
        };
        
        socket.onclose = () => {
          setWsStatus("disconnected");
          setWs(null);
          addTerminalLine("WebSocket disconnected. Reconnecting...", "warn");
          setTimeout(connect, 3000);
        };
        
        socket.onerror = () => {
          addTerminalLine("WebSocket error", "error");
        };
      } catch (e) {
        addTerminalLine(`Connection failed: ${e.message}`, "error");
        setTimeout(connect, 5000);
      }
    };
    
    connect();
  }, []);
  
  const handleWsMessage = useCallback((data) => {
    switch (data.type) {
      case "connected":
        addTerminalLine(`${data.message} · ${data.agents} agents`, "gold");
        loadAgents();
        loadStatus();
        break;
      case "stream":
        setStreamingText(prev => prev + data.chunk);
        break;
      case "response":
        setStreamingText("");
        setStreaming(false);
        setMessages(prev => [...prev, {
          id: Date.now(),
          role: "assistant",
          content: data.content,
          agent: data.agent,
          ts: new Date().toLocaleTimeString(),
        }]);
        addTerminalLine(`✓ Response from ${data.agent}`, "info");
        break;
      case "task_stream":
        addTerminalLine(data.chunk, "");
        break;
      case "task_done":
        addTerminalLine(`✓ Task completed`, "gold");
        loadAgents();
        break;
      case "agent_created":
        addTerminalLine(`✓ Agent created: ${data.agent.name}`, "gold");
        loadAgents();
        break;
    }
  }, [addTerminalLine]);
  
  const loadAgents = async () => {
    try {
      const res = await fetch(`${API_URL}/agents`);
      const data = await res.json();
      setAgents(data.agents || []);
      if (!selectedAgent && data.agents?.length > 0) {
        setSelectedAgent(data.agents[0]);
      }
    } catch (e) {
      addTerminalLine(`Failed to load agents: ${e.message}`, "error");
    }
  };
  
  const loadStatus = async () => {
    try {
      const res = await fetch(`${API_URL}/status`);
      const data = await res.json();
      setStatus(data);
    } catch {}
  };
  
  const loadMemories = async (query = "") => {
    try {
      const res = await fetch(`${API_URL}/memory/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query || "all", limit: 20 }),
      });
      const data = await res.json();
      setMemories(data.results || []);
    } catch {}
  };
  
  const loadIntegrations = async () => {
    try {
      const res = await fetch(`${API_URL}/integrations`);
      const data = await res.json();
      setIntegrations(data.integrations || []);
    } catch {}
  };
  
  useEffect(() => {
    loadAgents();
    const interval = setInterval(() => {
      loadAgents();
      loadStatus();
    }, 5000);
    return () => clearInterval(interval);
  }, []);
  
  useEffect(() => {
    if (activeTab === "memory") loadMemories(memoryQuery);
    if (activeTab === "integrations") loadIntegrations();
  }, [activeTab]);
  
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);
  
  const sendMessage = () => {
    if (!input.trim() || streaming || !ws) return;
    
    const userMsg = { id: Date.now(), role: "user", content: input, ts: new Date().toLocaleTimeString() };
    setMessages(prev => [...prev, userMsg]);
    setStreaming(true);
    setStreamingText("");
    
    ws.send(JSON.stringify({
      type: "chat",
      session_id: sessionId,
      content: input,
      agent_id: selectedAgent?.id,
    }));
    
    setInput("");
    addTerminalLine(`→ ${input.substring(0, 60)}...`, "info");
  };
  
  const runTask = () => {
    if (!taskInput.trim() || !ws) return;
    
    addTerminalLine(`$ ${taskInput}`, "gold");
    ws.send(JSON.stringify({
      type: "task",
      task: taskInput,
      agent_id: selectedAgent?.id,
    }));
    setTaskInput("");
  };
  
  const createAgent = async () => {
    try {
      const res = await fetch(`${API_URL}/agents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newAgent),
      });
      await res.json();
      setShowCreateAgent(false);
      setNewAgent({ name: "", type: "general", model: "claude-opus-4-6", anthropic_api_key: "" });
      loadAgents();
    } catch (e) {
      addTerminalLine(`Error creating agent: ${e.message}`, "error");
    }
  };
  
  const deleteAgent = async (agentId) => {
    if (!confirm("Delete this agent?")) return;
    try {
      await fetch(`${API_URL}/agents/${agentId}`, { method: "DELETE" });
      if (selectedAgent?.id === agentId) setSelectedAgent(null);
      loadAgents();
    } catch {}
  };
  
  const addIntegration = async () => {
    try {
      await fetch(`${API_URL}/integrations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newIntegration),
      });
      setShowIntegration(false);
      loadIntegrations();
    } catch {}
  };

  const renderContent = () => {
    switch (activeTab) {
      case "agents":
        return (
          <>
            <div className="panel-header">
              <div className="panel-title">Agents · وكلاء</div>
              <button className="btn primary" onClick={() => setShowCreateAgent(true)}>
                <Icons.Plus /> New Agent
              </button>
            </div>
            <div style={{ padding: "0 16px 8px", fontSize: 11, color: "var(--text-muted)", fontStyle: "italic" }}>
              "And sufficient is Allah as a Trustee (Wakil)" — 4:81
            </div>
            <div className="agents-grid">
              {agents.map(agent => (
                <div key={agent.id} style={{ position: "relative" }}>
                  <AgentCard
                    agent={agent}
                    selected={selectedAgent?.id === agent.id}
                    onClick={() => setSelectedAgent(agent)}
                  />
                  <button
                    className="btn danger"
                    style={{ position: "absolute", top: 10, right: 10, padding: "4px 6px" }}
                    onClick={e => { e.stopPropagation(); deleteAgent(agent.id); }}
                  >
                    <Icons.Trash />
                  </button>
                </div>
              ))}
              {agents.length === 0 && (
                <div className="empty-state" style={{ gridColumn: "1/-1" }}>
                  <div className="empty-arabic">وكيل</div>
                  <div className="empty-text">No agents initialized</div>
                  <div className="empty-sub">Ensure the backend is running</div>
                </div>
              )}
            </div>
          </>
        );
      
      case "chat":
        return (
          <div className="chat-container">
            <div className="chat-header">
              <Icons.Chat />
              <span style={{ fontFamily: "var(--font-display)", fontSize: 11, letterSpacing: "0.1em", color: "var(--gold)" }}>
                CHAT · محادثة
              </span>
              <select
                className="chat-agent-select"
                value={selectedAgent?.id || ""}
                onChange={e => {
                  const agent = agents.find(a => a.id === e.target.value);
                  setSelectedAgent(agent);
                }}
              >
                <option value="">Select Agent</option>
                {agents.map(a => (
                  <option key={a.id} value={a.id}>{a.name} ({a.role})</option>
                ))}
              </select>
              {selectedAgent && (
                <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8, fontSize: 11, color: "var(--text-muted)" }}>
                  <span style={{ fontFamily: "Georgia", color: "var(--gold)", fontSize: 14 }}>
                    {AGENT_ROLE_ICONS[selectedAgent.role] || "وكيل"}
                  </span>
                  <span>Nafs: {NAFS_LEVELS[selectedAgent.nafs_level]?.latin}</span>
                </div>
              )}
            </div>
            
            <div className="chat-messages">
              {messages.length === 0 && !streaming && (
                <div className="empty-state">
                  <div className="empty-arabic">تكلم</div>
                  <div className="empty-text">Begin the Conversation</div>
                  <div className="empty-sub">"And He taught Adam the names of all things" — 2:31</div>
                </div>
              )}
              
              {messages.map(msg => (
                <div key={msg.id} className={`message ${msg.role}`}>
                  <div className={`msg-avatar ${msg.role}`}>
                    {msg.role === "user" ? "أنت" : (msg.agent?.[0] || "م")}
                  </div>
                  <div>
                    <div className={`msg-bubble ${msg.role}`}>
                      {msg.content}
                    </div>
                    <div className="msg-meta">
                      {msg.role === "assistant" ? msg.agent : "You"} · {msg.ts}
                    </div>
                  </div>
                </div>
              ))}
              
              {streaming && streamingText && (
                <div className="message assistant">
                  <div className="msg-avatar agent">
                    {selectedAgent?.name?.[0] || "م"}
                  </div>
                  <div>
                    <div className="msg-bubble agent">
                      {streamingText}
                      <span className="streaming-cursor"/>
                    </div>
                  </div>
                </div>
              )}
              
              <div ref={messagesEndRef}/>
            </div>
            
            <div className="chat-input-area">
              <textarea
                className="chat-input"
                placeholder="Type your message... (Enter to send, Shift+Enter for new line)"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                  }
                }}
                rows={1}
                style={{ minHeight: 38 }}
              />
              <button className="send-btn" onClick={sendMessage} disabled={streaming || !input.trim() || !ws}>
                <Icons.Send />
              </button>
            </div>
          </div>
        );
      
      case "terminal":
        return (
          <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column", padding: 12, gap: 12 }}>
            <div className="panel-header" style={{ padding: "8px 12px" }}>
              <div className="panel-title">Task Runner · منفذ المهام</div>
              <span style={{ fontSize: 10, color: "var(--text-muted)", fontStyle: "italic" }}>
                "By the pen and what they write" — 68:1
              </span>
            </div>
            
            <div className="terminal" style={{ flex: 1 }}>
              <div className="terminal-header">
                <div className="terminal-dots">
                  <div className="terminal-dot" style={{ background: "#ef4444" }}/>
                  <div className="terminal-dot" style={{ background: "#f59e0b" }}/>
                  <div className="terminal-dot" style={{ background: "#10b981" }}/>
                </div>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-muted)", marginLeft: 8 }}>
                  mizan@aql ~ %
                </span>
                <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--text-muted)" }}>
                  Agent: {selectedAgent?.name || "None"}
                </span>
              </div>
              <div className="terminal-body">
                {terminalLines.map((line, i) => (
                  <div key={i} className={`terminal-line ${line.type}`}>
                    {line.type === "gold" ? <span className="terminal-prompt">❯ </span> : null}
                    {line.text}
                  </div>
                ))}
              </div>
              <div className="terminal-input-row">
                <span className="terminal-prompt" style={{ fontFamily: "var(--font-mono)", fontSize: 12, padding: "0 8px", color: "var(--gold)" }}>❯</span>
                <input
                  className="terminal-input"
                  placeholder="Enter task for agent... (e.g., 'search for latest AI papers')"
                  value={taskInput}
                  onChange={e => setTaskInput(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && runTask()}
                />
                <button className="btn primary" style={{ marginRight: 4, padding: "4px 10px" }} onClick={runTask}>
                  Run
                </button>
              </div>
            </div>
          </div>
        );
      
      case "memory":
        return (
          <>
            <div className="panel-header">
              <div className="panel-title">Memory · ذاكرة (Dhikr)</div>
              <div style={{ display: "flex", gap: 8 }}>
                <input
                  className="form-input"
                  style={{ width: 200, padding: "5px 10px" }}
                  placeholder="Search memories..."
                  value={memoryQuery}
                  onChange={e => setMemoryQuery(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && loadMemories(memoryQuery)}
                />
                <button className="btn" onClick={() => loadMemories(memoryQuery)}>Search</button>
                <button className="btn" onClick={async () => {
                  await fetch(`${API_URL}/memory/consolidate`, { method: "POST" });
                  addTerminalLine("Memory consolidated (Nisyan applied)", "gold");
                  loadMemories();
                }}>Consolidate</button>
              </div>
            </div>
            
            <div style={{ padding: "4px 16px 8px", fontSize: 11, color: "var(--text-muted)", fontStyle: "italic" }}>
              "And We have certainly made the Quran easy for remembrance (Dhikr)" — 54:17
            </div>
            
            <div className="memory-panel">
              {memories.length === 0 && (
                <div className="empty-state">
                  <div className="empty-arabic">ذكر</div>
                  <div className="empty-text">No memories found</div>
                  <div className="empty-sub">Search or run tasks to populate memory</div>
                </div>
              )}
              {memories.map(mem => (
                <div key={mem.id} className="memory-item">
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                    <span className={`memory-type-badge type-${mem.type}`}>{mem.type}</span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-muted)" }}>
                      {mem.agent_id ? `Agent: ${mem.agent_id.substring(0, 8)}` : "System"}
                    </span>
                    <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--text-muted)" }}>
                      Importance: {(mem.importance * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>
                    {typeof mem.content === "string" ? mem.content : JSON.stringify(mem.content)}
                  </div>
                  {mem.tags?.length > 0 && (
                    <div style={{ marginTop: 6, display: "flex", gap: 4, flexWrap: "wrap" }}>
                      {mem.tags.map(t => <span key={t} className="tool-tag">{t}</span>)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </>
        );
      
      case "architecture":
        return (
          <>
            <div className="panel-header">
              <div className="panel-title">Architecture · هندسة (Mizan)</div>
            </div>
            <div style={{ overflow: "auto", flex: 1 }}>
              <SevenLayersPanel />
              
              {status && (
                <div style={{ padding: "0 16px 16px" }}>
                  <div style={{ fontFamily: "var(--font-display)", fontSize: 10, letterSpacing: "0.2em", color: "var(--text-muted)", textTransform: "uppercase", marginBottom: 10 }}>
                    System State · حال النظام
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}>
                    {[
                      { label: "Agents", value: status.agents?.total, arabic: "وكلاء" },
                      { label: "Active", value: status.agents?.active, arabic: "نشط" },
                      { label: "Sessions", value: status.sessions, arabic: "جلسات" },
                      { label: "Connections", value: status.connections, arabic: "اتصالات" },
                    ].map(s => (
                      <div key={s.label} className="stat" style={{ padding: 12 }}>
                        <span style={{ fontFamily: "Georgia", fontSize: 20, color: "var(--gold)", display: "block" }}>
                          {s.arabic}
                        </span>
                        <span className="stat-value" style={{ fontSize: 20 }}>{s.value ?? "—"}</span>
                        <span className="stat-label">{s.label}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </>
        );
      
      case "integrations":
        return (
          <>
            <div className="panel-header">
              <div className="panel-title">Integrations · تكاملات</div>
              <button className="btn primary" onClick={() => setShowIntegration(true)}>
                <Icons.Plus /> Add Integration
              </button>
            </div>
            <div style={{ padding: 16, overflow: "auto", flex: 1 }}>
              {integrations.length === 0 && (
                <div className="empty-state">
                  <div className="empty-arabic">وصل</div>
                  <div className="empty-text">No integrations configured</div>
                  <div className="empty-sub">Connect AI providers, MCP servers, webhooks</div>
                </div>
              )}
              {integrations.map(int => (
                <div key={int.id} className="memory-item">
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span className="memory-type-badge type-semantic">{int.type}</span>
                    <span style={{ fontFamily: "var(--font-display)", fontSize: 12, color: "var(--text-primary)" }}>{int.name}</span>
                    <span style={{ marginLeft: "auto", fontSize: 10, color: int.enabled ? "var(--emerald)" : "var(--ruby)" }}>
                      {int.enabled ? "Enabled" : "Disabled"}
                    </span>
                    <button className="btn danger" onClick={async () => {
                      await fetch(`${API_URL}/integrations/${int.id}`, { method: "DELETE" });
                      loadIntegrations();
                    }} style={{ padding: "3px 6px" }}>
                      <Icons.Trash />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </>
        );
      
      default:
        return null;
    }
  };
  
  return (
    <>
      <style>{styles}</style>
      <GeometricBackground />
      
      {/* Header */}
      <div className="header">
        <div className="logo">
          <svg className="logo-symbol" viewBox="0 0 36 36">
            <circle cx="18" cy="18" r="16" fill="none" stroke="rgba(201,162,39,0.3)" strokeWidth="1"/>
            <polygon points="18,4 22,14 34,14 24,21 27,32 18,26 9,32 12,21 2,14 14,14" fill="none" stroke="#c9a227" strokeWidth="1.5"/>
            <circle cx="18" cy="18" r="4" fill="rgba(201,162,39,0.2)" stroke="#c9a227" strokeWidth="1"/>
          </svg>
          <div className="logo-text">
            <div className="logo-arabic">ميزان</div>
            <div className="logo-latin">MIZAN · AGI SYSTEM</div>
          </div>
        </div>
        
        <div className="header-verse">
          "And the heaven He raised and imposed the balance (Mizan)" — Quran 55:7
        </div>
        
        <div className="header-status">
          <div className="status-pill">
            <div className={`status-dot ${wsStatus !== "connected" ? "style" : ""}`} 
                 style={{ background: wsStatus === "connected" ? "var(--emerald)" : "var(--ruby)" }}/>
            {wsStatus === "connected" ? "ONLINE" : "OFFLINE"}
          </div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-muted)" }}>
            {agents.length} وكيل
          </div>
        </div>
      </div>
      
      {/* Stats bar */}
      {status && (
        <div className="stats-bar">
          <div className="stat-chip">
            <Icons.Agent />
            Agents: <span className="stat-chip-value">{status.agents?.total}</span>
          </div>
          <div className="stat-chip">
            <Icons.Zap />
            Active: <span className="stat-chip-value">{status.agents?.active}</span>
          </div>
          <div className="stat-chip">
            <Icons.Scale />
            Layer: <span className="stat-chip-value">Mizan v1.0</span>
          </div>
        </div>
      )}
      
      {/* Main layout */}
      <div className="main-layout">
        {/* Sidebar */}
        <div className="sidebar">
          <div className="nav-section">
            <div className="nav-section-label">Core · جوهر</div>
            {[
              { id: "agents", label: "Agents", arabic: "وكلاء", icon: <Icons.Agent /> },
              { id: "chat", label: "Chat", arabic: "محادثة", icon: <Icons.Chat /> },
              { id: "terminal", label: "Tasks", arabic: "مهام", icon: <Icons.Terminal /> },
            ].map(item => (
              <div
                key={item.id}
                className={`nav-item ${activeTab === item.id ? "active" : ""}`}
                onClick={() => setActiveTab(item.id)}
              >
                {item.icon}
                <span>{item.label}</span>
                <span className="nav-item-arabic">{item.arabic}</span>
              </div>
            ))}
          </div>
          
          <div className="nav-section">
            <div className="nav-section-label">Knowledge · علم</div>
            {[
              { id: "memory", label: "Memory", arabic: "ذاكرة", icon: <Icons.Memory /> },
              { id: "architecture", label: "Architecture", arabic: "هندسة", icon: <Icons.Brain /> },
            ].map(item => (
              <div
                key={item.id}
                className={`nav-item ${activeTab === item.id ? "active" : ""}`}
                onClick={() => setActiveTab(item.id)}
              >
                {item.icon}
                <span>{item.label}</span>
                <span className="nav-item-arabic">{item.arabic}</span>
              </div>
            ))}
          </div>
          
          <div className="nav-section">
            <div className="nav-section-label">System · نظام</div>
            {[
              { id: "integrations", label: "Integrations", arabic: "وصل", icon: <Icons.Globe /> },
              { id: "settings", label: "Settings", arabic: "إعدادات", icon: <Icons.Settings /> },
            ].map(item => (
              <div
                key={item.id}
                className={`nav-item ${activeTab === item.id ? "active" : ""}`}
                onClick={() => setActiveTab(item.id)}
              >
                {item.icon}
                <span>{item.label}</span>
                <span className="nav-item-arabic">{item.arabic}</span>
              </div>
            ))}
          </div>
          
          {/* Selected agent info */}
          {selectedAgent && (
            <div style={{ marginTop: "auto", padding: "12px 12px 8px", borderTop: "1px solid rgba(30,58,85,0.5)" }}>
              <div style={{ fontSize: 9, letterSpacing: "0.2em", color: "var(--text-muted)", textTransform: "uppercase", fontFamily: "var(--font-display)", marginBottom: 6 }}>
                Active Agent
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{ fontFamily: "Georgia", fontSize: 18, color: "var(--gold)" }}>
                  {AGENT_ROLE_ICONS[selectedAgent.role]?.[0] || "و"}
                </div>
                <div>
                  <div style={{ fontSize: 12, color: "var(--text-primary)", fontFamily: "var(--font-display)" }}>
                    {selectedAgent.name}
                  </div>
                  <div style={{ fontSize: 10, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                    {NAFS_LEVELS[selectedAgent.nafs_level]?.name} · {NAFS_LEVELS[selectedAgent.nafs_level]?.latin}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
        
        {/* Content */}
        <div className="content">
          {renderContent()}
        </div>
      </div>
      
      {/* Create Agent Modal */}
      {showCreateAgent && (
        <div className="modal-overlay" onClick={() => setShowCreateAgent(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-title">
              <span style={{ fontFamily: "Georgia", fontSize: 22, color: "var(--gold)" }}>وكيل</span>
              Create New Agent
            </div>
            
            <div className="form-group">
              <label className="form-label">Agent Name · اسم</label>
              <input className="form-input" placeholder="e.g., Al-Hafiz, Al-Mundhir..."
                value={newAgent.name} onChange={e => setNewAgent({...newAgent, name: e.target.value})}/>
            </div>
            
            <div className="form-group">
              <label className="form-label">Agent Type · نوع</label>
              <select className="form-select" value={newAgent.type}
                onChange={e => setNewAgent({...newAgent, type: e.target.value})}>
                <option value="general">General (وكيل)</option>
                <option value="browser">Browser / Mubashir (مبشر)</option>
                <option value="research">Research / Mundhir (منذر)</option>
                <option value="code">Code / Katib (كاتب)</option>
                <option value="communication">Communication / Rasul (رسول)</option>
              </select>
            </div>
            
            <div className="form-group">
              <label className="form-label">AI Model · نموذج</label>
              <select className="form-select" value={newAgent.model}
                onChange={e => setNewAgent({...newAgent, model: e.target.value})}>
                <option value="claude-opus-4-6">Claude Opus 4.6</option>
                <option value="claude-sonnet-4-6">Claude Sonnet 4.6</option>
                <option value="claude-haiku-4-5-20251001">Claude Haiku 4.5</option>
                <option value="gpt-4o">GPT-4o</option>
                <option value="ollama/llama3">Ollama Llama 3</option>
              </select>
            </div>
            
            <div className="form-group">
              <label className="form-label">Anthropic API Key (optional)</label>
              <input className="form-input" type="password" placeholder="sk-ant-..."
                value={newAgent.anthropic_api_key}
                onChange={e => setNewAgent({...newAgent, anthropic_api_key: e.target.value})}/>
            </div>
            
            <div className="modal-footer">
              <button className="btn" onClick={() => setShowCreateAgent(false)}>Cancel</button>
              <button className="btn primary" onClick={createAgent} disabled={!newAgent.name}>
                Create Agent
              </button>
            </div>
          </div>
        </div>
      )}
      
      {/* Add Integration Modal */}
      {showIntegration && (
        <div className="modal-overlay" onClick={() => setShowIntegration(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-title">
              <Icons.Globe /> Add Integration
            </div>
            
            <div className="form-group">
              <label className="form-label">Name</label>
              <input className="form-input" placeholder="Integration name"
                value={newIntegration.name}
                onChange={e => setNewIntegration({...newIntegration, name: e.target.value})}/>
            </div>
            
            <div className="form-group">
              <label className="form-label">Type</label>
              <select className="form-select" value={newIntegration.type}
                onChange={e => setNewIntegration({...newIntegration, type: e.target.value})}>
                <option value="anthropic">Anthropic Claude</option>
                <option value="openai">OpenAI</option>
                <option value="ollama">Ollama (Local)</option>
                <option value="mcp">MCP Server</option>
                <option value="webhook">Webhook</option>
                <option value="email">Email (IMAP/SMTP)</option>
                <option value="custom">Custom API</option>
              </select>
            </div>
            
            <div className="modal-footer">
              <button className="btn" onClick={() => setShowIntegration(false)}>Cancel</button>
              <button className="btn primary" onClick={addIntegration}>Add</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
