// ui/src/SovereignOrb.tsx

import { useEffect, useRef, useState, useCallback } from "react";

type OrbState = "idle" | "listening" | "thinking" | "speaking";
type Role = "friend" | "assistant" | "companion" | "mentor";
type Style = "empathetic" | "honest" | "hype" | "calm";

interface Message {
  role: "user" | "assistant";
  content: string;
  timestamp: number;
  isVoice?: boolean;
  isProactive?: boolean;
  imageData?: string;
}

const WS_URL = "ws://localhost:8765";

// ── Canvas Orb Renderer ────────────────────────────────────────────────────

function useOrbCanvas(state: OrbState, canvasRef: React.RefObject<HTMLCanvasElement>) {
  const animRef = useRef<number>(0);
  const timeRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d")!;
    const W = canvas.width;
    const H = canvas.height;
    const cx = W / 2;
    const cy = H / 2;

    const PARTICLE_COUNT = 180;
    const particles = Array.from({ length: PARTICLE_COUNT }, (_, i) => ({
      angle: (i / PARTICLE_COUNT) * Math.PI * 2,
      radius: 80 + Math.random() * 60,
      baseRadius: 80 + Math.random() * 60,
      speed: 0.002 + Math.random() * 0.004,
      size: 0.5 + Math.random() * 2.5,
      opacity: 0.3 + Math.random() * 0.7,
      layer: Math.floor(Math.random() * 3),
      drift: Math.random() * Math.PI * 2,
    }));

    const FILAMENT_COUNT = 40;
    const filaments = Array.from({ length: FILAMENT_COUNT }, () => ({
      angle: Math.random() * Math.PI * 2,
      length: 20 + Math.random() * 50,
      speed: 0.003 + Math.random() * 0.005,
      opacity: 0.2 + Math.random() * 0.5,
      width: 0.3 + Math.random() * 1,
    }));

    let floatOffset = 0;
    let floatDir = 1;

    function getStateParams() {
      switch (state) {
        case "speaking":
          return { scale: 1 + 0.15 * Math.sin(timeRef.current * 8), glow: 1.4, speed: 1.8, brightness: 1.3 };
        case "thinking":
          return { scale: 1.05, glow: 1.1, speed: 3.0, brightness: 1.0 };
        case "listening":
          return { scale: 1 + 0.08 * Math.sin(timeRef.current * 4), glow: 1.2, speed: 1.2, brightness: 1.1 };
        default:
          return { scale: 1 + 0.02 * Math.sin(timeRef.current * 0.8), glow: 0.8, speed: 0.6, brightness: 0.85 };
      }
    }

    function drawFrame(ts: number) {
      timeRef.current = ts / 1000;
      const t = timeRef.current;
      const { scale, glow, speed, brightness } = getStateParams();

      ctx.clearRect(0, 0, W, H);

      floatOffset += 0.008 * floatDir;
      if (Math.abs(floatOffset) > 6) floatDir *= -1;
      const orbY = cy + (state === "idle" ? floatOffset : 0);

      ctx.save();
      ctx.translate(cx, orbY);
      ctx.scale(scale, scale);

      const outerGrad = ctx.createRadialGradient(0, 0, 60, 0, 0, 160);
      outerGrad.addColorStop(0, `rgba(200, 100, 0, 0.0)`);
      outerGrad.addColorStop(0.4, `rgba(180, 80, 0, ${0.06 * glow})`);
      outerGrad.addColorStop(0.7, `rgba(160, 60, 0, ${0.12 * glow})`);
      outerGrad.addColorStop(1, `rgba(100, 30, 0, 0.0)`);
      ctx.beginPath();
      ctx.arc(0, 0, 160, 0, Math.PI * 2);
      ctx.fillStyle = outerGrad;
      ctx.fill();

      const coreGrad = ctx.createRadialGradient(-15, -15, 0, 0, 0, 80);
      coreGrad.addColorStop(0, `rgba(255, 200, 80, ${0.95 * brightness})`);
      coreGrad.addColorStop(0.3, `rgba(220, 120, 20, ${0.9 * brightness})`);
      coreGrad.addColorStop(0.6, `rgba(160, 60, 0, ${0.85 * brightness})`);
      coreGrad.addColorStop(0.85, `rgba(80, 20, 0, ${0.8 * brightness})`);
      coreGrad.addColorStop(1, `rgba(20, 5, 0, 0.9)`);
      ctx.beginPath();
      ctx.arc(0, 0, 80, 0, Math.PI * 2);
      ctx.fillStyle = coreGrad;
      ctx.fill();

      filaments.forEach((f) => {
        f.angle += f.speed * speed * 0.016;
        const x1 = Math.cos(f.angle) * 10;
        const y1 = Math.sin(f.angle) * 10;
        const x2 = Math.cos(f.angle) * (10 + f.length);
        const y2 = Math.sin(f.angle) * (10 + f.length);
        const pulse = 0.5 + 0.5 * Math.sin(t * 3 + f.angle * 2);
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.strokeStyle = `rgba(255, 160, 40, ${f.opacity * pulse * brightness})`;
        ctx.lineWidth = f.width;
        ctx.stroke();
      });

      particles.forEach((p) => {
        p.angle += p.speed * speed;
        p.drift += 0.01;
        const radiusPulse = p.baseRadius + 8 * Math.sin(t * 2 + p.drift);
        const x = Math.cos(p.angle) * radiusPulse;
        const y = Math.sin(p.angle) * radiusPulse * 0.85;
        const colors = [
          `rgba(255, 180, 60, `,
          `rgba(200, 100, 20, `,
          `rgba(150, 60, 10, `,
        ];
        const pulse = 0.6 + 0.4 * Math.sin(t * 4 + p.angle * 3);
        ctx.beginPath();
        ctx.arc(x, y, p.size, 0, Math.PI * 2);
        ctx.fillStyle = colors[p.layer] + `${p.opacity * pulse * brightness})`;
        ctx.fill();
      });

      const ringOpacity = state === "thinking" ? 0.6 : 0.25;
      const ringRotation = state === "thinking" ? t * 1.5 : t * 0.2;
      ctx.save();
      ctx.rotate(ringRotation);
      ctx.beginPath();
      ctx.arc(0, 0, 130, 0, Math.PI * 1.7);
      ctx.strokeStyle = `rgba(180, 100, 20, ${ringOpacity})`;
      ctx.lineWidth = 0.8;
      ctx.setLineDash([4, 8]);
      ctx.stroke();
      ctx.restore();

      ctx.save();
      ctx.rotate(-ringRotation * 0.7);
      ctx.beginPath();
      ctx.arc(0, 0, 110, 0, Math.PI * 1.3);
      ctx.strokeStyle = `rgba(220, 140, 40, ${ringOpacity * 0.6})`;
      ctx.lineWidth = 0.5;
      ctx.setLineDash([2, 6]);
      ctx.stroke();
      ctx.restore();

      ctx.setLineDash([]);
      ctx.restore();

      ctx.strokeStyle = "rgba(180, 100, 20, 0.4)";
      ctx.lineWidth = 0.8;
      const corners: [number, number][] = [[20, 20], [W - 20, 20], [20, H - 20], [W - 20, H - 20]];
      const dirs: [number, number][] = [[1, 1], [-1, 1], [1, -1], [-1, -1]];
      corners.forEach(([x, y], i) => {
        const [dx, dy] = dirs[i];
        ctx.beginPath();
        ctx.moveTo(x, y + dy * 15);
        ctx.lineTo(x, y);
        ctx.lineTo(x + dx * 15, y);
        ctx.stroke();
      });

      animRef.current = requestAnimationFrame(drawFrame);
    }

    animRef.current = requestAnimationFrame(drawFrame);
    return () => cancelAnimationFrame(animRef.current);
  }, [state, canvasRef]);
}


