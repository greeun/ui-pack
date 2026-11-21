// The UI pack viewer. build-view.py of the ui-pack skill exports it as static HTML for each pack.
// The frame (header, table of contents, tables, design guide) is drawn by viewer.css, which does not rely on the pack's tokens; the pack's look comes from the gallery (Gallery) and its global CSS.
import fs from "node:fs";
import path from "node:path";
import type { Metadata } from "next";
import { marked } from "marked";
import { Gallery, ThemeSwitch } from "./viewer-parts";
import "./viewer.css";

type InstallEntry = { from: string; to: string; mode: string };
type Pack = {
  name: string;
  version: string;
  description: string;
  source?: { repo?: string; commit?: string };
  origin?: { mode: string; inputs?: { kind: string; ref: string; captured?: string }[]; credit?: string; rights?: string; estimated?: string[] };
  requires?: Record<string, string>;
  dependencies?: Record<string, string>;
  devDependencies?: Record<string, string>;
  install: InstallEntry[];
  config?: string;
  patterns?: string;
  optional?: Record<string, string[] | string>;
  viewer?: { background?: string };
  components?: Record<string, { status: string; files?: string[]; gallery?: string; note?: string }>;
};
type Catalog = { statuses: Record<string, string>; categories: { name: string; items: { id: string; name: string; desc: string }[] }[] };

const DATA = path.join(process.cwd(), "src", "viewer-data");
const pack: Pack = JSON.parse(fs.readFileSync(path.join(DATA, "pack.json"), "utf8"));
const guide = fs.existsSync(path.join(DATA, "guide.md")) ? fs.readFileSync(path.join(DATA, "guide.md"), "utf8") : "";
const catalog: Catalog | null = fs.existsSync(path.join(DATA, "catalog.json"))
  ? JSON.parse(fs.readFileSync(path.join(DATA, "catalog.json"), "utf8"))
  : null;
const patterns: string[] = fs.existsSync(path.join(DATA, "patterns.json"))
  ? JSON.parse(fs.readFileSync(path.join(DATA, "patterns.json"), "utf8"))
  : [];

const MODE_LABEL: Record<string, string> = {
  copy: "copy as is",
  "replace-or-merge": "replace or merge",
  merge: "merge by hand from the example",
  "copy-and-adjust": "copy, then adjust the wording",
  "copy-and-adapt": "copy, then adapt to the target",
  "copy-if-missing": "copy only when missing",
};

export const metadata: Metadata = { title: `${pack.name} ${pack.version} · UI pack` };

