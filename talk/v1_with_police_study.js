const pptxgen = require("pptxgenjs");
const path = require("path");

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
pres.author = "Center research overview";
pres.title = "Reading the Press at Scale";

// ── Palette ────────────────────────────────────────────────────────────────
const INK = "14161F";
const INK2 = "20242F";
const WHITE = "FFFFFF";
const RED = "A31621";
const REDT = "F6E9EA"; // red tint for callout cards
const SLATE = "2B3A55";
const CARD = "F4F5F7";
const MUTED = "6B7280";
const DIM = "9AA1AE";
const LIGHTTXT = "C3C9D6";

const HEAD = "Cambria";
const BODY = "Calibri";
const MONO = "Courier New";

const IMG = (f) => path.join(__dirname, "img", f);

// ── Helpers (fresh option objects every call) ──────────────────────────────
function shadow() {
  return { type: "outer", color: "9AA1AE", blur: 8, offset: 2, angle: 90, opacity: 0.22 };
}

function lightSlide() {
  const s = pres.addSlide();
  s.background = { color: WHITE };
  return s;
}

function darkSlide() {
  const s = pres.addSlide();
  s.background = { color: INK };
  s.addShape(pres.ShapeType.ellipse, {
    x: 9.9, y: -1.5, w: 5.4, h: 5.4, fill: { color: RED, transparency: 88 }, line: { color: RED, transparency: 72, width: 1 },
  });
  s.addShape(pres.ShapeType.ellipse, {
    x: 11.4, y: 4.6, w: 3.4, h: 3.4, fill: { color: RED, transparency: 92 }, line: { type: "none" },
  });
  return s;
}

function title(s, text, opts = {}) {
  s.addText(text, {
    x: 0.65, y: opts.y || 0.36, w: 12.0, h: opts.h || 0.72, margin: 0,
    fontFace: HEAD, fontSize: opts.size || 34, bold: true, color: opts.color || INK,
    align: "left", valign: "middle",
  });
}

function kicker(s, text, opts = {}) {
  s.addText(text, {
    x: opts.x || 0.65, y: opts.y || 0.36, w: opts.w || 6.0, h: 0.3, margin: 0,
    fontFace: BODY, fontSize: 11, bold: true, charSpacing: 2.4,
    color: opts.color || RED, align: "left", valign: "middle",
  });
}

function card(s, o) {
  s.addShape(pres.ShapeType.roundRect, {
    x: o.x, y: o.y, w: o.w, h: o.h, rectRadius: 0.07,
    fill: { color: o.fill || CARD }, line: { type: "none" }, shadow: shadow(),
  });
}

function badge(s, x, y, label, opts = {}) {
  const d = opts.d || 0.42;
  s.addShape(pres.ShapeType.ellipse, {
    x, y, w: d, h: d, fill: { color: opts.fill || RED }, line: { type: "none" },
  });
  s.addText(label, {
    x, y, w: d, h: d, margin: 0, fontFace: BODY, fontSize: opts.size || 13, bold: true,
    color: WHITE, align: "center", valign: "middle",
  });
}

function src(s, text) {
  s.addText(text, {
    x: 0.65, y: 6.95, w: 12.0, h: 0.3, margin: 0,
    fontFace: BODY, fontSize: 9.5, italic: true, color: MUTED, align: "left", valign: "middle",
  });
}

// ═══════════════════════════════════════════════════════════════ 1. TITLE
{
  const s = darkSlide();
  kicker(s, "15-MINUTE OVERVIEW", { y: 1.5, color: "E0757F" });
  s.addText("Reading the Press at Scale", {
    x: 0.65, y: 1.92, w: 9.6, h: 1.0, margin: 0,
    fontFace: HEAD, fontSize: 46, bold: true, color: WHITE, valign: "middle",
  });
  s.addText("Doing research on media coverage of criminal justice", {
    x: 0.65, y: 3.0, w: 9.4, h: 0.5, margin: 0,
    fontFace: BODY, fontSize: 20, color: LIGHTTXT, valign: "middle",
  });
  s.addText(
    [
      { text: "Bay Area prosecutors", options: { bold: true } },
      { text: "     ·     " },
      { text: "GDELT", options: { bold: true } },
      { text: "     ·     " },
      { text: "the Boudin recall", options: { bold: true } },
    ],
    { x: 0.65, y: 4.05, w: 9.4, h: 0.4, margin: 0, fontFace: BODY, fontSize: 15, color: "E0757F", valign: "middle" }
  );
  s.addText("Prepared for the Center team  ·  August 2026", {
    x: 0.65, y: 6.35, w: 8.0, h: 0.35, margin: 0,
    fontFace: BODY, fontSize: 12.5, color: DIM, valign: "middle",
  });
  s.addNotes(
    "0:00-0:45. Two things I want you to leave with: (1) coverage of criminal justice is now measurable at scale and cheaply, and (2) the measurement choices matter more than the headline number. I'll use two of my own studies as the worked examples, and GDELT as the tool I wish I'd used from the start."
  );
}