// ── Shared button style helper ─────────────────────────────────────────────

function orbBtn(active = false, danger = false): React.CSSProperties {
  return {
    background: active
      ? (danger ? "rgba(180,40,10,0.4)" : "rgba(180,100,10,0.35)")
      : "rgba(180,80,10,0.12)",
    border: `0.5px solid rgba(180,100,20,${active ? 0.8 : 0.4})`,
    borderRadius: 6,
    padding: "8px 14px",
    color: active ? "#ffb84a" : "#c87830",
    cursor: "pointer",
    fontSize: "11px",
    letterSpacing: "0.1em",
    fontFamily: "'Courier New', monospace",
    transition: "all 0.15s",
    whiteSpace: "nowrap" as const,
  };
}


// ── Main Component ─────────────────────────────────────────────────────────

export default function SovereignOrb() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [orbState, setOrbState] = useState<OrbState>("idle");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [connected, setConnected] = useState(false);
  const [status, setStatus] = useState("Connecting...");
  const [voiceLoopActive, setVoiceLoopActive] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [liveTranscript, setLiveTranscript] = useState("");
  const [activeRole, setActiveRole] = useState<Role>("friend");
  const [activeStyle, setActiveStyle] = useState<Style>("empathetic");
  const [showSettings, setShowSettings] = useState(false);
  const [typing, setTyping] = useState(false);
  const [proactiveEnabled, setProactiveEnabled] = useState(true);
  const [needsSetup, setNeedsSetup] = useState(false);
  const [setupName, setSetupName] = useState("");
  const [setupPrompt, setSetupPrompt] = useState("Hi. I'm SOVEREIGN. What should I call you?");
  const proactiveFlagRef = useRef(false);
  const wsRef = useRef<WebSocket | null>(null);
  const recognitionRef = useRef<any>(null);
  const liveTranscriptRef = useRef("");
  const voiceLoopRef = useRef(false);
  const canSendRef = useRef(false);
  const errorCountRef = useRef(0);
  const errorWindowRef = useRef(0);

  useOrbCanvas(orbState, canvasRef as React.RefObject<HTMLCanvasElement>);

  // ── WebSocket ────────────────────────────────────────────────────────────

  const connect = useCallback(() => {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => { setConnected(true); setStatus("Online"); canSendRef.current = true; };

    ws.onmessage = (e) => {
      const data = JSON.parse(e.data);
      switch (data.type) {
        case "needs_setup":
          setNeedsSetup(true);
          setSetupPrompt(data.message || "What should I call you?");
          setOrbState("idle");
          break;
        case "ready":
          setNeedsSetup(false);
          setOrbState("idle");
          setMessages([{ role: "assistant", content: data.message, timestamp: Date.now() }]);
          break;
        case "orb_state":
          setOrbState(data.state as OrbState);
          break;
        case "voice_transcript":
          setMessages(prev => [...prev, {
            role: "user", content: data.transcript,
            timestamp: Date.now(), isVoice: true
          }]);
          break;
        case "response":
          setTyping(false);
          setOrbState(data.orb_state as OrbState);
          setMessages(prev => [...prev, {
            role: "assistant", content: data.content, timestamp: Date.now(),
            imageData: data.image_data,
          }]);
          setTimeout(() => setOrbState("idle"), 3000);
          break;
        case "typing":
          setTyping(true);
          setOrbState("thinking");
          break;
        case "proactive":
          // Next stream of chunks is an unprompted message
          proactiveFlagRef.current = true;
          break;
        case "response_chunk":
          setTyping(false);
          setMessages(prev => [...prev, {
            role: "assistant",
            content: data.content,
            timestamp: Date.now(),
            isProactive: proactiveFlagRef.current,
            imageData: data.is_final ? data.image_data : undefined,
          }]);
          if (data.is_final) {
            proactiveFlagRef.current = false;
            setOrbState((data.orb_state as OrbState) || "idle");
            setTimeout(() => setOrbState("idle"), 3000);
          } else {
            setOrbState("thinking");
          }
          break;
        case "ack":
          break;
        case "error":
          setOrbState("idle");
          setStatus(`Error: ${data.message}`);
          setTimeout(() => setStatus("Online"), 4000);
          break;
      }
    };

    ws.onclose = () => {
      canSendRef.current = false;
      voiceLoopRef.current = false;
      setConnected(false);
      setVoiceLoopActive(false);
      setIsRecording(false);
      try { recognitionRef.current?.stop(); } catch (_) { /* ignore */ }
      setStatus("Reconnecting...");
      setTimeout(connect, 3000);
    };

    ws.onerror = () => setStatus("Connection failed — is the Python backend running?");
  }, []);

  useEffect(() => {
    connect();
    return () => wsRef.current?.close();
  }, [connect]);

  const ws = () => wsRef.current;
  const canSend = connected && ws()?.readyState === WebSocket.OPEN;

  // ── Text send ────────────────────────────────────────────────────────────

  const send = useCallback(() => {
    if (!input.trim() || !canSend) return;
    const content = input.trim();
    setInput("");
    setMessages(prev => [...prev, { role: "user", content, timestamp: Date.now() }]);
    setOrbState("thinking");
    ws()!.send(JSON.stringify({ type: "message", content, mode: "text" }));
  }, [input, canSend]);

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  };

  // ── Voice — Web Speech API (real-time live transcription) ───────────────────

  const sendTranscript = useCallback((transcript: string) => {
    if (!transcript.trim() || !canSendRef.current || !wsRef.current) return;
    setMessages(prev => [...prev, { role: "user", content: transcript, timestamp: Date.now(), isVoice: true }]);
    setOrbState("thinking");
    wsRef.current.send(JSON.stringify({ type: "message", content: transcript, mode: "voice" }));
  }, []);

  const startRecognition = useCallback(() => {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) { setStatus("Voice not supported — use Chrome or Edge"); return; }

    const rec = new SR();
    rec.lang = "en-US";
    rec.interimResults = true;  // partial results as you speak
    rec.continuous = false;

    rec.onstart = () => { setIsRecording(true); setOrbState("listening"); setLiveTranscript(""); liveTranscriptRef.current = ""; };

    rec.onresult = (e: any) => {
      let interim = "", final = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) final += t; else interim += t;
      }
      const current = final || interim;
      setLiveTranscript(current);
      liveTranscriptRef.current = current;
    };

    rec.onend = () => {
      setIsRecording(false);
      const transcript = liveTranscriptRef.current.trim();
      setLiveTranscript(""); liveTranscriptRef.current = "";
      if (transcript) {
        errorCountRef.current = 0;
        sendTranscript(transcript);
      } else {
        setOrbState("idle");
      }
      if (voiceLoopRef.current) {
        const now = Date.now();
        if (now - errorWindowRef.current > 10000) {
          errorCountRef.current = 0;
          errorWindowRef.current = now;
        }
        if (errorCountRef.current < 4) {
          setTimeout(() => startRecognition(), 600);
        } else {
          setStatus("Mic: too many errors — voice loop paused");
          voiceLoopRef.current = false;
          setVoiceLoopActive(false);
        }
      }
    };

    rec.onerror = (e: any) => {
      errorCountRef.current++;
      if (e.error === "not-allowed" || e.error === "audio-capture") {
        setStatus(`Mic blocked: check browser permissions (${e.error})`);
        voiceLoopRef.current = false;
        setVoiceLoopActive(false);
      } else if (e.error !== "no-speech") {
        setStatus(`Mic error: ${e.error}`);
      }
      setIsRecording(false);
      setLiveTranscript("");
      setOrbState("idle");
      // onend fires after onerror — restart logic is handled there
    };

    recognitionRef.current = rec;
    rec.start();
  }, [sendTranscript]);

  const stopRecognition = useCallback(() => {
    voiceLoopRef.current = false;
    setVoiceLoopActive(false);
    recognitionRef.current?.stop();
    setIsRecording(false); setLiveTranscript(""); setOrbState("idle");
  }, []);

  const toggleMic = useCallback(() => {
    if (isRecording) stopRecognition();
    else { voiceLoopRef.current = false; setVoiceLoopActive(false); startRecognition(); }
  }, [isRecording, startRecognition, stopRecognition]);

  const toggleVoiceLoop = useCallback(() => {
    if (voiceLoopActive) stopRecognition();
    else { voiceLoopRef.current = true; setVoiceLoopActive(true); startRecognition(); }
  }, [voiceLoopActive, startRecognition, stopRecognition]);

  // ── Role / Style ─────────────────────────────────────────────────────────

  const changeRole = useCallback((role: Role) => {
    if (!canSend) return;
    ws()!.send(JSON.stringify({ type: "set_role", role }));
    setActiveRole(role);
  }, [canSend]);

  const changeStyle = useCallback((style: Style) => {
    if (!canSend) return;
    ws()!.send(JSON.stringify({ type: "set_style", style }));
    setActiveStyle(style);
  }, [canSend]);

  const toggleProactive = useCallback(() => {
    if (!canSend) return;
    const next = !proactiveEnabled;
    ws()!.send(JSON.stringify({ type: "proactive_toggle", enabled: next }));
    setProactiveEnabled(next);
  }, [canSend, proactiveEnabled]);

  const proactiveNow = useCallback(() => {
    if (!canSend) return;
    ws()!.send(JSON.stringify({ type: "proactive_now" }));
  }, [canSend]);

  const submitName = useCallback(() => {
    const name = setupName.trim();
    if (!name || !canSend) return;
    ws()!.send(JSON.stringify({ type: "set_name", name }));
    setSetupName("");
  }, [setupName, canSend]);

  // ── Render ────────────────────────────────────────────────────────────────

  const ROLES: Role[] = ["friend", "assistant", "companion", "mentor"];
  const STYLES: Style[] = ["empathetic", "honest", "hype", "calm"];

  return (
    <div style={{
      display: "flex", flexDirection: "column", alignItems: "center",
      width: "100vw", height: "100vh", background: "#050200",
      color: "#e8a050", fontFamily: "'Courier New', monospace", overflow: "hidden",
      position: "relative"
    }}>

      {/* First-run name setup */}
      {needsSetup && (
        <div style={{
          position: "absolute", inset: 0, zIndex: 100,
          background: "rgba(5,2,0,0.97)",
          display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center",
          gap: 24, padding: "0 32px", textAlign: "center",
        }}>
          <div style={{
            fontSize: "10px", letterSpacing: "0.3em",
            color: "rgba(200,120,40,0.6)",
          }}>
            SOVEREIGN OS · FIRST RUN
          </div>
          <div style={{
            fontSize: "18px", color: "rgba(240,160,60,0.95)",
            maxWidth: 420, lineHeight: 1.5,
          }}>
            {setupPrompt}
          </div>
          <input
            autoFocus
            value={setupName}
            onChange={e => setSetupName(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter") submitName(); }}
            placeholder="your name"
            maxLength={40}
            style={{
              width: "100%", maxWidth: 320,
              background: "rgba(180,80,10,0.08)",
              border: "0.5px solid rgba(180,100,20,0.5)",
              borderRadius: 8, padding: "12px 18px",
              color: "#e8a050", fontSize: "15px",
              fontFamily: "'Courier New', monospace",
              outline: "none", textAlign: "center",
              letterSpacing: "0.05em",
            }}
          />
          <button
            onClick={submitName}
            disabled={!setupName.trim() || !canSend}
            style={{
              ...orbBtn(false),
              padding: "10px 28px", fontSize: "12px",
              opacity: setupName.trim() && canSend ? 1 : 0.35,
            }}
          >
            CONTINUE
          </button>
          <div style={{
            fontSize: "10px", opacity: 0.4, maxWidth: 360,
            lineHeight: 1.5, marginTop: 12,
          }}>
            this is what i'll call you. you can change it later in settings.
          </div>
        </div>
      )}

      {/* Status bar */}
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0,
        display: "flex", justifyContent: "space-between", alignItems: "center",
        padding: "12px 24px", borderBottom: "0.5px solid rgba(180,100,20,0.3)",
        fontSize: "11px", color: "rgba(200,120,40,0.7)", zIndex: 10
      }}>
        <span style={{ letterSpacing: "0.2em" }}>SOVEREIGN OS</span>
        <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <span style={{
            width: 6, height: 6, borderRadius: "50%",
            background: connected ? "#4ade80" : "#ef4444",
            display: "inline-block"
          }} />
          {status}
        </span>
        <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{ opacity: 0.6, textTransform: "uppercase" }}>{orbState}</span>
          <button
            onClick={() => setShowSettings(s => !s)}
            style={{ ...orbBtn(showSettings), padding: "4px 10px", fontSize: "10px" }}
          >
            {showSettings ? "CLOSE" : "SETTINGS"}
          </button>
        </span>
      </div>

      {/* Settings panel */}
      {showSettings && (
        <div style={{
          position: "absolute", top: 44, right: 0, left: 0,
          background: "rgba(8,4,0,0.97)",
          borderBottom: "0.5px solid rgba(180,100,20,0.3)",
          padding: "16px 24px", zIndex: 9, display: "flex",
          flexDirection: "column", gap: 14,
        }}>
          <div>
            <div style={{ fontSize: "9px", letterSpacing: "0.2em", opacity: 0.5, marginBottom: 8 }}>ROLE</div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {ROLES.map(r => (
                <button key={r} onClick={() => changeRole(r)} style={orbBtn(activeRole === r)}>
                  {r.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div style={{ fontSize: "9px", letterSpacing: "0.2em", opacity: 0.5, marginBottom: 8 }}>STYLE</div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {STYLES.map(s => (
                <button key={s} onClick={() => changeStyle(s)} style={orbBtn(activeStyle === s)}>
                  {s.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div style={{ fontSize: "9px", letterSpacing: "0.2em", opacity: 0.5, marginBottom: 8 }}>UNPROMPTED MESSAGES</div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button onClick={toggleProactive} style={orbBtn(proactiveEnabled)}>
                {proactiveEnabled ? "ON" : "OFF"}
              </button>
              <button onClick={proactiveNow} style={orbBtn(false)} disabled={!canSend}>
                TRIGGER NOW
              </button>
            </div>
            <div style={{ fontSize: "10px", opacity: 0.4, marginTop: 6 }}>
              SOVEREIGN reaches out the next time you come back after a long gap (6+ hours) — like a friend who's been thinking about you. Use TRIGGER NOW to demo on demand.
            </div>
          </div>
          <div style={{ fontSize: "10px", opacity: 0.4 }}>
            Role controls personality. Style controls tone. Both affect response length.
          </div>
        </div>
      )}

      {/* Orb */}
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <canvas ref={canvasRef} width={400} height={400} style={{ display: "block" }} />
      </div>

      {/* Live transcript — appears below orb as you speak */}
      {(isRecording || liveTranscript) && (
        <div style={{
          position: "absolute", bottom: 160, left: "50%", transform: "translateX(-50%)",
          background: "rgba(5,2,0,0.88)", border: "0.5px solid rgba(255,160,40,0.5)",
          borderRadius: 10, padding: "10px 20px", maxWidth: 440, minWidth: 180,
          textAlign: "center", fontSize: "14px", color: "#ffcc70", letterSpacing: "0.02em",
          lineHeight: 1.5,
        }}>
          {liveTranscript || <span style={{ opacity: 0.4 }}>Listening...</span>}
        </div>
      )}

      {/* Messages */}
      <div style={{
        position: "absolute", right: 24, top: "50%", transform: "translateY(-50%)",
        width: 280, maxHeight: "60vh", overflowY: "auto", display: "flex",
        flexDirection: "column", gap: 10
      }}>
        {messages.slice(-6).map((m, i) => (
          <div key={i} style={{
            background: m.role === "user"
              ? "rgba(180,80,10,0.15)" : "rgba(100,50,0,0.2)",
            border: `0.5px solid rgba(180,100,20,${m.role === "assistant" ? 0.4 : 0.2})`,
            borderRadius: 8, padding: "8px 12px",
            fontSize: "12px", lineHeight: 1.5,
            color: m.role === "assistant" ? "rgba(240,160,60,0.95)" : "rgba(200,120,40,0.8)"
          }}>
            <div style={{ fontSize: "9px", opacity: 0.5, marginBottom: 4, letterSpacing: "0.1em" }}>
              {m.role === "user"
                ? (m.isVoice ? "YOU (VOICE)" : "YOU")
                : (m.isProactive ? "SOVEREIGN · UNPROMPTED" : "SOVEREIGN")}
            </div>
            {m.imageData && (
              <img
                src={m.imageData}
                alt="timetable"
                style={{ width: "100%", borderRadius: 6, marginBottom: 6, display: "block" }}
              />
            )}
            {m.content}
          </div>
        ))}
        {typing && (
          <div style={{
            background: "rgba(100,50,0,0.2)",
            border: "0.5px solid rgba(180,100,20,0.4)",
            borderRadius: 8, padding: "8px 12px",
            display: "inline-flex", alignItems: "center", gap: 4,
            alignSelf: "flex-start",
          }}>
            <span style={{ fontSize: "9px", opacity: 0.5, letterSpacing: "0.1em", marginRight: 6 }}>
              SOVEREIGN
            </span>
            <span style={{
              width: 5, height: 5, borderRadius: "50%",
              background: "rgba(255,180,60,0.9)",
              animation: "typingDot 1.2s infinite",
            }} />
            <span style={{
              width: 5, height: 5, borderRadius: "50%",
              background: "rgba(255,180,60,0.9)",
              animation: "typingDot 1.2s infinite 0.2s",
            }} />
            <span style={{
              width: 5, height: 5, borderRadius: "50%",
              background: "rgba(255,180,60,0.9)",
              animation: "typingDot 1.2s infinite 0.4s",
            }} />
          </div>
        )}
      </div>

      {/* Input bar */}
      <div style={{
        width: "100%", maxWidth: 640, padding: "0 24px 28px",
        display: "flex", flexDirection: "column", gap: 10,
      }}>
        {/* Role/style quick bar */}
        <div style={{ display: "flex", gap: 6, justifyContent: "center", flexWrap: "wrap" }}>
          {ROLES.map(r => (
            <button key={r} onClick={() => changeRole(r)}
              style={{ ...orbBtn(activeRole === r), padding: "4px 10px", fontSize: "10px" }}>
              {r.toUpperCase()}
            </button>
          ))}
        </div>

        {/* Text input + buttons */}
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Type or use mic..."
            style={{
              flex: 1, background: "rgba(180,80,10,0.08)",
              border: "0.5px solid rgba(180,100,20,0.4)",
              borderRadius: 8, padding: "10px 16px",
              color: "#e8a050", fontSize: "13px",
              fontFamily: "'Courier New', monospace", outline: "none"
            }}
          />

          {/* One-shot mic — click to start, click again to stop */}
          <button
            onClick={toggleMic}
            disabled={!canSend || voiceLoopActive}
            title={isRecording ? "Stop recording" : "Click to speak"}
            style={{
              ...orbBtn(isRecording),
              padding: "10px 14px",
              opacity: canSend && !voiceLoopActive ? 1 : 0.35,
              fontSize: "16px",
            }}
          >
            {isRecording ? "⏹" : "🎤"}
          </button>

          {/* Continuous voice loop */}
          <button
            onClick={toggleVoiceLoop}
            disabled={!canSend}
            title={voiceLoopActive ? "Stop continuous listening" : "Start continuous listening"}
            style={{
              ...orbBtn(voiceLoopActive, voiceLoopActive),
              padding: "10px 12px",
              opacity: canSend ? 1 : 0.35,
              fontSize: "14px",
            }}
          >
            {voiceLoopActive ? "⏹" : "🔁"}
          </button>

          <button
            onClick={send}
            disabled={!canSend || !input.trim()}
            style={{
              ...orbBtn(false),
              padding: "10px 18px",
              opacity: canSend && input.trim() ? 1 : 0.35,
            }}
          >
            SEND
          </button>
        </div>
      </div>
    </div>
  );
}
