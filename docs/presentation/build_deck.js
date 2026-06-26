const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const FA = require("react-icons/fa");

// ---- palette ---------------------------------------------------------------
const NAVY = "0F1B3D";    // dark background
const NAVY2 = "1B2C5A";   // raised card on dark
const ICE = "F4F7FC";     // light background
const WHITE = "FFFFFF";
const TEAL = "2DD4BF";    // primary accent
const PERI = "7C9CF0";    // secondary accent
const INK = "1A2138";     // text on light
const MUTED = "5B6478";   // muted on light
const DIM = "A9B5D6";     // muted on dark
const CARD = "FFFFFF";
const HF = "Georgia";     // header font
const BF = "Calibri";     // body font

const W = 13.333, H = 7.5;

// ---- icon helper -----------------------------------------------------------
async function icon(name, color = "#0F1B3D", size = 256) {
  const Comp = FA[name];
  if (!Comp) throw new Error("missing icon " + name);
  const svg = ReactDOMServer.renderToStaticMarkup(
    React.createElement(Comp, { color, size: String(size) })
  );
  const png = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + png.toString("base64");
}
const sh = () => ({ type: "outer", color: "0B1330", blur: 9, offset: 3, angle: 135, opacity: 0.22 });

(async () => {
  const p = new pptxgen();
  p.defineLayout({ name: "W", width: W, height: H });
  p.layout = "W";
  p.author = "AI-SDLC Bootstrap Kit";
  p.title = "AI-SDLC Bootstrap Kit";

  // preload icons
  const I = {};
  const want = {
    robot: "FaRobot", layers: "FaLayerGroup", warn: "FaExclamationTriangle",
    bulb: "FaLightbulb", board: "FaChalkboardTeacher",
    rocket: "FaRocket", onboard: "FaUserPlus", scale: "FaBalanceScale",
    gate: "FaCheckDouble", brain: "FaBrain", roles: "FaUsersCog", loop: "FaSyncAlt",
    architect: "FaDraftingCompass", em: "FaUsersCog", product: "FaClipboardList",
    dev: "FaCode", qa: "FaVial", db: "FaDatabase", stream: "FaStream",
    shield: "FaShieldAlt", contract: "FaFileContract", lock: "FaLock",
    branch: "FaCodeBranch", pen: "FaPenFancy", pr: "FaCodeBranch",
    chart: "FaChartLine", users: "FaUsers", terminal: "FaTerminal",
    check: "FaCheckCircle", plug: "FaPlug", search: "FaSearch", book: "FaBookOpen",
  };
  for (const [k, v] of Object.entries(want)) {
    I[k] = { dark: await icon(v, "#0F1B3D"), teal: await icon(v, "#2DD4BF"),
             white: await icon(v, "#FFFFFF"), peri: await icon(v, "#7C9CF0") };
  }

  // ---- reusable pieces -----------------------------------------------------
  function footer(s, n) {
    s.addText("AI-SDLC Bootstrap Kit", { x: 0.55, y: H - 0.46, w: 6, h: 0.3, fontFace: BF, fontSize: 9, color: MUTED, align: "left" });
    s.addText(String(n).padStart(2, "0"), { x: W - 1.1, y: H - 0.46, w: 0.55, h: 0.3, fontFace: BF, fontSize: 9, color: MUTED, align: "right" });
  }
  function kicker(s, text, color = TEAL, x = 0.85, y = 0.6) {
    s.addText(text.toUpperCase(), { x, y, w: 8, h: 0.3, fontFace: BF, fontSize: 12, bold: true, color, charSpacing: 3, margin: 0 });
  }
  // icon in a rounded teal tile
  function tile(s, data, x, y, sz = 0.8, fill = TEAL) {
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x, y, w: sz, h: sz, fill: { color: fill }, rectRadius: 0.1, shadow: sh() });
    const pad = sz * 0.22;
    s.addImage({ data, x: x + pad, y: y + pad, w: sz - 2 * pad, h: sz - 2 * pad });
  }
  function lightTitle(s, t, y = 0.95) {
    s.addText(t, { x: 0.85, y, w: 11.6, h: 0.95, fontFace: HF, fontSize: 32, bold: true, color: INK, margin: 0 });
  }

  // ============================ 1. TITLE ====================================
  let s = p.addSlide(); s.background = { color: NAVY };
  s.addShape(p.shapes.OVAL, { x: 9.6, y: -2.4, w: 6.5, h: 6.5, fill: { color: NAVY2 } });
  s.addShape(p.shapes.OVAL, { x: 11.2, y: 4.2, w: 4.2, h: 4.2, fill: { color: "16224A" } });
  tile(s, I.layers.dark, 0.95, 1.5, 1.15, TEAL);
  s.addText("AI-SDLC", { x: 0.9, y: 2.95, w: 11, h: 1.0, fontFace: HF, fontSize: 54, bold: true, color: WHITE, margin: 0 });
  s.addText("Bootstrap Kit", { x: 0.9, y: 3.95, w: 11, h: 1.0, fontFace: HF, fontSize: 54, bold: true, color: TEAL, margin: 0 });
  s.addText("A ready-made operating model for an AI-augmented Software Development Life Cycle —\nAI as a governed, grounded, attributable collaborator across the whole lifecycle.",
    { x: 0.95, y: 5.15, w: 10.5, h: 1.0, fontFace: BF, fontSize: 16, color: DIM, lineSpacingMultiple: 1.15, margin: 0 });
  s.addText("From the AUTOMATIZARE operating model — bootstrapped into any repo.", { x: 0.95, y: 6.25, w: 10, h: 0.3, fontFace: BF, fontSize: 12, italic: true, color: PERI, margin: 0 });

  // ============================ 2. PROBLEM ==================================
  s = p.addSlide(); s.background = { color: ICE };
  kicker(s, "The problem");
  lightTitle(s, "AI is in every dev workflow — but ungoverned");
  const probs = [
    ["warn", "Ad-hoc", "Every engineer prompts differently. No shared baseline, no repeatable quality."],
    ["search", "Ungrounded", "Agents answer from memory and guess APIs instead of the project's own truth."],
    ["lock", "Unattributable", "AI edits load-bearing artefacts with no named owner and no reviewable trail."],
    ["scale", "Reinvented", "Each project rebuilds the same governance from scratch — and it drifts."],
  ];
  let cx = 0.85, cy = 2.15, cw = 5.75, ch = 1.95, gx = 0.35, gy = 0.35;
  probs.forEach((pr, i) => {
    const x = cx + (i % 2) * (cw + gx), y = cy + Math.floor(i / 2) * (ch + gy);
    s.addShape(p.shapes.RECTANGLE, { x, y, w: cw, h: ch, fill: { color: CARD }, shadow: sh() });
    s.addShape(p.shapes.RECTANGLE, { x, y, w: 0.09, h: ch, fill: { color: TEAL } });
    tile(s, I[pr[0]].white, x + 0.32, y + 0.34, 0.78, NAVY);
    s.addText(pr[1], { x: x + 1.35, y: y + 0.3, w: cw - 1.6, h: 0.5, fontFace: HF, fontSize: 20, bold: true, color: INK, margin: 0 });
    s.addText(pr[2], { x: x + 1.35, y: y + 0.82, w: cw - 1.6, h: 1.0, fontFace: BF, fontSize: 13.5, color: MUTED, lineSpacingMultiple: 1.1, margin: 0 });
  });
  footer(s, 2);

  // ============================ 3. THE IDEA =================================
  s = p.addSlide(); s.background = { color: NAVY };
  kicker(s, "The idea", TEAL, 0.85, 0.6);
  s.addText("One operating model, bootstrapped into any repo", { x: 0.85, y: 0.95, w: 11.6, h: 0.9, fontFace: HF, fontSize: 32, bold: true, color: WHITE, margin: 0 });
  s.addText("It began on a whiteboard — AUTOMATIZARE. The kit turns that sketch into a runnable scaffold: a knowledge layer agents ground on, a Roles × Skills × MCP matrix, governance rules enforced as CI, onboarding, setup, and a human-owned improvement loop.",
    { x: 0.9, y: 1.95, w: 11.3, h: 1.0, fontFace: BF, fontSize: 15, color: DIM, lineSpacingMultiple: 1.15, margin: 0 });
  // flow: Sources -> ingest -> KG/RAG -> seats -> governed
  const flow = [["db", "Sources"], ["stream", "Ingest"], ["brain", "KG · RAG · Vector"], ["roles", "Roles × Skills × MCP"], ["shield", "Governed delivery"]];
  let fx = 0.95, fy = 3.55, fw = 2.15, fh = 1.85, fg = (W - 1.9 - flow.length * 2.15) / (flow.length - 1);
  flow.forEach((f, i) => {
    const x = fx + i * (fw + fg);
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x, y: fy, w: fw, h: fh, fill: { color: NAVY2 }, rectRadius: 0.08, shadow: sh() });
    tile(s, I[f[0]].dark, x + (fw - 0.85) / 2, fy + 0.3, 0.85, TEAL);
    s.addText(f[1], { x: x + 0.1, y: fy + 1.28, w: fw - 0.2, h: 0.5, fontFace: BF, fontSize: 12.5, bold: true, color: WHITE, align: "center", margin: 0 });
    if (i < flow.length - 1) s.addText("›", { x: x + fw + fg / 2 - 0.18, y: fy + 0.55, w: 0.36, h: 0.7, fontFace: HF, fontSize: 30, bold: true, color: TEAL, align: "center", margin: 0 });
  });
  s.addText("Human stays in the loop — promotion, sign-off and curation are never delegated.", { x: 0.95, y: 5.85, w: 11, h: 0.3, fontFace: BF, fontSize: 12, italic: true, color: PERI, margin: 0 });
  footer(s, 3);

  // ============================ 4. SEVEN PILLARS ============================
  s = p.addSlide(); s.background = { color: ICE };
  kicker(s, "The framework");
  lightTitle(s, "Seven pillars");
  const pillars = [
    ["rocket", "1 · Setup", "One-command bootstrap of a governed, AI-ready repo."],
    ["onboard", "2 · Onboarding", "Per-user first-run installs tooling and creates USER.md."],
    ["scale", "3 · Governance & rules", "One canonical brief, trust tiers, scoped-write MCP."],
    ["gate", "4 · CI/CD for AI", "Rules expressed as scripts, enforced as merge gates."],
    ["brain", "5 · Knowledge layer", "Sources → KG / RAG / vector; agents ground & cite."],
    ["roles", "6 · Roles × Skills × MCP", "Each seat = invokable skill + scoped connectors."],
    ["loop", "7 · Human methodology", "Dashboard + retro turn usage into improvements."],
  ];
  let px = 0.85, py = 2.0, pw = 3.82, ph = 1.45, pgx = 0.27, pgy = 0.22;
  pillars.forEach((pl, i) => {
    const col = i % 3, row = Math.floor(i / 3);
    const x = px + col * (pw + pgx), y = py + row * (ph + pgy);
    s.addShape(p.shapes.RECTANGLE, { x, y, w: pw, h: ph, fill: { color: CARD }, shadow: sh() });
    tile(s, I[pl[0]].white, x + 0.28, y + 0.3, 0.7, i === 6 ? PERI : NAVY);
    s.addText(pl[1], { x: x + 1.12, y: y + 0.26, w: pw - 1.3, h: 0.5, fontFace: HF, fontSize: 14.5, bold: true, color: INK, margin: 0 });
    s.addText(pl[2], { x: x + 1.12, y: y + 0.7, w: pw - 1.3, h: 0.75, fontFace: BF, fontSize: 11, color: MUTED, lineSpacingMultiple: 1.05, margin: 0 });
  });
  // 8th cell: summary accent
  const x8 = px + 0 * 0, lx = px + 0; // place accent block in last grid cell (col2,row2)
  const cx8 = px + 2 * (pw + pgx), cy8 = py + 2 * (ph + pgy);
  s.addShape(p.shapes.RECTANGLE, { x: cx8, y: cy8, w: pw, h: ph, fill: { color: NAVY } });
  s.addText("Each pillar ships at least one runnable or enforceable artefact — not just prose.", { x: cx8 + 0.3, y: cy8 + 0.28, w: pw - 0.6, h: ph - 0.5, fontFace: BF, fontSize: 13, italic: true, color: WHITE, valign: "middle", margin: 0 });
  footer(s, 4);

  // ============================ 5. ROLES x SKILLS x MCP =====================
  s = p.addSlide(); s.background = { color: ICE };
  kicker(s, "Pillar 6");
  lightTitle(s, "Roles × Skills × MCP");
  s.addText("Five named seats. Each carries an invokable role-contract skill and a scoped set of MCP connectors — who owns what, which skills they invoke, which tools they may act in.",
    { x: 0.85, y: 1.85, w: 11.6, h: 0.7, fontFace: BF, fontSize: 14, color: MUTED, lineSpacingMultiple: 1.1, margin: 0 });
  const seats = [
    ["architect", "Architect", "Shape · ADRs · standards"],
    ["em", "EM", "Repos · CI · capacity"],
    ["product", "Product", "Scope · backlog · roadmap"],
    ["dev", "Developer", "Implementation · tests"],
    ["qa", "QA", "Strategy · gates · traceability"],
  ];
  let sx = 0.85, sy = 2.75, sw = 2.32, sgap = (W - 1.7 - seats.length * 2.32) / (seats.length - 1), sht = 2.3;
  seats.forEach((se, i) => {
    const x = sx + i * (sw + sgap);
    s.addShape(p.shapes.RECTANGLE, { x, y: sy, w: sw, h: sht, fill: { color: CARD }, shadow: sh() });
    s.addShape(p.shapes.RECTANGLE, { x, y: sy, w: sw, h: 0.1, fill: { color: TEAL } });
    tile(s, I[se[0]].white, x + (sw - 0.9) / 2, sy + 0.35, 0.9, NAVY);
    s.addText(se[1], { x, y: sy + 1.35, w: sw, h: 0.4, fontFace: HF, fontSize: 17, bold: true, color: INK, align: "center", margin: 0 });
    s.addText(se[2], { x: x + 0.15, y: sy + 1.78, w: sw - 0.3, h: 0.5, fontFace: BF, fontSize: 10.5, color: MUTED, align: "center", lineSpacingMultiple: 1.0, margin: 0 });
  });
  // bottom band: skills + mcp
  const by = 5.35;
  s.addShape(p.shapes.RECTANGLE, { x: 0.85, y: by, w: 5.75, h: 1.35, fill: { color: NAVY } });
  tile(s, I.book.dark, 1.1, by + 0.32, 0.7, TEAL);
  s.addText("Invokable Skills", { x: 2.0, y: by + 0.28, w: 4.4, h: 0.4, fontFace: HF, fontSize: 15, bold: true, color: WHITE, margin: 0 });
  s.addText(".claude/skills/playbook-<seat> — auto-discovered, conform to agentskills.io", { x: 2.0, y: by + 0.7, w: 4.5, h: 0.55, fontFace: BF, fontSize: 11, color: DIM, lineSpacingMultiple: 1.0, margin: 0 });
  s.addShape(p.shapes.RECTANGLE, { x: 6.85, y: by, w: 5.6, h: 1.35, fill: { color: NAVY2 } });
  tile(s, I.plug.dark, 7.1, by + 0.32, 0.7, PERI);
  s.addText("Scoped MCP connectors", { x: 7.95, y: by + 0.28, w: 4.4, h: 0.4, fontFace: HF, fontSize: 15, bold: true, color: WHITE, margin: 0 });
  s.addText(".mcp.json — tracker · wiki · knowledge · docs, per seat", { x: 7.95, y: by + 0.7, w: 4.4, h: 0.55, fontFace: BF, fontSize: 11, color: DIM, lineSpacingMultiple: 1.0, margin: 0 });
  footer(s, 5);

  // ============================ 6. KNOWLEDGE LAYER ==========================
  s = p.addSlide(); s.background = { color: NAVY };
  kicker(s, "Pillar 5", TEAL);
  s.addText("Knowledge layer — ground, don't guess", { x: 0.85, y: 0.95, w: 11.6, h: 0.9, fontFace: HF, fontSize: 32, bold: true, color: WHITE, margin: 0 });
  s.addText("Project sources are ingested into a queryable store. Agents answer from it and cite the source's trust tier — instead of guessing from memory.",
    { x: 0.9, y: 1.95, w: 11.3, h: 0.7, fontFace: BF, fontSize: 15, color: DIM, lineSpacingMultiple: 1.15, margin: 0 });
  const klay = [["book", "Sources", "Docs, ADRs, standards, stakeholder input — frontmatter carries the trust tier."],
    ["stream", "Ingest", "Chunk + index (stub: keyword; prod: embeddings or a knowledge MCP server)."],
    ["brain", "KG / RAG / Vector", "A store agents query for grounded, citable context."]];
  let kx = 0.95, ky = 3.1, kw = 3.7, kg = (W - 1.9 - 3 * 3.7) / 2, kh = 2.55;
  klay.forEach((kl, i) => {
    const x = kx + i * (kw + kg);
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x, y: ky, w: kw, h: kh, fill: { color: NAVY2 }, rectRadius: 0.07, shadow: sh() });
    tile(s, I[kl[0]].dark, x + 0.35, ky + 0.35, 0.85, TEAL);
    s.addText(kl[1], { x: x + 0.35, y: ky + 1.3, w: kw - 0.6, h: 0.45, fontFace: HF, fontSize: 18, bold: true, color: WHITE, margin: 0 });
    s.addText(kl[2], { x: x + 0.35, y: ky + 1.78, w: kw - 0.6, h: 0.7, fontFace: BF, fontSize: 12, color: DIM, lineSpacingMultiple: 1.08, margin: 0 });
    if (i < 2) s.addText("›", { x: x + kw + kg / 2 - 0.2, y: ky + 0.85, w: 0.4, h: 0.8, fontFace: HF, fontSize: 34, bold: true, color: TEAL, align: "center", margin: 0 });
  });
  s.addText("scripts/knowledge/ingest.py — runnable on day one, no external services.", { x: 0.95, y: 6.0, w: 11, h: 0.3, fontFace: BF, fontSize: 12, italic: true, color: PERI, margin: 0 });
  footer(s, 6);

  // ============================ 7. GOVERNANCE & TRUST =======================
  s = p.addSlide(); s.background = { color: ICE };
  kicker(s, "Pillar 3");
  lightTitle(s, "Governance & trust");
  // left: trust tiers stack
  s.addText("Trust tiers — what an AI may rely on", { x: 0.85, y: 2.0, w: 5.7, h: 0.4, fontFace: HF, fontSize: 16, bold: true, color: INK, margin: 0 });
  const tiers = [["Authoritative", "cite directly", TEAL], ["Working", "cite + status flag", PERI], ["Exploratory", "read only if named", "9AA6C2"], ["Restricted", "path-referenced only", MUTED]];
  let ty = 2.55;
  tiers.forEach((t) => {
    s.addShape(p.shapes.RECTANGLE, { x: 0.85, y: ty, w: 5.7, h: 0.78, fill: { color: CARD }, shadow: sh() });
    s.addShape(p.shapes.RECTANGLE, { x: 0.85, y: ty, w: 0.12, h: 0.78, fill: { color: t[2] } });
    s.addText(t[0], { x: 1.15, y: ty + 0.13, w: 2.7, h: 0.5, fontFace: HF, fontSize: 15, bold: true, color: INK, margin: 0 });
    s.addText(t[1], { x: 3.7, y: ty + 0.16, w: 2.7, h: 0.45, fontFace: BF, fontSize: 12.5, color: MUTED, align: "right", margin: 0 });
    ty += 0.92;
  });
  // right: posture cards
  s.addText("Scoped-write MCP posture", { x: 6.95, y: 2.0, w: 5.5, h: 0.4, fontFace: HF, fontSize: 16, bold: true, color: INK, margin: 0 });
  const post = [["contract", "One canonical brief", "AGENTS.md is the single source of truth; CLAUDE.md is a thin pointer that can't drift."],
    ["shield", "Attributable, never silent", "Every AI write to a load-bearing artefact has a named seat and a reviewable trail."],
    ["lock", "Humans hold the keys", "Promotion, sign-off, and merges to protected branches stay human."]];
  let gy2 = 2.55;
  post.forEach((g) => {
    s.addShape(p.shapes.RECTANGLE, { x: 6.95, y: gy2, w: 5.5, h: 1.12, fill: { color: NAVY } });
    tile(s, I[g[0]].dark, 7.2, gy2 + 0.22, 0.68, TEAL);
    s.addText(g[1], { x: 8.05, y: gy2 + 0.16, w: 4.3, h: 0.4, fontFace: HF, fontSize: 14.5, bold: true, color: WHITE, margin: 0 });
    s.addText(g[2], { x: 8.05, y: gy2 + 0.55, w: 4.25, h: 0.5, fontFace: BF, fontSize: 10.8, color: DIM, lineSpacingMultiple: 1.0, margin: 0 });
    gy2 += 1.27;
  });
  footer(s, 7);

  // ============================ 8. CI/CD FOR AI =============================
  s = p.addSlide(); s.background = { color: ICE };
  kicker(s, "Pillar 4");
  lightTitle(s, "CI/CD for the AI framework — rules as scripts");
  s.addText("Governance rules are runnable scripts, enforced as merge gates. Local pre-commit gives fast feedback; CI is the non-bypassable gate.",
    { x: 0.85, y: 1.85, w: 11.6, h: 0.6, fontFace: BF, fontSize: 14, color: MUTED, lineSpacingMultiple: 1.1, margin: 0 });
  const gates = [["gate", "validate-skills.py", "Every SKILL.md conforms to the agentskills.io spec."],
    ["contract", "validate-frontmatter.py", "Every governed doc carries the maturity & trust contract."],
    ["branch", "commit_msg_ticket.py", "Every commit references an issue key, linking code to work."]];
  let ggx = 0.85, ggy = 2.7, ggw = 3.82, ggg = 0.27, ggh = 2.35;
  gates.forEach((g, i) => {
    const x = ggx + i * (ggw + ggg);
    s.addShape(p.shapes.RECTANGLE, { x, y: ggy, w: ggw, h: ggh, fill: { color: CARD }, shadow: sh() });
    s.addShape(p.shapes.RECTANGLE, { x, y: ggy, w: ggw, h: 0.1, fill: { color: TEAL } });
    tile(s, I[g[0]].white, x + 0.32, ggy + 0.35, 0.8, NAVY);
    s.addText(g[1], { x: x + 0.32, y: ggy + 1.32, w: ggw - 0.6, h: 0.45, fontFace: "Consolas", fontSize: 14, bold: true, color: INK, margin: 0 });
    s.addText(g[2], { x: x + 0.32, y: ggy + 1.78, w: ggw - 0.6, h: 0.5, fontFace: BF, fontSize: 12, color: MUTED, lineSpacingMultiple: 1.05, margin: 0 });
  });
  s.addShape(p.shapes.RECTANGLE, { x: 0.85, y: 5.45, w: 11.62, h: 0.95, fill: { color: NAVY } });
  s.addText([{ text: "Same scripts, two homes:  ", options: { bold: true, color: TEAL } },
    { text: ".pre-commit-config.yaml (fast, local) → .github/workflows/ai-governance.yml (enforced merge gate).", options: { color: WHITE } }],
    { x: 1.1, y: 5.45, w: 11.1, h: 0.95, fontFace: BF, fontSize: 13.5, valign: "middle", margin: 0 });
  footer(s, 8);

  // ============================ 9. SESSION RITUAL ===========================
  s = p.addSlide(); s.background = { color: NAVY };
  kicker(s, "The session ritual", TEAL);
  s.addText("Repo → Edit → Pull Request", { x: 0.85, y: 0.95, w: 11.6, h: 0.9, fontFace: HF, fontSize: 32, bold: true, color: WHITE, margin: 0 });
  s.addText("Every session follows the same lightweight loop, so authorship and review stay consistent.",
    { x: 0.9, y: 1.9, w: 11.3, h: 0.5, fontFace: BF, fontSize: 15, color: DIM, margin: 0 });
  const steps = [["branch", "Start", "Confirm seat. Print branch & sync state. Optional fast-forward."],
    ["search", "Ground", "Answer from the knowledge layer; cite the source's trust tier."],
    ["pen", "Edit", "Work on a branch. Frontmatter: owner = seat, author = git."],
    ["gate", "Gate", "Pre-commit runs the governance checks before the commit lands."],
    ["pr", "Pull Request", "Commit, push branch, open a PR. Merge is human-reviewed."]];
  let stx = 0.95, sty = 2.85, stw = 2.18, stg = (W - 1.9 - steps.length * 2.18) / (steps.length - 1), sth = 2.5;
  steps.forEach((st2, i) => {
    const x = stx + i * (stw + stg);
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x, y: sty, w: stw, h: sth, fill: { color: NAVY2 }, rectRadius: 0.08, shadow: sh() });
    s.addText(String(i + 1), { x: x + 0.0, y: sty + 0.25, w: stw, h: 0.5, fontFace: HF, fontSize: 16, bold: true, color: PERI, align: "center", margin: 0 });
    tile(s, I[st2[0]].dark, x + (stw - 0.8) / 2, sty + 0.72, 0.8, TEAL);
    s.addText(st2[1], { x, y: sty + 1.62, w: stw, h: 0.4, fontFace: HF, fontSize: 15, bold: true, color: WHITE, align: "center", margin: 0 });
    s.addText(st2[2], { x: x + 0.18, y: sty + 2.0, w: stw - 0.36, h: 0.45, fontFace: BF, fontSize: 9.8, color: DIM, align: "center", lineSpacingMultiple: 0.98, margin: 0 });
    if (i < steps.length - 1) s.addText("›", { x: x + stw + stg / 2 - 0.16, y: sty + 0.95, w: 0.32, h: 0.6, fontFace: HF, fontSize: 26, bold: true, color: TEAL, align: "center", margin: 0 });
  });
  s.addText("AI never pushes a protected branch. Every change is attributable to a named seat.", { x: 0.95, y: 5.7, w: 11.5, h: 0.3, fontFace: BF, fontSize: 12.5, italic: true, color: PERI, margin: 0 });
  footer(s, 9);

  // ============================ 10. HUMAN IN THE LOOP =======================
  s = p.addSlide(); s.background = { color: ICE };
  kicker(s, "Pillar 7");
  lightTitle(s, "Human in the loop");
  s.addText("A utilization dashboard (DB + web) and a recurring retro turn AI usage into improvements to the rules, skills, and knowledge. The point is honest cost and quality — not surveillance.",
    { x: 0.85, y: 1.85, w: 11.6, h: 0.7, fontFace: BF, fontSize: 14, color: MUTED, lineSpacingMultiple: 1.1, margin: 0 });
  // metric callouts
  const mets = [["68%", "Acceptance rate", TEAL], ["$0.21", "Cost / accepted", PERI], ["12%", "Rework rate", "E0794B"], ["83%", "Grounding rate", TEAL]];
  let mx = 0.85, my = 2.85, mw = 2.78, mg = (W - 1.7 - 4 * 2.78) / 3, mh = 1.7;
  mets.forEach((m, i) => {
    const x = mx + i * (mw + mg);
    s.addShape(p.shapes.RECTANGLE, { x, y: my, w: mw, h: mh, fill: { color: NAVY } });
    s.addText(m[0], { x, y: my + 0.28, w: mw, h: 0.75, fontFace: HF, fontSize: 38, bold: true, color: m[2], align: "center", margin: 0 });
    s.addText(m[1], { x, y: my + 1.08, w: mw, h: 0.4, fontFace: BF, fontSize: 12, color: WHITE, align: "center", margin: 0 });
  });
  // loop line
  s.addShape(p.shapes.RECTANGLE, { x: 0.85, y: 4.95, w: 11.62, h: 1.45, fill: { color: CARD }, shadow: sh() });
  tile(s, I.loop.white, 1.1, 5.25, 0.85, NAVY);
  s.addText("Observe → Measure → Review → Improve", { x: 2.15, y: 5.18, w: 10, h: 0.45, fontFace: HF, fontSize: 17, bold: true, color: INK, margin: 0 });
  s.addText("Each retro leaves a diff: a sharper skill description, a new knowledge source, a tightened — or removed — rule.", { x: 2.15, y: 5.66, w: 10.1, h: 0.55, fontFace: BF, fontSize: 12.5, color: MUTED, lineSpacingMultiple: 1.05, margin: 0 });
  footer(s, 10);

  // ============================ 11. HOW TO ADOPT ============================
  s = p.addSlide(); s.background = { color: ICE };
  kicker(s, "Adoption");
  lightTitle(s, "Adopt it in one command");
  // left: terminal
  s.addShape(p.shapes.RECTANGLE, { x: 0.85, y: 2.0, w: 6.6, h: 2.5, fill: { color: NAVY } });
  s.addShape(p.shapes.OVAL, { x: 1.05, y: 2.2, w: 0.16, h: 0.16, fill: { color: "FF5F56" } });
  s.addShape(p.shapes.OVAL, { x: 1.28, y: 2.2, w: 0.16, h: 0.16, fill: { color: "FFBD2E" } });
  s.addShape(p.shapes.OVAL, { x: 1.51, y: 2.2, w: 0.16, h: 0.16, fill: { color: "27C93F" } });
  s.addText([
    { text: "$ template/scripts/bootstrap.sh \\", options: { color: TEAL, breakLine: true } },
    { text: "    --name \"Acme Wallet\" --slug acme-wallet \\", options: { color: WHITE, breakLine: true } },
    { text: "    --dir ../acme-wallet --ticket ACME --host github", options: { color: WHITE, breakLine: true } },
    { text: "", options: { breakLine: true } },
    { text: "✓ copied template  ✓ substituted placeholders", options: { color: DIM, breakLine: true } },
    { text: "✓ git init + commit  ✓ installed hooks", options: { color: DIM } },
  ], { x: 1.05, y: 2.6, w: 6.2, h: 1.7, fontFace: "Consolas", fontSize: 11.5, lineSpacingMultiple: 1.25, margin: 0 });
  // right: steps
  const adopt = [["terminal", "Bootstrap", "One script scaffolds a governed, AI-ready repo."],
    ["pen", "Fill placeholders", "AGENTS.md §1 mission, §3 constraints, §4 connectors."],
    ["onboard", "Onboard", "Open in Claude Code — it runs ONBOARDING.md."],
    ["rocket", "Start", "Add knowledge sources and ship — gated from day one."]];
  let ax = 7.7, ay = 2.0, aw = 4.78, ah = 1.12, ag = 0.12;
  adopt.forEach((a, i) => {
    const y = ay + i * (ah + ag);
    s.addShape(p.shapes.RECTANGLE, { x: ax, y, w: aw, h: ah, fill: { color: CARD }, shadow: sh() });
    tile(s, I[a[0]].white, ax + 0.22, y + 0.22, 0.68, NAVY);
    s.addText(a[1], { x: ax + 1.05, y: y + 0.16, w: aw - 1.2, h: 0.4, fontFace: HF, fontSize: 14.5, bold: true, color: INK, margin: 0 });
    s.addText(a[2], { x: ax + 1.05, y: y + 0.56, w: aw - 1.2, h: 0.45, fontFace: BF, fontSize: 10.8, color: MUTED, lineSpacingMultiple: 1.0, margin: 0 });
  });
  s.addText("Verify the gates locally: python3 scripts/validate-skills.py · validate-frontmatter.py · knowledge/ingest.py --build", { x: 0.85, y: 4.75, w: 6.6, h: 0.5, fontFace: BF, fontSize: 10.5, italic: true, color: MUTED, lineSpacingMultiple: 1.05, margin: 0 });
  footer(s, 11);

  // ============================ 12. CTA =====================================
  s = p.addSlide(); s.background = { color: NAVY };
  s.addShape(p.shapes.OVAL, { x: -2.2, y: 3.6, w: 6.5, h: 6.5, fill: { color: NAVY2 } });
  s.addShape(p.shapes.OVAL, { x: 10.5, y: -2.6, w: 5.5, h: 5.5, fill: { color: "16224A" } });
  tile(s, I.check.dark, 0.95, 1.15, 1.05, TEAL);
  s.addText("AI as a first-class,\ngoverned collaborator", { x: 0.9, y: 2.45, w: 11.5, h: 1.7, fontFace: HF, fontSize: 44, bold: true, color: WHITE, lineSpacingMultiple: 1.02, margin: 0 });
  const tags = ["Grounded", "Attributable", "Gated", "Human-owned"];
  let tx = 0.95;
  tags.forEach((t) => {
    const w2 = 0.55 + t.length * 0.135;
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: tx, y: 4.55, w: w2, h: 0.62, fill: { color: NAVY2 }, line: { color: TEAL, width: 1 }, rectRadius: 0.31 });
    s.addText(t, { x: tx, y: 4.55, w: w2, h: 0.62, fontFace: BF, fontSize: 14, bold: true, color: TEAL, align: "center", valign: "middle", margin: 0 });
    tx += w2 + 0.3;
  });
  s.addText("Bootstrap a governed AI-SDLC into your next repo in one command.", { x: 0.95, y: 5.6, w: 11, h: 0.5, fontFace: BF, fontSize: 16, color: DIM, margin: 0 });
  s.addText("AI-SDLC Bootstrap Kit  ·  README.md → docs/SPEC.md → template/AGENTS.md", { x: 0.95, y: 6.35, w: 11.5, h: 0.4, fontFace: BF, fontSize: 12, italic: true, color: PERI, margin: 0 });

  await p.writeFile({ fileName: "/Users/georgiandinca/ps/AI/SDLC/docs/presentation/ai-sdlc-bootstrap.pptx" });
  console.log("WROTE ai-sdlc-bootstrap.pptx");
})();