// ═══════════════════════════════════════════════════════ 2. WHY IT MATTERS
{
  const s = lightSlide();
  title(s, "Coverage is a legal question, not a comms question", { size: 30 });

  const rows = [
    ["1", "Coverage is part of the decision environment",
      "Jury pools, DA elections, and legislative appetite for reform all move with how cases get told. It is an input to outcomes you litigate."],
    ["2", "Prosecutors are structurally under-covered",
      "In this Bay Area corpus, 82% of crime articles mention police and 15% mention the district attorney. The scarce coverage that exists carries a lot of weight."],
    ["3", "And it is now cheap to measure",
      "Six years of local reporting can be read end to end in an afternoon. That changes what you can put in a brief, a memo, or a motion."],
  ];
  let y = 1.55;
  rows.forEach(([n, h, b]) => {
    badge(s, 0.68, y + 0.06, n);
    s.addText(h, {
      x: 1.3, y, w: 5.6, h: 0.38, margin: 0,
      fontFace: BODY, fontSize: 16.5, bold: true, color: SLATE, valign: "middle",
    });
    s.addText(b, {
      x: 1.3, y: y + 0.42, w: 5.6, h: 0.95, margin: 0,
      fontFace: BODY, fontSize: 13, color: "3F4757", valign: "top", lineSpacingMultiple: 1.12,
    });
    y += 1.62;
  });

  card(s, { x: 7.35, y: 1.55, w: 5.3, h: 4.4 });
  s.addText("WHO GETS WRITTEN ABOUT", {
    x: 7.7, y: 1.8, w: 4.6, h: 0.3, margin: 0,
    fontFace: BODY, fontSize: 10.5, bold: true, charSpacing: 1.8, color: MUTED, valign: "middle",
  });
  s.addText("82%", {
    x: 7.7, y: 2.2, w: 4.6, h: 1.0, margin: 0,
    fontFace: HEAD, fontSize: 66, bold: true, color: SLATE, valign: "middle",
  });
  s.addText("of crime articles mention the police", {
    x: 7.7, y: 3.18, w: 4.6, h: 0.32, margin: 0,
    fontFace: BODY, fontSize: 13, color: "3F4757", valign: "middle",
  });
  s.addText("15%", {
    x: 7.7, y: 3.75, w: 4.6, h: 1.0, margin: 0,
    fontFace: HEAD, fontSize: 66, bold: true, color: RED, valign: "middle",
  });
  s.addText("mention the district attorney", {
    x: 7.7, y: 4.73, w: 4.6, h: 0.32, margin: 0,
    fontFace: BODY, fontSize: 13, color: "3F4757", valign: "middle",
  });
  s.addText("The most consequential actor in the system is close to invisible in the reporting about it.", {
    x: 7.7, y: 5.15, w: 4.6, h: 0.65, margin: 0,
    fontFace: BODY, fontSize: 11.5, italic: true, color: MUTED, valign: "top", lineSpacingMultiple: 1.1,
  });
  src(s, "Corpus: 12,827 prosecutor-attributed Bay Area articles, 2019-2024. Coverage-deficit finding consistent with Hessick & Thornburg (2023).");
  s.addNotes("0:45-2:15. Anchor on the 82/15 split. This is why prosecutor coverage is high-leverage: there is so little of it that each article does more work.");
}

// ══════════════════════════════════════════════════════ 3. TWO STUDIES
{
  const s = lightSlide();
  title(s, "Two studies, one event");

  card(s, { x: 0.65, y: 1.5, w: 5.85, h: 3.75 });
  badge(s, 1.0, 1.85, "A", { d: 0.5, size: 15 });
  s.addText("What does the coverage look like?", {
    x: 1.0, y: 2.45, w: 5.15, h: 0.5, margin: 0,
    fontFace: HEAD, fontSize: 21, bold: true, color: SLATE, valign: "top",
  });
  s.addText("12,827 attributed articles, 2019-2024. Four NLP measures of tone, stance, thematic salience and framing, across five Bay Area prosecutors in three counties.", {
    x: 1.0, y: 3.05, w: 5.15, h: 1.3, margin: 0,
    fontFace: BODY, fontSize: 13.5, color: "3F4757", valign: "top", lineSpacingMultiple: 1.15,
  });
  s.addText("MEASURES THE PRESS", {
    x: 1.0, y: 4.6, w: 5.15, h: 0.3, margin: 0,
    fontFace: BODY, fontSize: 10.5, bold: true, charSpacing: 1.8, color: RED, valign: "middle",
  });

  card(s, { x: 6.85, y: 1.5, w: 5.85, h: 3.75 });
  badge(s, 7.2, 1.85, "B", { d: 0.5, size: 15 });
  s.addText("What did the coverage do?", {
    x: 7.2, y: 2.45, w: 5.15, h: 0.5, margin: 0,
    fontFace: HEAD, fontSize: 21, bold: true, color: SLATE, valign: "top",
  });
  s.addText("A regression kink design around the 7 June 2022 recall. SFPD stops, arrests, officer reports, citizen calls, charging decisions and the jail population, week by week.", {
    x: 7.2, y: 3.05, w: 5.15, h: 1.3, margin: 0,
    fontFace: BODY, fontSize: 13.5, color: "3F4757", valign: "top", lineSpacingMultiple: 1.15,
  });
  s.addText("MEASURES THE BEHAVIOUR", {
    x: 7.2, y: 4.6, w: 5.15, h: 0.3, margin: 0,
    fontFace: BODY, fontSize: 10.5, bold: true, charSpacing: 1.8, color: RED, valign: "middle",
  });

  card(s, { x: 0.65, y: 5.5, w: 12.05, h: 1.15, fill: REDT });
  s.addText(
    [
      { text: "Same city, same years, same event — and neither one measures the link between them.", options: { bold: true } },
      { text: "  That gap is where GDELT comes in." },
    ],
    { x: 1.05, y: 5.5, w: 11.3, h: 1.15, margin: 0, fontFace: BODY, fontSize: 15, color: "6D1119", valign: "middle", lineSpacingMultiple: 1.1 }
  );
  s.addNotes("2:15-3:15. Set up the whole talk: study A reads the press, study B watches behaviour around a media-saturated election. The thing I could not do was connect them at weekly resolution. Hold that thought.");
}

