/* Matchbox — Profile. The identity block that sits at the top of every rendered
   CV: your name, contact, a one-line headline, and links. Nothing here is
   computed or inferred — it just edits your profile row. Because this copy lands
   on every CV you send, this is the place to fix a typo once and have it stick
   everywhere. */
import { useEffect, useState } from "react";
import * as api from "../api/profile";
import * as targetsApi from "../api/targets";
import { Icon } from "../ui/icon";

/** Split a comma-or-newline list into trimmed, non-empty entries. */
function splitList(text: string): string[] {
  return text
    .split(/[\n,]/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

export function Profile({ flash }: { flash: (msg: string) => void }) {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [location, setLocation] = useState("");
  const [headline, setHeadline] = useState("");
  const [links, setLinks] = useState("");
  const [busy, setBusy] = useState(false);

  const hydrate = (p: api.ProfileDetails): void => {
    setFullName(p.fullName);
    setEmail(p.email);
    setPhone(p.phone);
    setLocation(p.location);
    setHeadline(p.headline);
    setLinks(p.links.join("\n"));
  };

  useEffect(() => {
    void api.getProfileDetails().then(hydrate);
  }, []);

  const save = async (): Promise<void> => {
    if (!fullName.trim() || busy) return;
    setBusy(true);
    const next = await api.saveProfileDetails({
      full_name: fullName.trim(),
      email,
      phone,
      location,
      headline,
      links,
    });
    setBusy(false);
    hydrate(next);
    flash("Profile saved.");
  };

  // Targets & work authorization — a separate row from the profile above; it
  // feeds the eligibility filter in Discover. Kept on its own state and effect
  // so it never disturbs the identity block.
  const [roleFamilies, setRoleFamilies] = useState("");
  const [locations, setLocations] = useState("");
  const [dreamCompanies, setDreamCompanies] = useState("");
  const [exclusions, setExclusions] = useState("");
  const [citizenships, setCitizenships] = useState("");
  const [needsSponsorship, setNeedsSponsorship] = useState(false);
  const [hasClearance, setHasClearance] = useState(false);
  const [compMin, setCompMin] = useState("");
  const [compMax, setCompMax] = useState("");
  const [compCurrency, setCompCurrency] = useState("USD");
  const [targetsBusy, setTargetsBusy] = useState(false);

  const hydrateTargets = (t: targetsApi.Targets): void => {
    setRoleFamilies(t.role_families.join(", "));
    setLocations(t.locations.join(", "));
    setDreamCompanies(t.dream_companies.join(", "));
    setExclusions(t.exclusions.join(", "));
    setCitizenships(t.work_auth.citizenships.join(", "));
    setNeedsSponsorship(t.work_auth.needs_sponsorship);
    setHasClearance(t.work_auth.has_clearance);
    setCompCurrency(t.comp.currency || "USD");
    setCompMin(t.comp.min == null ? "" : String(t.comp.min));
    setCompMax(t.comp.max == null ? "" : String(t.comp.max));
  };

  useEffect(() => {
    void targetsApi.getTargets().then(hydrateTargets);
  }, []);

  const saveTargets = async (): Promise<void> => {
    if (targetsBusy) return;
    setTargetsBusy(true);
    const toInt = (s: string): number | null => {
      const n = parseInt(s.trim(), 10);
      return Number.isFinite(n) ? n : null;
    };
    const next = await targetsApi.saveTargets({
      role_families: splitList(roleFamilies),
      locations: splitList(locations),
      dream_companies: splitList(dreamCompanies),
      exclusions: splitList(exclusions),
      comp: { currency: compCurrency.trim() || "USD", min: toInt(compMin), max: toInt(compMax) },
      work_auth: {
        citizenships: splitList(citizenships),
        needs_sponsorship: needsSponsorship,
        has_clearance: hasClearance,
      },
    });
    setTargetsBusy(false);
    hydrateTargets(next);
    flash("Targets saved.");
  };

  return (
    <div>
      <div className="phead">
        <div>
          <h1>Profile</h1>
          <p className="sub">
            This block sits at the top of every CV you render. Nothing here is computed — fix a typo
            once and it carries everywhere.
          </p>
        </div>
      </div>

      <section className="card" style={{ padding: "18px 20px", maxWidth: 640 }}>
        <label className="fld">
          <span className="fld__l">
            <Icon name="user" size={14} /> Full name
          </span>
          <input
            className="inp"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder="Your name"
          />
        </label>

        <label className="fld" style={{ marginTop: 14 }}>
          <span className="fld__l">Email</span>
          <input
            className="inp"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
        </label>

        <label className="fld" style={{ marginTop: 14 }}>
          <span className="fld__l">Phone</span>
          <input
            className="inp"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="Optional"
          />
        </label>

        <label className="fld" style={{ marginTop: 14 }}>
          <span className="fld__l">Location</span>
          <input
            className="inp"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            placeholder="City, Country"
          />
        </label>

        <label className="fld" style={{ marginTop: 14 }}>
          <span className="fld__l">Headline</span>
          <input
            className="inp"
            value={headline}
            onChange={(e) => setHeadline(e.target.value)}
            placeholder="One line under your name"
          />
        </label>

        <label className="fld" style={{ marginTop: 14 }}>
          <span className="fld__l">Links</span>
          <textarea
            className="inp"
            value={links}
            onChange={(e) => setLinks(e.target.value)}
            placeholder="One link per line"
            rows={4}
          />
          <span className="sub" style={{ marginTop: 6 }}>One link per line.</span>
        </label>

        <div style={{ marginTop: 18 }}>
          <button className="btn primary" disabled={busy || !fullName.trim()} onClick={() => void save()}>
            <Icon name="save" size={15} /> Save profile
          </button>
        </div>
      </section>

      <section className="card" style={{ padding: "18px 20px", maxWidth: 640, marginTop: 18 }}>
        <div className="sec-h">
          <Icon name="target" size={18} />
          <span className="t">Targets &amp; work authorization</span>
        </div>
        <p className="sub" style={{ marginTop: -4, marginBottom: 16 }}>
          These feed the eligibility filter in Discover. Sponsorship/clearance only ever rule a role
          OUT on an explicit conflict — never in.
        </p>

        <label className="fld">
          <span className="fld__l">Role families</span>
          <input
            className="inp"
            value={roleFamilies}
            onChange={(e) => setRoleFamilies(e.target.value)}
            placeholder="Backend, Platform, Infra"
          />
          <span className="sub" style={{ marginTop: 6 }}>Comma or newline separated.</span>
        </label>

        <label className="fld" style={{ marginTop: 14 }}>
          <span className="fld__l">Locations</span>
          <input
            className="inp"
            value={locations}
            onChange={(e) => setLocations(e.target.value)}
            placeholder="Remote, London, New York"
          />
          <span className="sub" style={{ marginTop: 6 }}>Comma or newline separated.</span>
        </label>

        <label className="fld" style={{ marginTop: 14 }}>
          <span className="fld__l">Dream companies</span>
          <textarea
            className="inp"
            value={dreamCompanies}
            onChange={(e) => setDreamCompanies(e.target.value)}
            placeholder="One per line, or comma separated"
            rows={3}
          />
          <span className="sub" style={{ marginTop: 6 }}>Comma or newline separated.</span>
        </label>

        <label className="fld" style={{ marginTop: 14 }}>
          <span className="fld__l">Exclusions</span>
          <textarea
            className="inp"
            value={exclusions}
            onChange={(e) => setExclusions(e.target.value)}
            placeholder="Companies or sectors to rule out"
            rows={3}
          />
          <span className="sub" style={{ marginTop: 6 }}>Comma or newline separated.</span>
        </label>

        <div className="fld" style={{ marginTop: 14 }}>
          <span className="fld__l">Compensation target</span>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <input
              className="inp"
              style={{ flex: 1, minWidth: 120 }}
              value={compMin}
              onChange={(e) => setCompMin(e.target.value)}
              placeholder="Min"
              inputMode="numeric"
            />
            <input
              className="inp"
              style={{ flex: 1, minWidth: 120 }}
              value={compMax}
              onChange={(e) => setCompMax(e.target.value)}
              placeholder="Max"
              inputMode="numeric"
            />
            <input
              className="inp"
              style={{ width: 90 }}
              value={compCurrency}
              onChange={(e) => setCompCurrency(e.target.value)}
              placeholder="USD"
            />
          </div>
          <span className="sub" style={{ marginTop: 6 }}>
            Optional. Whole numbers — your own compensation reference, stored locally.
          </span>
        </div>

        <label className="fld" style={{ marginTop: 14 }}>
          <span className="fld__l">Citizenships</span>
          <input
            className="inp"
            value={citizenships}
            onChange={(e) => setCitizenships(e.target.value)}
            placeholder="IN, US"
          />
          <span className="sub" style={{ marginTop: 6 }}>Comma separated.</span>
        </label>

        <label className="fld" style={{ marginTop: 14, flexDirection: "row", alignItems: "center", gap: 8 }}>
          <input
            type="checkbox"
            checked={needsSponsorship}
            onChange={(e) => setNeedsSponsorship(e.target.checked)}
          />
          <span className="fld__l" style={{ margin: 0 }}>I need visa sponsorship</span>
        </label>

        <label className="fld" style={{ marginTop: 10, flexDirection: "row", alignItems: "center", gap: 8 }}>
          <input
            type="checkbox"
            checked={hasClearance}
            onChange={(e) => setHasClearance(e.target.checked)}
          />
          <span className="fld__l" style={{ margin: 0 }}>I hold a security clearance</span>
        </label>

        <div style={{ marginTop: 18 }}>
          <button className="btn primary" disabled={targetsBusy} onClick={() => void saveTargets()}>
            <Icon name="save" size={15} /> Save targets
          </button>
        </div>
      </section>
    </div>
  );
}
