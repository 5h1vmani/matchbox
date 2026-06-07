/* Matchbox — Offers. The offer ledger plus an honest own-pool salary benchmark.
   Negotiation here is STATUS-TRACKING only: the counter-offer draft is written by
   the user in Claude Code and voice-checked there. This screen never invents
   strategy or a fabricated percentile — when the pool has no match it shows the
   backend's honest basis line verbatim. */
import { useEffect, useState } from "react";
import type { Application } from "../types";
import { listApplications } from "../api/client";
import * as oapi from "../api/offers";
import { cx } from "../lib/derive";
import { Icon } from "../ui/icon";

type AppLite = { id: string; company: string; role: string };

// Forward transitions only. Received can move to negotiating or close either way;
// negotiating can close either way; accepted/declined are terminal.
const NEXT: Record<string, oapi.OfferStatus[]> = {
  received: ["negotiating", "accepted", "declined"],
  negotiating: ["accepted", "declined"],
  accepted: [],
  declined: [],
};

const STATUS_LABEL: Record<string, string> = {
  received: "Received",
  negotiating: "Negotiating",
  accepted: "Accepted",
  declined: "Declined",
};

const STATUS_ICON: Record<oapi.OfferStatus, string> = {
  received: "check",
  negotiating: "arrow-right",
  accepted: "party-popper",
  declined: "x",
};

function money(n: number | null, currency: string | null): string {
  if (n === null) return "—";
  const formatted = n.toLocaleString("en-US");
  return currency ? `${currency} ${formatted}` : formatted;
}

function num(s: string): number | null {
  const t = s.trim();
  if (!t) return null;
  const n = Number(t.replace(/[, ]/g, ""));
  return Number.isFinite(n) ? n : null;
}

function BenchmarkPanel({ offer }: { offer: oapi.Offer }) {
  const [bm, setBm] = useState<oapi.Benchmark | null>(null);
  useEffect(() => {
    if (offer.base === null) return;
    void oapi
      .getBenchmark(offer.base, undefined, offer.currency ?? undefined)
      .then(setBm);
  }, [offer.base, offer.currency]);

  if (offer.base === null) return null;
  if (!bm) return <div className="sub" style={{ marginTop: 10 }}>Checking your pool…</div>;

  const honest = bm.confidence === "none" || bm.sampleSize === 0;

  return (
    <div
      style={{
        marginTop: 12,
        paddingTop: 12,
        borderTop: "1px solid var(--border)",
        display: "flex",
        flexDirection: "column",
        gap: 6,
      }}
    >
      <div className="sec-h" style={{ margin: 0 }}>
        <span className="t" style={{ fontSize: 13.5 }}>Benchmark</span>
        <span
          className={cx("badge", honest ? "muted" : "ok")}
          style={{ marginLeft: "auto" }}
        >
          {honest ? "no data" : `${bm.confidence} confidence`}
        </span>
      </div>

      {honest ? (
        <p className="sub" style={{ margin: 0 }}>{bm.basis}</p>
      ) : (
        <>
          <div style={{ display: "flex", gap: 22, flexWrap: "wrap" }}>
            <div>
              <div className="mono" style={{ fontSize: 20, fontWeight: 600 }}>
                {bm.percentile === null ? "—" : `p${bm.percentile}`}
              </div>
              <div className="sub">percentile</div>
            </div>
            <div>
              <div className="mono" style={{ fontSize: 20, fontWeight: 600 }}>
                {bm.range
                  ? `${money(bm.range.low, bm.currency)} – ${money(bm.range.high, bm.currency)}`
                  : "—"}
              </div>
              <div className="sub">p25 – p75</div>
            </div>
            <div>
              <div className="mono" style={{ fontSize: 20, fontWeight: 600 }}>{bm.sampleSize}</div>
              <div className="sub">sample size</div>
            </div>
          </div>
          <p className="sub" style={{ margin: 0 }}>{bm.basis}</p>
        </>
      )}
    </div>
  );
}

// Client-side, NOT a stored computation: a transparent weighted read across
// offers so they can be eyeballed side by side. Fixed weights, computed in the
// browser every render; nothing is persisted.
const WEIGHTS = { base: 1, bonus: 0.6, equity: 0.4 };

function clientScore(o: oapi.Offer): number {
  const equityPresent = o.equity && o.equity.trim() ? 1 : 0;
  return (
    (o.base ?? 0) * WEIGHTS.base +
    (o.bonus ?? 0) * WEIGHTS.bonus +
    equityPresent * (o.base ?? 0) * WEIGHTS.equity
  );
}