// ══════════════════════════════════════════════════════ 4. STUDY A BUILD
{
  const s = lightSlide();
  title(s, "Study A — building the corpus");

  const funnel = [
    ["136,313", "articles pulled", "LexisNexis, 21 Bay Area outlets, Jan 2019 - Dec 2024"],
    ["107,713", "crime and justice", "keyword pre-filter, then a zero-shot topic classifier"],
    ["12,827", "attributed to a DA", "regex name matching with disambiguation and a time filter"],
  ];
  let x = 0.65;
  funnel.forEach(([big, lab, note], i) => {
    card(s, { x, y: 1.45, w: 3.75, h: 1.95 });
    s.addText(big, {
      x: x + 0.3, y: 1.6, w: 3.15, h: 0.72, margin: 0,
      fontFace: HEAD, fontSize: 38, bold: true, color: i === 2 ? RED : SLATE, valign: "middle",
    });
    s.addText(lab, {
      x: x + 0.3, y: 2.32, w: 3.15, h: 0.28, margin: 0,
      fontFace: BODY, fontSize: 13, bold: true, color: SLATE, valign: "middle",
    });
    s.addText(note, {
      x: x + 0.3, y: 2.6, w: 3.15, h: 0.66, margin: 0,
      fontFace: BODY, fontSize: 10.5, color: MUTED, valign: "top", lineSpacingMultiple: 1.08,
    });
    if (i < 2) {
      s.addText("→", {
        x: x + 3.78, y: 1.45, w: 0.5, h: 1.95, margin: 0,
        fontFace: BODY, fontSize: 26, bold: true, color: DIM, align: "center", valign: "middle",
      });
    }
    x += 4.28;
  });

  s.addText("Who the articles are about", {
    x: 0.65, y: 3.6, w: 7.3, h: 0.35, margin: 0,
    fontFace: BODY, fontSize: 14, bold: true, color: SLATE, valign: "middle",
  });
  const rows = [
    [
      { text: "Prosecutor", options: { bold: true, color: WHITE, fill: { color: SLATE } } },
      { text: "County", options: { bold: true, color: WHITE, fill: { color: SLATE } } },
      { text: "Orientation", options: { bold: true, color: WHITE, fill: { color: SLATE } } },
      { text: "Articles", options: { bold: true, color: WHITE, fill: { color: SLATE }, align: "right" } },
    ],
    ["Chesa Boudin", "San Francisco", "Progressive", { text: "5,783", options: { align: "right" } }],
    ["Brooke Jenkins", "San Francisco", "Traditional", { text: "3,097", options: { align: "right" } }],
    ["Nancy O'Malley", "Alameda", "Traditional", { text: "1,497", options: { align: "right" } }],
    ["Pamela Price", "Alameda", "Progressive", { text: "802", options: { align: "right" } }],
    ["Steve Wagstaffe", "San Mateo", "Traditional", { text: "1,648", options: { align: "right" } }],
  ];
  s.addTable(rows, {
    x: 0.65, y: 4.0, w: 7.3, colW: [2.4, 1.85, 1.75, 1.3],
    rowH: 0.34, fontFace: BODY, fontSize: 12, color: "3F4757",
    border: { type: "solid", color: "E3E6EC", pt: 1 }, fill: { color: WHITE },
    valign: "middle", margin: [0.04, 0.1, 0.04, 0.1],
  });

  card(s, { x: 8.35, y: 3.6, w: 4.35, h: 2.8, fill: REDT });
  badge(s, 8.7, 3.9, "!");
  s.addText("Attribution is the hard part", {
    x: 8.7, y: 4.45, w: 3.65, h: 0.35, margin: 0,
    fontFace: BODY, fontSize: 15, bold: true, color: "6D1119", valign: "middle",
  });
  s.addText("Requiring a first name or a title near every surname match removed 126 false positives and reassigned 26 articles — pieces about other people named Jenkins or Price. That one fix erased one of our headline results.", {
    x: 8.7, y: 4.85, w: 3.65, h: 1.4, margin: 0,
    fontFace: BODY, fontSize: 12, color: "6D1119", valign: "top", lineSpacingMultiple: 1.12,
  });
  src(s, "Counts from output/06_stats_results.json. Progressive 6,585 / Traditional 6,242.");
  s.addNotes("3:15-4:45. The pipeline is boring; the attribution step is not. Emphasise the 126 false positives: name matching looks trivial and it is the single largest source of error we found.");
}

