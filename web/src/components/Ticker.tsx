import { useEffect, useState } from "react";

type TradeRow = {
  signature: string;
  trader?: string;
  isBuy?: boolean;
  solAmount?: number | string;
};

type Status = "idle" | "live" | "error";

export const Ticker = () => {
  const [trades, setTrades] = useState<TradeRow[]>([]);
  const [status, setStatus] = useState<Status>("idle");

  useEffect(() => {
    const streamUrl = import.meta.env.VITE_PUMP_PORTAL_WS;
    const mint = import.meta.env.VITE_TOKEN_MINT;
    if (!streamUrl) {
      setStatus("error");
      return;
    }

    let ws: WebSocket | undefined;
    let retry: ReturnType<typeof setTimeout> | undefined;

    const open = () => {
      ws = new WebSocket(streamUrl);
      ws.onopen = () => {
        setStatus("live");
        if (mint) {
          ws!.send(JSON.stringify({ method: "subscribeTokenTrade", keys: [mint] }));
        } else {
          ws!.send(JSON.stringify({ method: "subscribeNewTrades" }));
        }
      };
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.signature) {
            setTrades((prev) => [data as TradeRow, ...prev].slice(0, 5));
          }
        } catch {
          /* ignore malformed frames */
        }
      };
      ws.onclose = () => {
        setStatus("idle");
        retry = setTimeout(open, 3000);
      };
      ws.onerror = () => ws?.close();
    };

    open();
    return () => {
      if (retry) clearTimeout(retry);
      ws?.close();
    };
  }, []);

  return (
    <div className="bg-black/50 p-4 rounded-xl border border-green-500/30">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-green-500 font-bold uppercase text-xs">Live Trades</h3>
        <span className="text-[10px] uppercase tracking-widest text-white/40">
          {status}
        </span>
      </div>
      <div className="space-y-2">
        {trades.length === 0 && (
          <div className="text-xs text-white/40">waiting for events…</div>
        )}
        {trades.map((tx, i) => (
          <div key={i} className="text-xs flex justify-between animate-pulse">
            <span className="text-white/60 truncate max-w-[60%]">
              {tx.trader ?? tx.signature.slice(0, 12)}
            </span>
            <span className={tx.isBuy === false ? "text-red-400" : "text-green-500"}>
              {tx.isBuy === false ? "sell" : "buy"}
              {tx.solAmount !== undefined ? ` · ${tx.solAmount} SOL` : ""}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};
