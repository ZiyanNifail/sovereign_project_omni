// ui/src/SovereignOrb.tsx
// The animated amber orb — idle floats, speaking pulses, thinking spins

import { useEffect, useRef, useState, useCallback } from "react";

type OrbState = "idle" | "listening" | "thinking" | "speaking";

interface Message {
  role: "user" | "assistant";
  content: string;
  timestamp: number;
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

    // Particle system
    const PARTICLE_COUNT = 180;
    const particles = Array.from({ length: PARTICLE_COUNT }, (_, i) => ({
      angle: (i / PARTICLE_COUNT) * Math.PI * 2,
      radius: 80 + Math.random() * 60,
      baseRadius: 80 + Math.random() * 60,
      speed: 0.002 + Math.random() * 0.004,
      size: 0.5 + Math.random() * 2.5,
      opacity: 0.3 + Math.random() * 0.7,
      layer: Math.floor(Math.random() * 3), // 0=inner, 1=mid, 2=outer
      drift: Math.random() * Math.PI * 2,
    }));

    // Inner filaments
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
        default: // idle
          return { scale: 1 + 0.02 * Math.sin(timeRef.current * 0.8), glow: 0.8, speed: 0.6, brightness: 0.85 };
      }
    }

    function drawFrame(ts: number) {
      timeRef.current = ts / 1000;
      const t = timeRef.current;
      const { scale, glow, speed, brightness } = getStateParams();

      ctx.clearRect(0, 0, W, H);

      // Floating offset
      floatOffset += 0.008 * floatDir;
      if (Math.abs(floatOffset) > 6) floatDir *= -1;
      const orbY = cy + (state === "idle" ? floatOffset : 0);

      ctx.save();
      ctx.translate(cx, orbY);
      ctx.scale(scale, scale);

      // ── Outer glow ring ──────────────────────────────────────────────────
      const outerGrad = ctx.createRadialGradient(0, 0, 60, 0, 0, 160);
      outerGrad.addColorStop(0, `rgba(200, 100, 0, ${0.0})`);
      outerGrad.addColorStop(0.4, `rgba(180, 80, 0, ${0.06 * glow})`);
      outerGrad.addColorStop(0.7, `rgba(160, 60, 0, ${0.12 * glow})`);
      outerGrad.addColorStop(1, `rgba(100, 30, 0, ${0.0})`);
      ctx.beginPath();
      ctx.arc(0, 0, 160, 0, Math.PI * 2);
      ctx.fillStyle = outerGrad;
      ctx.fill();

      // ── Core sphere ───────────────────────────────────────────────────────
      const coreGrad = ctx.createRadialGradient(-15, -15, 0, 0, 0, 80);
      coreGrad.addColorStop(0, `rgba(255, 200, 80, ${0.95 * brightness})`);
      coreGrad.addColorStop(0.3, `rgba(220, 120, 20, ${0.9 * brightness})`);
      coreGrad.addColorStop(0.6, `rgba(160, 60, 0, ${0.85 * brightness})`);
      coreGrad.addColorStop(0.85, `rgba(80, 20, 0, ${0.8 * brightness})`);
      coreGrad.addColorStop(1, `rgba(20, 5, 0, ${0.9})`);
      ctx.beginPath();
      ctx.arc(0, 0, 80, 0, Math.PI * 2);
      ctx.fillStyle = coreGrad;
      ctx.fill();

      // ── Inner filaments ───────────────────────────────────────────────────
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

      // ── Particles ─────────────────────────────────────────────────────────
      particles.forEach((p) => {
        p.angle += p.speed * speed;
        p.drift += 0.01;
        const radiusPulse = p.baseRadius + 8 * Math.sin(t * 2 + p.drift);
        const x = Math.cos(p.angle) * radiusPulse;
        const y = Math.sin(p.angle) * radiusPulse * 0.85; // slight ellipse

        const colors = [
          `rgba(255, 180, 60, `,   // inner — bright gold
          `rgba(200, 100, 20, `,   // mid — orange
          `rgba(150, 60, 10, `,    // outer — dark amber
        ];
        const pulse = 0.6 + 0.4 * Math.sin(t * 4 + p.angle * 3);

        ctx.beginPath();
        ctx.arc(x, y, p.size, 0, Math.PI * 2);
        ctx.fillStyle = colors[p.layer] + `${p.opacity * pulse * brightness})`;
        ctx.fill();
      });

      // ── HUD ring ─────────────────────────────────────────────────────────
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

      // Inner ring
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

      // ── Corner HUD elements ───────────────────────────────────────────────
      ctx.strokeStyle = "rgba(180, 100, 20, 0.4)";
      ctx.lineWidth = 0.8;
      const corners = [[20, 20], [W - 20, 20], [20, H - 20], [W - 20, H - 20]];
      const dirs = [[1, 1], [-1, 1], [1, -1], [-1, -1]];
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


// ── Main Component ─────────────────────────────────────────────────────────

export default function SovereignOrb() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [orbState, setOrbState] = useState<OrbState>("idle");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [connected, setConnected] = useState(false);
  const [status, setStatus] = useState("Connecting...");
  const wsRef = useRef<WebSocket | null>(null);

  useOrbCanvas(orbState, canvasRef as React.RefObject<HTMLCanvasElement>);

  // ── WebSocket ────────────────────────────────────────────────────────────

  const connect = useCallback(() => {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      setStatus("Online");
    };

    ws.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.type === "ready") {
        setOrbState("idle");
        setMessages([{ role: "assistant", content: data.message, timestamp: Date.now() }]);
      } else if (data.type === "orb_state") {
        setOrbState(data.state as OrbState);
      } else if (data.type === "response") {
        setOrbState(data.orb_state as OrbState);
        setMessages(prev => [...prev, { role: "assistant", content: data.content, timestamp: Date.now() }]);
        // Return to idle after speaking
        setTimeout(() => setOrbState("idle"), 3000);
      } else if (data.type === "error") {
        setOrbState("idle");
        setStatus(`Error: ${data.message}`);
      }
    };

    ws.onclose = () => {
      setConnected(false);
      setStatus("Reconnecting...");
      setTimeout(connect, 3000);
    };

    ws.onerror = () => {
      setStatus("Connection failed — is the Python backend running?");
    };
  }, []);

  useEffect(() => {
    connect();
    return () => wsRef.current?.close();
  }, [connect]);

  // ── Send Message ─────────────────────────────────────────────────────────

  const send = useCallback(() => {
    if (!input.trim() || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    const content = input.trim();
    setInput("");
    setMessages(prev => [...prev, { role: "user", content, timestamp: Date.now() }]);
    setOrbState("thinking");
    wsRef.current.send(JSON.stringify({ type: "message", content, mode: "text" }));
  }, [input]);

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  };

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div style={{
      display: "flex", flexDirection: "column", alignItems: "center",
      width: "100vw", height: "100vh", background: "#050200",
      color: "#e8a050", fontFamily: "'Courier New', monospace", overflow: "hidden",
      position: "relative"
    }}>
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
        <span style={{ letterSpacing: "0.1em", textTransform: "uppercase" }}>
          {orbState}
        </span>
      </div>

      {/* Orb */}
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <canvas
          ref={canvasRef}
          width={400}
          height={400}
          style={{ display: "block" }}
        />
      </div>

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
              {m.role === "user" ? "YOU" : "SOVEREIGN"}
            </div>
            {m.content}
          </div>
        ))}
      </div>

      {/* Input */}
      <div style={{
        width: "100%", maxWidth: 600, padding: "0 24px 28px",
        display: "flex", gap: 10, alignItems: "center"
      }}>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Speak to SOVEREIGN..."
          style={{
            flex: 1, background: "rgba(180,80,10,0.08)",
            border: "0.5px solid rgba(180,100,20,0.4)",
            borderRadius: 8, padding: "10px 16px",
            color: "#e8a050", fontSize: "13px",
            fontFamily: "'Courier New', monospace",
            outline: "none"
          }}
        />
        <button
          onClick={send}
          disabled={!connected || !input.trim()}
          style={{
            background: "rgba(180,80,10,0.2)",
            border: "0.5px solid rgba(180,100,20,0.5)",
            borderRadius: 8, padding: "10px 20px",
            color: "#e8a050", cursor: "pointer",
            fontSize: "12px", letterSpacing: "0.1em",
            opacity: connected && input.trim() ? 1 : 0.4
          }}
        >
          SEND
        </button>
      </div>
    </div>
  );
}