// ══════════════════════════════════════════════════ 5. BIAS IS NOT ONE THING
{
  const s = lightSlide();
  title(s, "Bias is not one thing");
  s.addImage({ path: IMG("forest.png"), x: 0.55, y: 1.35, w: 7.3, h: 4.09 });
  s.addText("Each row is the same corpus, a different instrument. Green band = negligible.", {
    x: 0.55, y: 5.5, w: 7.3, h: 0.3, margin: 0,
    fontFace: BODY, fontSize: 10.5, italic: true, color: MUTED, valign: "middle",
  });

  s.addText("Four defensible measures, three different answers", {
    x: 8.1, y: 1.35, w: 4.6, h: 0.75, margin: 0,
    fontFace: BODY, fontSize: 16.5, bold: true, color: SLATE, valign: "top", lineSpacingMultiple: 1.08,
  });
  s.addText(
    [
      { text: "Stance classification", options: { bold: true, breakLine: false } },
      { text: "  d = -0.34", options: { color: RED, bold: true, breakLine: true } },
      { text: "Critical coverage of reform DAs. Survives every control.", options: { fontSize: 11.5, color: MUTED, breakLine: true, paraSpaceAfter: 8 } },
      { text: "Keyword salience", options: { bold: true, breakLine: false } },
      { text: "  d = -0.20", options: { color: RED, bold: true, breakLine: true } },
      { text: "Anti-prosecutor themes near the DA's name.", options: { fontSize: 11.5, color: MUTED, breakLine: true, paraSpaceAfter: 8 } },
      { text: "Aspect + document tone", options: { bold: true, breakLine: false } },
      { text: "  d = +0.05", options: { color: SLATE, bold: true, breakLine: true } },
      { text: "Statistically equivalent to zero. Points the other way.", options: { fontSize: 11.5, color: MUTED, breakLine: true, paraSpaceAfter: 8 } },
      { text: "Attributed critical themes", options: { bold: true, breakLine: false } },
      { text: "  |d| = 0.42", options: { color: RED, bold: true, breakLine: true } },
      { text: "The largest single effect in the study.", options: { fontSize: 11.5, color: MUTED } },
    ],
    { x: 8.1, y: 2.2, w: 4.6, h: 2.9, margin: 0, fontFace: BODY, fontSize: 13, color: "3F4757", valign: "top", lineSpacingMultiple: 1.05 }
  );
  card(s, { x: 8.1, y: 4.5, w: 4.6, h: 1.6, fill: REDT });
  s.addText(
    [
      { text: "Composite d = -0.151, p < .0001.", options: { bold: true, breakLine: true } },
      { text: "Drop the stance method and it becomes +0.025, p = 0.15 — a null. The index is carried by one instrument.", options: {} },
    ],
    { x: 8.42, y: 4.5, w: 3.96, h: 1.6, margin: 0, fontFace: BODY, fontSize: 12.5, color: "6D1119", valign: "middle", lineSpacingMultiple: 1.12 }
  );
  s.addNotes("4:45-6:15. The key slide of part one. Same articles, four defensible instruments, and they disagree in sign. If someone hands you 'a study found media bias,' the first question is which instrument, and whether the result survives dropping it.");
}

// ═══════════════════════════════════════════════════ 6. THE HONEST VERSION
{
  const s = lightSlide();
  title(s, "What the honest version of that slide looks like");

  const cols = [
    ["1", "The index is fragile",
      "Remove one of four methods and the headline difference disappears (d = +0.025, p = 0.15). We report the decomposition, not the composite alone."],
    ["2", "The model cannot read one article",
      "Against a human coder, article-level stance agreement was no better than chance (kappa = 0.049). The continuous score is still correctly ordered in human labels (AUC = 0.69)."],
    ["3", "Errors are not random",
      "The 126 mis-attributed articles clustered after one prosecutor took office. Removing them turned a significant post-recall level shift into p = 0.07."],
  ];
  let x = 0.65;
  cols.forEach(([n, h, b]) => {
    card(s, { x, y: 1.45, w: 3.9, h: 3.15 });
    badge(s, x + 0.32, 1.72, n);
    s.addText(h, {
      x: x + 0.32, y: 2.26, w: 3.26, h: 0.6, margin: 0,
      fontFace: BODY, fontSize: 16, bold: true, color: SLATE, valign: "top", lineSpacingMultiple: 1.05,
    });
    s.addText(b, {
      x: x + 0.32, y: 2.92, w: 3.26, h: 1.45, margin: 0,
      fontFace: BODY, fontSize: 12.5, color: "3F4757", valign: "top", lineSpacingMultiple: 1.14,
    });
    x += 4.13;
  });

  card(s, { x: 0.65, y: 4.95, w: 12.05, h: 1.5, fill: INK });
  s.addText(
    [
      { text: "Aggregate contrasts: yes.   “This article is biased”: never.", options: { bold: true, fontSize: 18, color: WHITE, breakLine: true } },
      { text: "For litigation that distinction is the whole ballgame — a measure that works in expectation is not evidence about a document.", options: { fontSize: 13, color: LIGHTTXT } },
    ],
    { x: 1.05, y: 4.95, w: 11.3, h: 1.5, margin: 0, fontFace: BODY, valign: "middle", lineSpacingMultiple: 1.25 }
  );
  s.addNotes("6:15-7:30. This is the slide I would want a lawyer to remember. Say plainly: our own validation failed at the article level and we published that. Any expert who cannot show you their agreement statistic has not done this step.");
}

