// src/App.tsx - Solana Liquidity Stream Tracker
import { Ticker } from "./components/Ticker";
import { ShieldCheck, Zap, TrendingUp, Database } from "lucide-react";

function App() {
  return (
    <div className="min-h-screen w-full bg-[#050505] text-white selection:bg-green-500 selection:text-black">
      {/* Hero */}
      <section className="relative pt-20 pb-32 px-6 overflow-hidden">
        <div className="max-w-7xl mx-auto text-center relative z-10">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-green-500/10 border border-green-500/20 text-green-500 text-xs font-bold mb-8 uppercase tracking-widest">
            <Zap size={14} /> Real-time on-chain market data
          </div>

          <h1 className="text-5xl md:text-7xl font-black mb-6 tracking-tighter leading-none">
            SOLANA LIQUIDITY
            <br />
            <span className="text-green-500 drop-shadow-[0_0_15px_rgba(34,197,94,0.5)]">
              STREAM TRACKER
            </span>
          </h1>

          <p className="text-white/60 max-w-2xl mx-auto text-lg mb-12">
            A transparent market-data monitor for pump.fun activity. It
            subscribes to on-chain trade events over WebSocket, parses
            transaction metadata, and persists each event through a versioned
            SQLite schema. No wallets. No strategies. Just the stream.
          </p>

          <div className="max-w-xl mx-auto">
            <Ticker />
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="px-6 pb-32">
        <div className="max-w-5xl mx-auto grid md:grid-cols-2 gap-6">
          {[
            {
              icon: Zap,
              title: "Stream-first",
              body: "A logsSubscribe WebSocket connection watches the program and feeds every notification to the parser.",
            },
            {
              icon: TrendingUp,
              title: "Resilient",
              body: "Dropped streams reconnect automatically with jittered exponential backoff; malformed frames are skipped, not fatal.",
            },
            {
              icon: Database,
              title: "Persisted",
              body: "Every parsed event lands in a SQLite schema (init_db.py) with signature-dedupe built in.",
            },
            {
              icon: ShieldCheck,
              title: "Zero-alpha by design",
              body: "This repository contains no wallet logic and no key material. It observes the market; it does not act on it.",
            },
          ].map((card) => (
            <div
              key={card.title}
              className="bg-white/[0.03] border border-white/10 rounded-2xl p-6 text-left"
            >
              <card.icon className="text-green-500 mb-4" size={28} />
              <h3 className="font-bold mb-2">{card.title}</h3>
              <p className="text-white/60 text-sm">{card.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/10 py-10 px-6">
        <div className="max-w-5xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4 text-sm text-white/40">
          <span>solana-liquidity-stream-tracker</span>
          <span>market data · stdlib python · react frontend</span>
        </div>
      </footer>
    </div>
  );
}

export default App;
