/* Matchbox — Sources. The job-board connectors: each row points an ATS board
   (Greenhouse, Lever, Ashby…) at a company, and a scan is a real, live network
   fetch. Honest throughout — a bad slug is not validated away up front; it
   surfaces as a calm warning after a scan (the "visible status" pattern). The
   no-auth aggregators and an optional bring-your-own-key Adzuna feed round it
   out. Nothing is invented: counts and statuses come straight from the server. */
import { useEffect, useState } from "react";
import * as api from "../api/sources";
import * as jobsApi from "../api/jobs";
import { cx } from "../lib/derive";
import { Icon } from "../ui/icon";

function fmtWhen(iso: string | null): string {
  if (!iso) return "never";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

function SourceRow({
  source,
  flash,
  onChange,
  onRemove,
}: {
  source: api.Source;
  flash: (msg: string) => void;
  onChange: (s: api.Source) => void;
  onRemove: (id: number) => void;
}) {
  const [scanning, setScanning] = useState(false);
  const [busy, setBusy] = useState(false);

  const enabled = source.enabled !== 0;

  const scan = async () => {
    setScanning(true);
    const res = await api.scanSource(source.id);
    setScanning(false);
    if (res) {
      onChange(res.source);
      const inserted = res.result["inserted"];
      const count = typeof inserted === "number" ? inserted : 0;
      flash(`Scanned ${source.company}: added ${count} job${count === 1 ? "" : "s"}.`);
    } else {
      flash(`Scan of ${source.company} failed.`);
    }
  };

  const toggle = async () => {
    setBusy(true);
    const updated = await api.toggleSource(source.id);
    setBusy(false);
    if (updated) {
      onChange(updated);
      flash(updated.enabled !== 0 ? `Enabled ${updated.company}.` : `Disabled ${updated.company}.`);
    }
  };

  const remove = async () => {
    setBusy(true);
    const ok = await api.deleteSource(source.id);
    setBusy(false);
    if (ok) {
      onRemove(source.id);
      flash(`Removed ${source.company}.`);
    }
  };

  return (
    <div className="card" style={{ padding: "16px 20px" }}>
      <div className="sec-h" style={{ marginBottom: 10, alignItems: "flex-start" }}>
        <span className="t" style={{ flex: 1, minWidth: 0 }}>{source.company}</span>
        <span className={cx("badge", enabled ? "ok" : "muted")} style={{ marginLeft: "auto", flex: "0 0 auto" }}>
          {enabled ? "Enabled" : "Disabled"}
        </span>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", marginBottom: 10 }}>
        <span className="badge muted">{source.ats_type}</span>
        <span className="sub mono">{source.slug}</span>
        {source.country && <span className="sub">{source.country}</span>}
        {source.sector && <span className="sub">{source.sector}</span>}
        <span className="sub">
          <span className="mono">{source.job_count}</span> job{source.job_count === 1 ? "" : "s"}
        </span>
      </div>

      <div style={{ marginBottom: 12 }}>
        {source.last_error ? (
          <span className="sub" style={{ display: "inline-flex", alignItems: "center", gap: 6, color: "var(--warn, var(--muted-foreground))" }}>
            <Icon name="alert-circle" size={14} />
            Last scan reported: {source.last_error}
            <span className="sub" style={{ marginLeft: 4 }}>({fmtWhen(source.last_attempt_at)})</span>
          </span>
        ) : source.last_ok_at ? (
          <span className="sub" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <Icon name="check-circle" size={14} />
            Last good scan {fmtWhen(source.last_ok_at)}
          </span>
        ) : (
          <span className="sub" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <Icon name="radar" size={14} />
            Not scanned yet.
          </span>
        )}
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button className="btn tiny" disabled={scanning || busy} onClick={() => void scan()}>
          <Icon name="refresh-cw" size={13} className={cx(scanning && "spin")} />
          {scanning ? " Scanning…" : " Scan"}
        </button>
        <button className="btn ghost tiny" disabled={scanning || busy} onClick={() => void toggle()}>
          <Icon name={enabled ? "x" : "check"} size={13} />
          {enabled ? " Disable" : " Enable"}
        </button>
        <button className="btn ghost tiny" disabled={scanning || busy} onClick={() => void remove()}>
          <Icon name="trash-2" size={13} /> Delete
        </button>
      </div>
    </div>
  );
}

export function Sources({ flash }: { flash: (msg: string) => void }) {
  const [sources, setSources] = useState<api.Source[]>([]);
  const [atsTypes, setAtsTypes] = useState<string[]>([]);
  const [adzunaCfg, setAdzunaCfg] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState<boolean>(true);

  // Add-source form.
  const [atsType, setAtsType] = useState<string>("");
  const [slug, setSlug] = useState<string>("");
  const [company, setCompany] = useState<string>("");
  const [country, setCountry] = useState<string>("");
  const [sector, setSector] = useState<string>("");
  const [adding, setAdding] = useState<boolean>(false);

  // Remote aggregator scan.
  const [remoteBusy, setRemoteBusy] = useState<boolean>(false);
  const [remoteResults, setRemoteResults] = useState<api.RemoteResult[] | null>(null);

  // Adzuna BYO-key form.
  const [appId, setAppId] = useState<string>("");
  const [appKey, setAppKey] = useState<string>("");
  const [adzCountry, setAdzCountry] = useState<string>("");
  const [adzWhat, setAdzWhat] = useState<string>("");
  const [adzBusy, setAdzBusy] = useState<boolean>(false);

  // Add-a-role-by-hand form.
  const [jobCompany, setJobCompany] = useState<string>("");
  const [jobTitle, setJobTitle] = useState<string>("");
  const [jobUrl, setJobUrl] = useState<string>("");
  const [jobApplyUrl, setJobApplyUrl] = useState<string>("");
  const [jobLocation, setJobLocation] = useState<string>("");
  const [jobText, setJobText] = useState<string>("");
  const [jobBusy, setJobBusy] = useState<boolean>(false);
  const [scoreBusy, setScoreBusy] = useState<boolean>(false);

  useEffect(() => {
    void api.getSources().then((view) => {
      setSources(view.sources);
      setAtsTypes(view.atsTypes);
      setAdzunaCfg(view.adzuna);
      if (view.atsTypes.length > 0) setAtsType(view.atsTypes[0]);
      setLoading(false);
    });
  }, []);

  const onChange = (updated: api.Source) =>
    setSources((rows) => rows.map((s) => (s.id === updated.id ? updated : s)));

  const onRemove = (id: number) =>
    setSources((rows) => rows.filter((s) => s.id !== id));

  const submitAdd = async () => {
    const ty = atsType.trim();
    const sl = slug.trim();
    const co = company.trim();
    if (!ty || !sl || !co) return;
    setAdding(true);
    const res = await api.addSource({
      ats_type: ty,
      slug: sl,
      company: co,
      country: country.trim() || null,
      sector: sector.trim() || null,
    });
    setAdding(false);
    if (res.ok) {
      setSources((rows) => [res.source, ...rows]);
      setSlug("");
      setCompany("");
      setCountry("");
      setSector("");
      flash(`Added ${res.source.company}. Scan it to pull in jobs.`);
    } else if (res.error === "duplicate") {
      flash("That source is already on your list.");
    } else if (res.error === "bad_type") {
      flash("That ATS type is not supported yet.");
    } else {
      flash("Could not add that source.");
    }
  };

  const runRemote = async () => {
    setRemoteBusy(true);
    const results = await api.scanRemote();
    setRemoteBusy(false);
    setRemoteResults(results);
    const total = results.reduce((sum, r) => sum + r.inserted, 0);
    flash(`Remote scan done: added ${total} job${total === 1 ? "" : "s"}.`);
    // Counts may have moved; refresh the source rows.
    void api.getSources().then((view) => setSources(view.sources));
  };

  const saveAdzuna = async () => {
    const id = appId.trim();
    const key = appKey.trim();
    if (!id || !key) return;
    setAdzBusy(true);
    const ok = await api.saveAdzuna({
      app_id: id,
      app_key: key,
      country: adzCountry.trim() || null,
      what: adzWhat.trim() || null,
    });
    setAdzBusy(false);
    if (ok) {
      setAppKey("");
      setAdzunaCfg((cfg) => ({ ...cfg, configured: true }));
      flash("Adzuna key saved on this device.");
    } else {
      flash("Could not save the Adzuna key.");
    }
  };

  const submitJob = async () => {
    const co = jobCompany.trim();
    const ti = jobTitle.trim();
    const ur = jobUrl.trim();
    const jd = jobText.trim();
    // Validate on click (the button stays enabled) so a missing field names
    // itself, instead of a silently-greyed button that appears to "do nothing".
    const missing: string[] = [];
    if (!co) missing.push("company");
    if (!ti) missing.push("title");
    if (!ur) missing.push("URL");
    if (!jd) missing.push("JD text");
    if (missing.length) {
      flash("Still need: " + missing.join(", ") + ".");
      return;
    }
    setJobBusy(true);
    const res = await jobsApi.addJobByHand({
      company: co,
      title: ti,
      url: ur,
      jd_text: jd,
      apply_url: jobApplyUrl.trim() || null,
      location: jobLocation.trim() || null,
    });
    if (!res.ok) {
      setJobBusy(false);
      if (res.status === 409) flash("A role with that URL already exists.");
      else if (res.status === 400) flash("Company, title, URL, and the JD text are all required.");
      else flash("Could not add that role.");
      return;
    }
    // Auto-score so the role lands in Discover in one step (no separate click).
    const scored = await jobsApi.scoreNewJobs();
    setJobBusy(false);
    setJobCompany("");
    setJobTitle("");
    setJobUrl("");
    setJobApplyUrl("");
    setJobLocation("");
    setJobText("");
    flash(
      scored.scored > 0
        ? "Added and scored. Open Today's roles: if it is not India-eligible it sits under Set aside."
        : "Added. Click Score new roles, then check Today's roles.",
    );
  };

  const scoreNew = async () => {
    setScoreBusy(true);
    const res = await jobsApi.scoreNewJobs();
    setScoreBusy(false);
    flash(`Scored ${res.scored} role(s).`);
  };

  const adzunaConfigured = adzunaCfg["configured"] === true;

  return (
    <div>
      <div className="phead">
        <div>
          <h1>Sources</h1>
          <p className="sub">
            The job boards you point at companies. A scan is a real, live fetch, and an honest one: a
            bad slug shows up here as a warning after you scan, never guessed at.
          </p>
        </div>
      </div>

      <section className="card" style={{ padding: "18px 20px", marginBottom: 18 }}>
        <div className="sec-h" style={{ marginBottom: 14 }}>
          <span className="t">Add a source</span>
        </div>

        <label className="fld">
          <span className="fld__l">ATS type</span>
          {atsTypes.length > 0 ? (
            <select className="inp" value={atsType} onChange={(e) => setAtsType(e.target.value)}>
              {atsTypes.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          ) : (
            <span className="sub">No ATS types available.</span>
          )}
        </label>

        <label className="fld" style={{ marginTop: 14 }}>
          <span className="fld__l">Slug</span>
          <input
            className="inp"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            placeholder="the board identifier, e.g. acme"
          />
        </label>

        <label className="fld" style={{ marginTop: 14 }}>
          <span className="fld__l">Company</span>
          <input
            className="inp"
            value={company}
            onChange={(e) => setCompany(e.target.value)}
            placeholder="Acme Inc."
          />
        </label>

        <div style={{ display: "flex", gap: 12, marginTop: 14, flexWrap: "wrap" }}>
          <label className="fld" style={{ flex: 1, minWidth: 160 }}>
            <span className="fld__l">Country (optional)</span>
            <input
              className="inp"
              value={country}
              onChange={(e) => setCountry(e.target.value)}
              placeholder="e.g. US"
            />
          </label>
          <label className="fld" style={{ flex: 1, minWidth: 160 }}>
            <span className="fld__l">Sector (optional)</span>
            <input
              className="inp"
              value={sector}
              onChange={(e) => setSector(e.target.value)}
              placeholder="e.g. fintech"
            />
          </label>
        </div>

        <div style={{ marginTop: 16 }}>
          <button
            className="btn primary"
            disabled={adding || !atsType.trim() || !slug.trim() || !company.trim()}
            onClick={() => void submitAdd()}
          >
            <Icon name="plus" size={14} /> Add source
          </button>
        </div>
      </section>

      <section className="card" style={{ padding: "16px 20px", marginBottom: 18 }}>
        <div className="sec-h" style={{ marginBottom: 12 }}>
          <span className="t">Scan remote aggregators</span>
          <button
            className="btn tiny"
            disabled={remoteBusy}
            onClick={() => void runRemote()}
            style={{ marginLeft: "auto" }}
          >
            <Icon name="radar" size={13} className={cx(remoteBusy && "spin")} />
            {remoteBusy ? " Scanning…" : " Scan now"}
          </button>
        </div>
        <p className="sub" style={{ margin: "0 0 12px" }}>
          Pulls from the no-auth aggregators, plus Adzuna if you have added a key below. Runs over the
          network, so it can take a few seconds.
        </p>

        {remoteResults !== null && (
          remoteResults.length === 0 ? (
            <p className="sub" style={{ margin: 0 }}>No aggregators responded.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {remoteResults.map((r) => (
                <div
                  key={r.name}
                  style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 0", borderBottom: "1px solid var(--border)" }}
                >
                  <Icon
                    name={r.ok ? "check-circle" : "alert-circle"}
                    size={15}
                    style={{ flex: "0 0 auto", color: r.ok ? undefined : "var(--warn, var(--muted-foreground))" }}
                  />
                  <span style={{ flex: 1, minWidth: 0 }}>{r.name}</span>
                  {r.error ? (
                    <span className="sub" style={{ flex: "0 0 auto" }}>{r.error}</span>
                  ) : (
                    <span className="sub mono" style={{ flex: "0 0 auto" }}>
                      +{r.inserted} / {r.fetched} fetched
                    </span>
                  )}
                </div>
              ))}
            </div>
          )
        )}
      </section>

      <section className="card" style={{ padding: "18px 20px", marginBottom: 18 }}>
        <div className="sec-h" style={{ marginBottom: 12 }}>
          <span className="t">Adzuna key</span>
          <span className={cx("badge", adzunaConfigured ? "ok" : "muted")} style={{ marginLeft: "auto" }}>
            {adzunaConfigured ? "Key set" : "Optional"}
          </span>
        </div>
        <p className="sub" style={{ margin: "0 0 14px" }}>
          Optional. Bring your own Adzuna credentials and the remote scan will include it. The key is
          stored only on this device and used straight from here, never sent anywhere else.
        </p>

        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <label className="fld" style={{ flex: 1, minWidth: 200 }}>
            <span className="fld__l">App ID</span>
            <input
              className="inp"
              value={appId}
              onChange={(e) => setAppId(e.target.value)}
              placeholder="your Adzuna app id"
              autoComplete="off"
            />
          </label>
          <label className="fld" style={{ flex: 1, minWidth: 200 }}>
            <span className="fld__l">App key</span>
            <input
              className="inp"
              type="password"
              value={appKey}
              onChange={(e) => setAppKey(e.target.value)}
              placeholder="your Adzuna app key"
              autoComplete="off"
            />
          </label>
        </div>

        <div style={{ display: "flex", gap: 12, marginTop: 14, flexWrap: "wrap" }}>
          <label className="fld" style={{ flex: 1, minWidth: 160 }}>
            <span className="fld__l">Country (optional)</span>
            <input
              className="inp"
              value={adzCountry}
              onChange={(e) => setAdzCountry(e.target.value)}
              placeholder="e.g. gb"
            />
          </label>
          <label className="fld" style={{ flex: 1, minWidth: 160 }}>
            <span className="fld__l">What (optional)</span>
            <input
              className="inp"
              value={adzWhat}
              onChange={(e) => setAdzWhat(e.target.value)}
              placeholder="e.g. software engineer"
            />
          </label>
        </div>

        <div style={{ marginTop: 16 }}>
          <button
            className="btn primary"
            disabled={adzBusy || !appId.trim() || !appKey.trim()}
            onClick={() => void saveAdzuna()}
          >
            <Icon name="check" size={14} /> Save Adzuna key
          </button>
        </div>
      </section>

      <section className="card" style={{ padding: "18px 20px", marginBottom: 18 }}>
        <div className="sec-h" style={{ marginBottom: 12 }}>
          <span className="t">Add a role by hand</span>
        </div>
        <p className="sub" style={{ margin: "0 0 14px" }}>
          Paste a JD that isn't on a polled ATS (LinkedIn, a careers page, a referral). It is scored by
          the same rubric and shows up in Discover.
        </p>

        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <label className="fld" style={{ flex: 1, minWidth: 200 }}>
            <span className="fld__l">Company</span>
            <input
              className="inp"
              value={jobCompany}
              onChange={(e) => setJobCompany(e.target.value)}
              placeholder="Acme Inc."
            />
          </label>
          <label className="fld" style={{ flex: 1, minWidth: 200 }}>
            <span className="fld__l">Title</span>
            <input
              className="inp"
              value={jobTitle}
              onChange={(e) => setJobTitle(e.target.value)}
              placeholder="Senior Software Engineer"
            />
          </label>
        </div>

        <label className="fld" style={{ marginTop: 14 }}>
          <span className="fld__l">URL</span>
          <input
            className="inp"
            value={jobUrl}
            onChange={(e) => setJobUrl(e.target.value)}
            placeholder="the link to the posting"
          />
        </label>

        <div style={{ display: "flex", gap: 12, marginTop: 14, flexWrap: "wrap" }}>
          <label className="fld" style={{ flex: 1, minWidth: 200 }}>
            <span className="fld__l">Apply URL (optional)</span>
            <input
              className="inp"
              value={jobApplyUrl}
              onChange={(e) => setJobApplyUrl(e.target.value)}
              placeholder="where to apply, if different"
            />
          </label>
          <label className="fld" style={{ flex: 1, minWidth: 160 }}>
            <span className="fld__l">Location (optional)</span>
            <input
              className="inp"
              value={jobLocation}
              onChange={(e) => setJobLocation(e.target.value)}
              placeholder="e.g. Remote (US)"
            />
          </label>
        </div>

        <label className="fld" style={{ marginTop: 14 }}>
          <span className="fld__l">JD text</span>
          <textarea
            className="inp"
            value={jobText}
            onChange={(e) => setJobText(e.target.value)}
            placeholder="Paste the full job description here."
            rows={8}
          />
        </label>

        <div style={{ display: "flex", gap: 12, marginTop: 16, flexWrap: "wrap" }}>
          <button
            className="btn primary"
            disabled={jobBusy}
            onClick={() => void submitJob()}
          >
            <Icon name="plus" size={14} /> {jobBusy ? "Adding…" : "Add role"}
          </button>
          <button
            className="btn ghost"
            disabled={scoreBusy}
            onClick={() => void scoreNew()}
          >
            <Icon name="radar" size={14} className={cx(scoreBusy && "spin")} />
            {scoreBusy ? " Scoring…" : " Score new roles"}
          </button>
        </div>
      </section>

      <div className="sec-h" style={{ marginBottom: 12 }}>
        <span className="t">Your sources</span>
        {sources.length > 0 && <span className="badge muted" style={{ marginLeft: "auto" }}>{sources.length}</span>}
      </div>

      {loading ? (
        <div className="sub" style={{ padding: 20 }}>Loading…</div>
      ) : sources.length === 0 ? (
        <div className="card" style={{ padding: "28px 20px", textAlign: "center" }}>
          <span
            className="ic"
            style={{
              width: 36,
              height: 36,
              borderRadius: 9,
              background: "var(--muted)",
              color: "var(--muted-foreground)",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              marginBottom: 10,
            }}
          >
            <Icon name="rss" size={18} />
          </span>
          <p className="sub" style={{ margin: 0 }}>
            No sources yet. Add an ATS board above and scan it to pull in jobs.
          </p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {sources.map((s) => (
            <SourceRow key={s.id} source={s} flash={flash} onChange={onChange} onRemove={onRemove} />
          ))}
        </div>
      )}
    </div>
  );
}