// ═══════════════════════════════════════════════════════ 7. DIVIDER: GDELT
{
  const s = darkSlide();
  kicker(s, "PART TWO", { y: 2.05, color: "E0757F" });
  s.addText("GDELT", {
    x: 0.65, y: 2.45, w: 8.0, h: 1.15, margin: 0,
    fontFace: HEAD, fontSize: 60, bold: true, color: WHITE, valign: "middle",
  });
  s.addText("A free, public, near-real-time index of what the world's news is talking about", {
    x: 0.65, y: 3.7, w: 8.6, h: 0.8, margin: 0,
    fontFace: BODY, fontSize: 19, color: LIGHTTXT, valign: "top", lineSpacingMultiple: 1.15,
  });
  s.addText("The bottleneck in this kind of research is almost never the analysis. It is getting the coverage in the first place.", {
    x: 0.65, y: 4.85, w: 8.2, h: 0.7, margin: 0,
    fontFace: BODY, fontSize: 14, italic: true, color: DIM, valign: "top", lineSpacingMultiple: 1.15,
  });
  s.addNotes("7:30-7:45. Quick pivot. One line: everything in part one cost a LexisNexis licence and six months. Part two is what you can do for free, today.");
}

// ═══════════════════════════════════════════════════════ 8. WHAT GDELT IS
{
  const s = lightSlide();
  title(s, "What it is");
  s.addText("The Global Database of Events, Language and Tone. Public, free, no licence, no API key.", {
    x: 0.65, y: 1.12, w: 12.0, h: 0.35, margin: 0,
    fontFace: BODY, fontSize: 15, color: "3F4757", valign: "middle",
  });

  const cards = [
    ["Event Database", "1979 to present. Machine-coded actor-action-actor records on the CAMEO taxonomy: 300+ event types, geolocated to city level."],
    ["Global Knowledge Graph", "Themes, people, organisations, places and tone for every monitored article — plus 2,230+ GCAM emotional and thematic dimensions."],
    ["Television", "163 stations from the Internet Archive's TV News Archive, 2009 to present, searchable by caption text. Local stations included."],
  ];
  let x = 0.65;
  cards.forEach(([h, b]) => {
    card(s, { x, y: 1.62, w: 3.9, h: 1.95 });
    s.addText(h, {
      x: x + 0.32, y: 1.84, w: 3.26, h: 0.35, margin: 0,
      fontFace: HEAD, fontSize: 17, bold: true, color: SLATE, valign: "middle",
    });
    s.addText(b, {
      x: x + 0.32, y: 2.24, w: 3.26, h: 1.15, margin: 0,
      fontFace: BODY, fontSize: 12, color: "3F4757", valign: "top", lineSpacingMultiple: 1.14,
    });
    x += 4.13;
  });

  const facts = [["65", "languages, live-translated"], ["15 min", "refresh cycle, worldwide"], ["$0", "no licence, no API key"]];
  x = 0.65;
  facts.forEach(([big, lab]) => {
    s.addText(big, {
      x, y: 3.78, w: 3.9, h: 0.5, margin: 0,
      fontFace: HEAD, fontSize: 27, bold: true, color: RED, valign: "middle",
    });
    s.addText(lab, {
      x, y: 4.26, w: 3.9, h: 0.3, margin: 0,
      fontFace: BODY, fontSize: 12, color: MUTED, valign: "middle",
    });
    x += 4.13;
  });

  card(s, { x: 0.65, y: 4.8, w: 12.05, h: 1.55, fill: REDT });
  badge(s, 1.05, 5.2, "!");
  s.addText(
    [
      { text: "The catch: GDELT indexes coverage, it does not host it.", options: { bold: true, fontSize: 16, breakLine: true } },
      { text: "You get tone, themes, entities, dates and a URL — not the article body. Anything that requires reading the text still needs LexisNexis, the outlet, or the documents themselves.", options: { fontSize: 12.5 } },
    ],
    { x: 1.7, y: 4.8, w: 10.65, h: 1.55, margin: 0, fontFace: BODY, color: "6D1119", valign: "middle", lineSpacingMultiple: 1.15 }
  );
  src(s, "gdeltproject.org/data.html. GCAM: 18 content-analysis systems, 2,230+ dimensions.");
  s.addNotes("7:45-9:15. Three products. Land the catch hard — people assume GDELT is a full-text archive and design a project around that mistake. It is an index plus a measurement layer.");
}

// ═══════════════════════════════════════════════════════ 9. HOW TO USE IT
{
  const s = lightSlide();
  title(s, "How to actually use it");

  const tiers = [
    ["1", "Point and click", "Television Explorer and GDELT Summary. Zero code, CSV export, chartable in the browser. Enough for a memo exhibit or a hearing."],
    ["2", "DOC 2.0 API", "One URL, no key, JSON or CSV back. Full-text search to 1 Jan 2017. Ceilings: 250 records per call, 3-month default window, one request every 5 seconds."],
    ["3", "BigQuery", "gdelt-bq.gdeltv2.gkg_partitioned. The whole archive in SQL, refreshed every 15 minutes. Query the partitioned tables or the bill grows fast."],
  ];
  let y = 1.4;
  tiers.forEach(([n, h, b]) => {
    card(s, { x: 0.65, y, w: 12.05, h: 0.95 });
    badge(s, 1.0, y + 0.26, n);
    s.addText(h, {
      x: 1.62, y, w: 2.85, h: 0.95, margin: 0,
      fontFace: BODY, fontSize: 15.5, bold: true, color: SLATE, valign: "middle",
    });
    s.addText(b, {
      x: 4.5, y, w: 7.85, h: 0.95, margin: 0,
      fontFace: BODY, fontSize: 12.5, color: "3F4757", valign: "middle", lineSpacingMultiple: 1.12,
    });
    y += 1.1;
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: 0.65, y: 4.8, w: 12.05, h: 1.6, rectRadius: 0.06,
    fill: { color: INK }, line: { type: "none" }, shadow: shadow(),
  });
  s.addText(
    [
      { text: "https://api.gdeltproject.org/api/v2/doc/doc", options: { color: "8FD8B0", breakLine: true } },
      { text: "  ?query=\"Chesa Boudin\"   &mode=timelinevol", options: { color: WHITE, breakLine: true } },
      { text: "  &startdatetime=20220101000000   &enddatetime=20221231000000   &format=json", options: { color: WHITE } },
    ],
    { x: 1.0, y: 4.8, w: 11.4, h: 1.6, margin: 0, fontFace: MONO, fontSize: 13, valign: "middle", lineSpacingMultiple: 1.35 }
  );
  s.addText("Swap mode= for artlist (articles with URLs), timelinetone, tonechart, or wordcloudimagetags. Narrow with domain:sfchronicle.com, sourcecountry:US, or theme:ARREST.", {
    x: 0.65, y: 6.58, w: 12.05, h: 0.55, margin: 0,
    fontFace: BODY, fontSize: 11.5, italic: true, color: MUTED, valign: "top", lineSpacingMultiple: 1.1,
  });
  s.addNotes("9:15-10:30. Tier 2 is the sweet spot for our work — paste the URL in a browser and you have data. Mention the 5-second rate limit; I got throttled preparing this. For anything serious, BigQuery.");
}