function Comparison({ offers, label }: { offers: oapi.Offer[]; label: (id: number) => string }) {
  if (offers.length < 2) return null;
  const scored = offers
    .filter((o) => o.base !== null)
    .map((o) => ({ o, score: clientScore(o) }))
    .sort((a, b) => b.score - a.score);
  if (scored.length < 2) return null;
  const max = scored[0].score || 1;

  return (
    <section className="card" style={{ padding: "16px 20px", marginBottom: 18 }}>
      <div className="sec-h">
        <span className="t">Weighted comparison</span>
        <span className="badge muted" style={{ marginLeft: "auto" }}>
          client-side, not a stored computation
        </span>
      </div>
      <p className="sub" style={{ marginTop: -4, marginBottom: 12 }}>
        A rough read computed in your browser right now (base ×{WEIGHTS.base}, bonus ×{WEIGHTS.bonus},
        equity-present ×{WEIGHTS.equity} of base). Nothing here is saved.
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {scored.map(({ o, score }) => (
          <div key={o.id} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13.5 }}>
            <span style={{ width: 180, flex: "0 0 auto" }}>{label(o.applicationId)}</span>
            <div style={{ flex: 1, height: 8, background: "var(--muted)", borderRadius: 999 }}>
              <div
                style={{
                  width: `${Math.round((score / max) * 100)}%`,
                  height: "100%",
                  background: "var(--primary)",
                  borderRadius: 999,
                }}
              />
            </div>
            <span className="mono" style={{ width: 90, textAlign: "right", flex: "0 0 auto" }}>
              {money(o.base, o.currency)}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

interface AddFormProps {
  apps: AppLite[];
  onAdd: (offer: oapi.Offer) => void;
  flash: (msg: string) => void;
}

function AddForm({ apps, onAdd, flash }: AddFormProps) {
  const [open, setOpen] = useState(false);
  const [appId, setAppId] = useState("");
  const [base, setBase] = useState("");
  const [bonus, setBonus] = useState("");
  const [equity, setEquity] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [location, setLocation] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);

  const reset = () => {
    setAppId("");
    setBase("");
    setBonus("");
    setEquity("");
    setCurrency("USD");
    setLocation("");
    setNotes("");
  };

  const submit = async () => {
    const numericAppId = Number(appId);
    if (!appId || !Number.isFinite(numericAppId)) {
      flash("Pick an application first.");
      return;
    }
    setBusy(true);
    const offer = await oapi.createOffer({
      applicationId: numericAppId,
      base: num(base),
      bonus: num(bonus),
      equity: equity.trim() || null,
      currency: currency.trim() || null,
      location: location.trim() || null,
      notes: notes.trim() || null,
    });
    setBusy(false);
    if (offer) {
      onAdd(offer);
      flash("Offer added.");
      reset();
      setOpen(false);
    } else {
      flash("Could not add the offer.");
    }
  };

  if (!open) {
    return (
      <button className="btn" onClick={() => setOpen(true)} disabled={apps.length === 0}>
        <Icon name="plus" size={16} /> Add offer
      </button>
    );
  }

  return (
    <section className="card" style={{ padding: "16px 20px", marginBottom: 18 }}>
      <div className="sec-h">
        <span className="t">Add an offer</span>
        <button className="btn ghost tiny" style={{ marginLeft: "auto" }} onClick={() => setOpen(false)}>
          <Icon name="x" size={14} /> Cancel
        </button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <label className="fld">
          <span className="fld__l">Application</span>
          <select className="inp" value={appId} onChange={(e) => setAppId(e.target.value)}>
            <option value="">Select an application…</option>
            {apps.map((a) => (
              <option key={a.id} value={a.id}>
                {a.company} — {a.role}
              </option>
            ))}
          </select>
        </label>

        <label className="fld">
          <span className="fld__l">Currency</span>
          <input className="inp" value={currency} onChange={(e) => setCurrency(e.target.value)} placeholder="USD" />
        </label>

        <label className="fld">
          <span className="fld__l">Base</span>
          <input className="inp" value={base} onChange={(e) => setBase(e.target.value)} placeholder="e.g. 165000" inputMode="numeric" />
        </label>

        <label className="fld">
          <span className="fld__l">Bonus</span>
          <input className="inp" value={bonus} onChange={(e) => setBonus(e.target.value)} placeholder="e.g. 15000" inputMode="numeric" />
        </label>

        <label className="fld">
          <span className="fld__l">Equity</span>
          <input className="inp" value={equity} onChange={(e) => setEquity(e.target.value)} placeholder="e.g. 0.05% / $40k RSU" />
        </label>

        <label className="fld">
          <span className="fld__l">Location</span>
          <input className="inp" value={location} onChange={(e) => setLocation(e.target.value)} placeholder="e.g. Remote (US)" />
        </label>

        <label className="fld" style={{ gridColumn: "1 / -1" }}>
          <span className="fld__l">Notes</span>
          <input className="inp" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Anything to remember" />
        </label>
      </div>

      <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
        <button className="btn primary" disabled={busy} onClick={() => void submit()}>
          <Icon name="check" size={16} /> Save offer
        </button>
        <button className="btn ghost" disabled={busy} onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
    </section>
  );
}

interface OfferCardProps {
  offer: oapi.Offer;
  label: string;
  onStatus: (id: number, status: oapi.OfferStatus) => void;
  busy: boolean;
}

function OfferCard({ offer, label, onStatus, busy }: OfferCardProps) {
  const transitions = NEXT[offer.status] ?? [];
  const terminal = transitions.length === 0;

  return (
    <section className="card" style={{ padding: "16px 20px" }}>
      <div className="sec-h" style={{ marginBottom: 12 }}>
        <span className="t">{label}</span>
        <span
          className={cx("badge", offer.status === "accepted" ? "ok" : "muted")}
          style={{ marginLeft: "auto" }}
        >
          {STATUS_LABEL[offer.status] ?? offer.status}
        </span>
      </div>

      <div style={{ display: "flex", gap: 22, flexWrap: "wrap" }}>
        <div>
          <div className="mono" style={{ fontSize: 22, fontWeight: 600 }}>{money(offer.base, offer.currency)}</div>
          <div className="sub">base</div>
        </div>
        <div>
          <div className="mono" style={{ fontSize: 22, fontWeight: 600 }}>{money(offer.bonus, offer.currency)}</div>
          <div className="sub">bonus</div>
        </div>
        <div>
          <div className="mono" style={{ fontSize: 22, fontWeight: 600 }}>{money(offer.totalComp, offer.currency)}</div>
          <div className="sub">total comp</div>
        </div>
        <div>
          <div className="mono" style={{ fontSize: 22, fontWeight: 600 }}>{offer.equity ?? "—"}</div>
          <div className="sub">equity</div>
        </div>
      </div>

      {(offer.location || offer.notes) && (
        <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 4 }}>
          {offer.location && <div className="sub">Location: {offer.location}</div>}
          {offer.notes && <div className="sub">{offer.notes}</div>}
        </div>
      )}

      <BenchmarkPanel offer={offer} />

      <div style={{ marginTop: 14, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        {terminal ? (
          <span className="sub" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <Icon name={offer.status === "accepted" ? "check-circle" : "x"} size={15} />
            {STATUS_LABEL[offer.status] ?? offer.status} — no further changes.
          </span>
        ) : (
          transitions.map((t) => (
            <button
              key={t}
              className={cx("btn tiny", t === "accepted" ? "primary" : "ghost")}
              disabled={busy}
              onClick={() => onStatus(offer.id, t)}
            >
              <Icon name={STATUS_ICON[t]} size={14} /> {STATUS_LABEL[t]}
            </button>
          ))
        )}
      </div>

      {offer.status === "negotiating" && (
        <p className="sub" style={{ marginTop: 10 }}>
          This tracks status only. Write your counter-offer draft in Claude Code — it is grounded and
          voice-checked there. No strategy text is generated here.
        </p>
      )}
    </section>
  );
}

export function Offers({ flash }: { flash: (msg: string) => void }) {
  const [offers, setOffers] = useState<oapi.Offer[]>([]);
  const [apps, setApps] = useState<AppLite[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    void Promise.all([oapi.listOffers(), listApplications()]).then(([o, a]) => {
      if (!alive) return;
      setOffers(o);
      setApps((a as Application[]).map((x) => ({ id: x.id, company: x.company, role: x.role })));
      setLoaded(true);
    });
    return () => {
      alive = false;
    };
  }, []);

  const labelFor = (applicationId: number): string => {
    const app = apps.find((a) => String(a.id) === String(applicationId));
    return app ? `${app.company} — ${app.role}` : `Application #${applicationId}`;
  };

  const onAdd = (offer: oapi.Offer) => setOffers((prev) => [offer, ...prev]);

  const onStatus = async (id: number, status: oapi.OfferStatus) => {
    setBusyId(id);
    const updated = await oapi.setOfferStatus(id, status);
    setBusyId(null);
    if (updated) {
      setOffers((prev) => prev.map((o) => (o.id === id ? updated : o)));
      flash(`Offer marked ${STATUS_LABEL[status].toLowerCase()}.`);
    } else {
      flash("Could not update the offer.");
    }
  };

  return (
    <div>
      <div className="phead">
        <div>
          <h1>Offers</h1>
          <p className="sub">Track offers and read them against your own pool. Honest numbers, no invented strategy.</p>
        </div>
        <AddForm apps={apps} onAdd={onAdd} flash={flash} />
      </div>

      <Comparison offers={offers} label={labelFor} />

      {!loaded ? (
        <div className="sub" style={{ padding: 20 }}>Loading…</div>
      ) : offers.length === 0 ? (
        <section className="card" style={{ padding: "16px 20px" }}>
          <p className="sub" style={{ margin: 0 }}>No offers yet.</p>
        </section>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {offers.map((o) => (
            <OfferCard
              key={o.id}
              offer={o}
              label={labelFor(o.applicationId)}
              onStatus={(id, status) => void onStatus(id, status)}
              busy={busyId === o.id}
            />
          ))}
        </div>
      )}
    </div>
  );
}
