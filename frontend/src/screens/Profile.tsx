/* Matchbox — Profile. The identity block that sits at the top of every rendered
   CV: your name, contact, a one-line headline, and links. Nothing here is
   computed or inferred — it just edits your profile row. Because this copy lands
   on every CV you send, this is the place to fix a typo once and have it stick
   everywhere. */
import { useEffect, useState } from "react";
import * as api from "../api/profile";
import { Icon } from "../ui/icon";

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
    </div>
  );
}