// ═══════════════════════════════════════════════════ 10. RECALL: BEHAVIOUR
{
  const s = lightSlide();
  title(s, "Study B — what the police did around the recall");
  s.addText("Regression kink design at 7 June 2022: the night the result was known, and four weeks before any new DA took office.", {
    x: 0.65, y: 1.06, w: 12.05, h: 0.35, margin: 0,
    fontFace: BODY, fontSize: 13.5, color: "3F4757", valign: "middle",
  });

  s.addImage({ path: IMG("stops.png"), x: 0.75, y: 1.55, w: 5.3, h: 3.79 });
  s.addImage({ path: IMG("calls.png"), x: 7.25, y: 1.55, w: 5.3, h: 3.79 });

  s.addText(
    [
      { text: "Officer-initiated stops.", options: { bold: true, breakLine: true } },
      { text: "-0.17 per week before, +0.38 after. Slope shift 0.558, p < .001.", options: { fontSize: 12 } },
    ],
    { x: 0.75, y: 5.42, w: 5.3, h: 0.7, margin: 0, fontFace: BODY, fontSize: 13, color: SLATE, valign: "top", lineSpacingMultiple: 1.1 }
  );
  s.addText(
    [
      { text: "Citizen calls for service.", options: { bold: true, breakLine: true } },
      { text: "No kink. Same null for reports residents filed online.", options: { fontSize: 12 } },
    ],
    { x: 7.25, y: 5.42, w: 5.3, h: 0.7, margin: 0, fontFace: BODY, fontSize: 13, color: SLATE, valign: "top", lineSpacingMultiple: 1.1 }
  );

  card(s, { x: 0.65, y: 6.2, w: 12.05, h: 0.8, fill: REDT });
  s.addText(
    [
      { text: "About 30 more stops and 49 more arrests in ten weeks", options: { bold: true } },
      { text: " — with no change in what the public reported. Enforcement effort moved; crime did not." },
    ],
    { x: 1.05, y: 6.2, w: 11.3, h: 0.8, margin: 0, fontFace: BODY, fontSize: 13.5, color: "6D1119", valign: "middle" }
  );
  s.addNotes("10:30-11:45. The two panels are the whole argument: discretionary police activity kinks at the election, citizen-initiated activity does not. Arrests move the same way as stops: -0.26 to +0.64 per week, shift 0.90, p < .001. Effects concentrate in traffic, property and public-order stops, not violent crime — less discretion there.");
}

// ══════════════════════════════════════════════════════════ 11. JAIL
{
  const s = lightSlide();
  title(s, "And it lands in a jail");

  s.addImage({ path: IMG("jail.png"), x: 0.65, y: 1.5, w: 5.5, h: 3.93 });
  s.addText("SF jail population, weeks relative to the recall election.", {
    x: 0.65, y: 5.5, w: 5.5, h: 0.3, margin: 0,
    fontFace: BODY, fontSize: 10.5, italic: true, color: MUTED, valign: "middle",
  });

  card(s, { x: 6.6, y: 1.5, w: 6.1, h: 1.5 });
  const stats = [["902", "extra jail\nperson-days"], [">$270k", "at ~$300 a day\nin San Francisco"], [">$1.4M", "annualised cost\nin the paper"]];
  let sx = 6.85;
  stats.forEach(([big, lab]) => {
    s.addText(big, {
      x: sx, y: 1.62, w: 1.85, h: 0.62, margin: 0,
      fontFace: HEAD, fontSize: 27, bold: true, color: RED, valign: "middle",
    });
    s.addText(lab, {
      x: sx, y: 2.22, w: 1.85, h: 0.65, margin: 0,
      fontFace: BODY, fontSize: 10.5, color: MUTED, valign: "top", lineSpacingMultiple: 1.05,
    });
    sx += 1.9;
  });

  card(s, { x: 6.6, y: 3.15, w: 6.1, h: 1.1 });
  s.addText(
    [
      { text: "Charges flat, discharges up.", options: { bold: true, breakLine: true } },
      { text: "Prosecutors saw more cases, not better ones — the police supplied more marginal arrests.", options: { fontSize: 12 } },
    ],
    { x: 6.95, y: 3.15, w: 5.4, h: 1.1, margin: 0, fontFace: BODY, fontSize: 13, color: "3F4757", valign: "middle", lineSpacingMultiple: 1.12 }
  );
  card(s, { x: 6.6, y: 4.4, w: 6.1, h: 1.1 });
  s.addText(
    [
      { text: "Concentrated where discretion lives.", options: { bold: true, breakLine: true } },
      { text: "Traffic, property and public-order stops moved. Violent-crime stops did not — less room to choose.", options: { fontSize: 12 } },
    ],
    { x: 6.95, y: 4.4, w: 5.4, h: 1.1, margin: 0, fontFace: BODY, fontSize: 13, color: "3F4757", valign: "middle", lineSpacingMultiple: 1.12 }
  );

  card(s, { x: 0.65, y: 6.0, w: 12.05, h: 0.95, fill: INK });
  s.addText(
    [
      { text: "A media-saturated election changed who sat in a cell.", options: { bold: true, fontSize: 16, color: WHITE, breakLine: true } },
      { text: "No statute changed, no new DA had taken office, and no more crime was reported.", options: { fontSize: 12.5, color: LIGHTTXT } },
    ],
    { x: 1.05, y: 6.0, w: 11.3, h: 0.95, margin: 0, fontFace: BODY, valign: "middle", lineSpacingMultiple: 1.15 }
  );
  s.addNotes("11:45-12:45. This is the payoff for a legal audience: a political event, transmitted through coverage, produced real custody with no change in law and no change in reported crime. Note the discharge finding: quality of cases fell.");
}