function Rows({ entries }: { entries: [string, string][] }) {
  return (
    <table className="v-table">
      <tbody>
        {entries.map(([k, v]) => (
          <tr key={k}>
            <th scope="row">{k}</th>
            <td>{v}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function Page() {
  const deps = Object.entries({ ...pack.dependencies, ...pack.devDependencies });
  const optional = Object.entries(pack.optional ?? {}).filter(([, v]) => Array.isArray(v) && v.length > 0) as [string, string[]][];
  const guideHtml = guide ? (marked.parse(guide, { async: false }) as string) : "";

  return (
    <div className="v-page" style={{ ["--v-bg" as string]: pack.viewer?.background ?? "Canvas" }}>
      <header className="v-head">
        <div>
          <p className="v-kicker">UI pack</p>
          <h1>
            {pack.name} <span className="v-version">{pack.version}</span>
          </h1>
          <p className="v-lead">{pack.description}</p>
        </div>
        <div className="v-theme">
          <ThemeSwitch />
        </div>
      </header>

      <nav className="v-toc" aria-label="Contents">
        <a href="#gallery">Gallery</a>
        {catalog && <a href="#catalog">Component catalog</a>}
        {guideHtml && <a href="#guide">Design guide</a>}
        <a href="#overview">Install details</a>
        <a href="#files">Files</a>
      </nav>

      <section id="gallery" className="v-section v-gallery">
        <h2>Gallery</h2>
        <p className="v-note">The components below are rendered by the pack's real code. Press the buttons, hover, and move focus with Tab to check them.</p>
        <Gallery />
      </section>




      {catalog && (
        <section id="catalog" className="v-section">
          <h2>Component catalog</h2>
          <p className="v-note">
            This pack's status against the standard list of {catalog.categories.reduce((n, c) => n + c.items.length, 0)} components a UI pack is expected to cover.{" "}
            {Object.entries(catalog.statuses).map(([s, d]) => (
              <span key={s} className="v-legend">
                <span className="v-status" data-s={s}>
                  {s}
                </span>{" "}
                {d}
              </span>
            ))}
          </p>
          <p className="v-note">
            {Object.keys(catalog.statuses)
              .map((s) => `${s} ${Object.values(pack.components ?? {}).filter((c) => c.status === s).length}`)
              .join(" · ")}
          </p>
          {catalog.categories.map((cat) => (
            <div key={cat.name}>
              <h3>{cat.name}</h3>
              <table className="v-table v-catalog">
                <thead>
                  <tr>
                    <th scope="col">Component</th>
                    <th scope="col">Status</th>
                    <th scope="col">Files and gallery card</th>
                    <th scope="col">Description</th>
                  </tr>
                </thead>
                <tbody>
                  {cat.items.map((it) => {
                    const c = pack.components?.[it.id];
                    const s = c?.status ?? "absent";
                    return (
                      <tr key={it.id}>
                        <th scope="row">{it.name}</th>
                        <td>
                          <span className="v-status" data-s={s}>
                            {s}
                          </span>
                        </td>
                        <td>
                          {c?.files?.map((f) => (
                            <code key={f}>{f}</code>
                          ))}
                          {c?.gallery && <span className="v-card">Gallery card: {c.gallery}</span>}
                        </td>
                        <td>
                          {it.desc}
                          {c?.note && <span className="v-sub">{c.note}</span>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ))}
        </section>
      )}

      {guideHtml && (
        <section id="guide" className="v-section">
          <h2>Design guide</h2>
          <article className="v-prose" dangerouslySetInnerHTML={{ __html: guideHtml }} />
        </section>
      )}

      <section id="overview" className="v-section">
        <h2>Install details</h2>
        <p>
          Apply: <code>/ui-pack apply {pack.name}</code>
        </p>
        <div className="v-grid">
          <div>
            <h3>Required stack</h3>
            <Rows entries={Object.entries(pack.requires ?? {})} />
          </div>
          <div>
            <h3>Packages installed with it</h3>
            <Rows entries={deps} />
          </div>
        </div>
        {pack.origin && (
          <p className="v-note">
            {pack.origin.mode === "inspired" ? "Inspired pack (only the structure of the source was used; its name, brand colors and proprietary fonts were left out)" : "Faithful pack rebuilt from screens"}
            {pack.origin.credit ? ` · Source credited: ${pack.origin.credit}` : ""}
            {pack.origin.inputs?.length ? ` · Inputs: ${pack.origin.inputs.map((i) => i.kind).join(", ")}` : ""}
            {pack.origin.estimated?.length ? ` · Estimated values: ${pack.origin.estimated.join(", ")}` : ""}
          </p>
        )}
        {pack.source?.commit && (
          <p className="v-note">
            Source: {pack.source.repo ? path.basename(pack.source.repo) : "source project"} commit <code>{pack.source.commit}</code>
          </p>
        )}
      </section>

      <section id="files" className="v-section">
        <h2>Files</h2>
        <table className="v-table">
          <thead>
            <tr>
              <th scope="col">Pack</th>
              <th scope="col">Target project</th>
              <th scope="col">Mode</th>
            </tr>
          </thead>
          <tbody>
            {pack.install.map((e) => (
              <tr key={e.from}>
                <td>
                  <code>{e.from}</code>
                </td>
                <td>
                  <code>{e.to}</code>
                </td>
                <td>{MODE_LABEL[e.mode] ?? e.mode}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {pack.config && (
          <p className="v-note">
            Values that differ per app are set only in <code>{pack.config}</code>.
          </p>
        )}
        {optional.map(([group, files]) => (
          <div key={group}>
            <h3>Optional group: {group}</h3>
            <p className="v-note">
              When the target does not have this feature, leave it out with <code>--without {group}</code>.
            </p>
            <ul className="v-list">
              {files.map((f) => (
                <li key={f}>
                  <code>{f}</code>
                </li>
              ))}
            </ul>
          </div>
        ))}
        {patterns.length > 0 && (
          <div>
            <h3>Reference patterns</h3>
            {pack.patterns && <p className="v-note">{pack.patterns}</p>}
            <ul className="v-list">
              {patterns.map((f) => (
                <li key={f}>
                  <code>{f}</code>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </div>
  );
}