// ══════════════════════════════════════════════════ 12. WHERE GDELT HELPS
{
  const s = lightSlide();
  title(s, "Where GDELT would have made that study better");
  s.addText("We measured coverage in one dataset (LexisNexis, monthly) and behaviour in another (SFPD, weekly). We never had a measure of attention at the resolution the design needs.", {
    x: 0.65, y: 1.06, w: 12.05, h: 0.6, margin: 0,
    fontFace: BODY, fontSize: 13.5, color: "3F4757", valign: "top", lineSpacingMultiple: 1.12,
  });

  const items = [
    ["1", "Put attention on the same axis",
      "A daily coverage-volume series for \"Boudin\" and \"recall\", plotted against the enforcement kink. Does the turn track coverage, or only the ballot date?"],
    ["2", "Controls, for free",
      "The identical query for Alameda and San Mateo — the untreated county the interrupted-time-series already leans on. One more line of code, not one more licence."],
    ["3", "Local television",
      "This fight ran on KRON, KTVU and KPIX. Captions are searchable back to 2009. LexisNexis barely covers broadcast, so we simply missed that channel."],
    ["4", "Tone before the vote",
      "The SFPD-DA conflict opened in February 2022 when the chief withdrew from the use-of-force MOU. A tone timeline tests whether the shift began then, not in June."],
  ];
  const pos = [[0.65, 1.9], [6.9, 1.9], [0.65, 3.95], [6.9, 3.95]];
  items.forEach(([n, h, b], i) => {
    const [cx, cy] = pos[i];
    card(s, { x: cx, y: cy, w: 5.8, h: 1.8 });
    badge(s, cx + 0.3, cy + 0.26, n);
    s.addText(h, {
      x: cx + 0.92, y: cy + 0.2, w: 4.55, h: 0.38, margin: 0,
      fontFace: BODY, fontSize: 15.5, bold: true, color: SLATE, valign: "middle",
    });
    s.addText(b, {
      x: cx + 0.3, y: cy + 0.7, w: 5.2, h: 1.0, margin: 0,
      fontFace: BODY, fontSize: 12, color: "3F4757", valign: "top", lineSpacingMultiple: 1.14,
    });
  });

  s.addText("None of this requires a new data purchase. All of it is a URL.", {
    x: 0.65, y: 6.1, w: 12.05, h: 0.45, margin: 0,
    fontFace: BODY, fontSize: 15, bold: true, color: RED, valign: "middle",
  });
  s.addNotes("12:45-13:30. The honest self-critique, and the strongest argument for the tool. Point 2 is the one economists will care about; point 3 is the one that would have changed the paper.");
}

// ═══════════════════════════════════════════════════ 13. FOUR USES FOR US
{
  const s = lightSlide();
  title(s, "Four things the Center could do with this");

  const items = [
    ["Pretrial publicity and venue",
      "Quantify local saturation with a dated, reproducible pull instead of a stack of clippings: volume by outlet, by week, with every URL attached."],
    ["Watch a reform while you litigate it",
      "How is Prop 36 implementation being framed, county by county, this month? The index refreshes every fifteen minutes."],
    ["Test the narrative against the data",
      "When an agency says crime is surging, put the coverage curve next to its own reported numbers and show the gap."],
    ["Comparison at no marginal cost",
      "The same query runs across 58 California counties, or across states. Scaling up costs time, not money."],
  ];
  const pos = [[0.65, 1.5], [6.9, 1.5], [0.65, 3.5], [6.9, 3.5]];
  items.forEach(([h, b], i) => {
    const [cx, cy] = pos[i];
    card(s, { x: cx, y: cy, w: 5.8, h: 1.75 });
    badge(s, cx + 0.3, cy + 0.26, String(i + 1));
    s.addText(h, {
      x: cx + 0.92, y: cy + 0.2, w: 4.55, h: 0.38, margin: 0,
      fontFace: BODY, fontSize: 15.5, bold: true, color: SLATE, valign: "middle",
    });
    s.addText(b, {
      x: cx + 0.3, y: cy + 0.7, w: 5.2, h: 0.95, margin: 0,
      fontFace: BODY, fontSize: 12, color: "3F4757", valign: "top", lineSpacingMultiple: 1.14,
    });
  });

  card(s, { x: 0.65, y: 5.55, w: 12.05, h: 1.1, fill: REDT });
  s.addText(
    [
      { text: "Rule of thumb: ", options: { bold: true } },
      { text: "GDELT for attention and timing. LexisNexis, or the documents themselves, for what was actually said." },
    ],
    { x: 1.05, y: 5.55, w: 11.3, h: 1.1, margin: 0, fontFace: BODY, fontSize: 14.5, color: "6D1119", valign: "middle" }
  );
  s.addNotes("13:30-14:15. Move fast here and invite them to pick one. The venue application is the one that usually lands with litigators.");
}

// ═════════════════════════════════════════════ 14. WHAT AN OPPONENT SAYS
{
  const s = lightSlide();
  title(s, "What a good opponent will say — and the answer");

  const rows = [
    ["“Your sample isn't a census.”",
      "Correct. GDELT's source list grows over time. So archive every pull with its date and query string, and state the frame as a limitation rather than hiding it."],
    ["“Volume isn't reach.”",
      "Also correct — there is no audience weighting. Volume measures editorial attention, which is the thing that moves officials. Claim that, and nothing more."],
    ["“Tone isn't bias.”",
      "Right. Tone is a dictionary score. It supports comparisons between groups; it does not establish that any single article was slanted."],
    ["“Your classifier is unvalidated.”",
      "This is the one that bites. Hand-code a stratified sample and report the agreement statistic even when it is bad. Ours was kappa = 0.049 at the article level."],
  ];
  let y = 1.4;
  rows.forEach(([q, a]) => {
    card(s, { x: 0.65, y, w: 12.05, h: 1.05 });
    s.addText(q, {
      x: 1.0, y, w: 3.75, h: 1.05, margin: 0,
      fontFace: HEAD, fontSize: 14.5, bold: true, italic: true, color: RED, valign: "middle", lineSpacingMultiple: 1.05,
    });
    s.addText(a, {
      x: 4.95, y, w: 7.4, h: 1.05, margin: 0,
      fontFace: BODY, fontSize: 12.5, color: "3F4757", valign: "middle", lineSpacingMultiple: 1.14,
    });
    y += 1.2;
  });

  s.addText("Every one of these is answerable — but only if the audit trail exists before the question is asked.", {
    x: 0.65, y: 6.35, w: 12.05, h: 0.45, margin: 0,
    fontFace: BODY, fontSize: 15, bold: true, color: SLATE, valign: "middle",
  });
  s.addNotes("14:15-14:45. Frame this as pre-mortem discipline, not defensiveness. The fourth row is the one to dwell on if there is time.");
}

// ══════════════════════════════════════════════════════ 15. TAKEAWAYS
{
  const s = darkSlide();
  kicker(s, "TAKEAWAYS", { y: 0.75, color: "E0757F" });

  const items = [
    ["1", "The instrument decides the answer.",
      "Four defensible measures of one corpus disagreed in sign. Choose and disclose the measure before you look at the result."],
    ["2", "GDELT for attention; documents for content.",
      "Free, fast, includes local television, back to 2017 by API and 1979 by archive. It will not hand you the article."],
    ["3", "Validate on humans, or you have a number and not a finding.",
      "A score that fails against a hand-coded sample is still a score. Report the agreement statistic either way."],
  ];
  let y = 1.35;
  items.forEach(([n, h, b]) => {
    badge(s, 0.68, y + 0.08, n, { d: 0.46, size: 14 });
    s.addText(h, {
      x: 1.4, y, w: 10.4, h: 0.4, margin: 0,
      fontFace: HEAD, fontSize: 21, bold: true, color: WHITE, valign: "middle",
    });
    s.addText(b, {
      x: 1.4, y: y + 0.44, w: 9.9, h: 0.7, margin: 0,
      fontFace: BODY, fontSize: 13.5, color: LIGHTTXT, valign: "top", lineSpacingMultiple: 1.14,
    });
    y += 1.45;
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: 0.65, y: 5.7, w: 12.05, h: 1.2, rectRadius: 0.06,
    fill: { color: INK2 }, line: { type: "none" },
  });
  s.addText("START HERE", {
    x: 1.0, y: 5.85, w: 3.0, h: 0.3, margin: 0,
    fontFace: BODY, fontSize: 10.5, bold: true, charSpacing: 2, color: "E0757F", valign: "middle",
  });
  s.addText(
    [
      { text: "api.gdeltproject.org/api/v2/doc/doc", options: { color: "8FD8B0" } },
      { text: "      television.gdeltproject.org", options: { color: "8FD8B0" } },
      { text: "      gdelt-bq.gdeltv2  (BigQuery)", options: { color: "8FD8B0" } },
    ],
    { x: 1.0, y: 6.2, w: 11.4, h: 0.5, margin: 0, fontFace: MONO, fontSize: 12.5, valign: "middle" }
  );
  s.addNotes("14:45-15:00. Close on the three links and one ask: bring me a question about coverage and we can have a first answer the same day.");
}

const out = path.join(__dirname, "media_research_overview.pptx");
pres.writeFile({ fileName: out }).then(() => console.log("wrote " + out));
