const pptxgen = require("pptxgenjs");
const path = require("path");

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
pres.author = "Center research overview";
pres.title = "When the Press Covers a Prosecutor";

// ── Palette ────────────────────────────────────────────────────────────────
const INK = "14161F";
const INK2 = "20242F";
const WHITE = "FFFFFF";
const RED = "A31621";
const REDT = "F6E9EA";
const SLATE = "2B3A55";
const CARD = "F4F5F7";
const MUTED = "6B7280";
const DIM = "9AA1AE";
const LIGHTTXT = "C3C9D6";
const BODYTXT = "3F4757";

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
    x: 0.65, y: opts.y || 0.36, w: opts.w || 12.0, h: opts.h || 0.72, margin: 0,
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

function chip(s, o) {
  s.addShape(pres.ShapeType.roundRect, {
    x: o.x, y: o.y, w: o.w, h: o.h, rectRadius: 0.12,
    fill: { color: o.fill }, line: { type: "none" },
  });
  s.addText(o.text, {
    x: o.x, y: o.y, w: o.w, h: o.h, margin: 0,
    fontFace: BODY, fontSize: o.size || 12.5, bold: true, color: o.color || WHITE,
    align: "center", valign: "middle",
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
  s.addText("When the Press Covers a Prosecutor", {
    x: 0.65, y: 1.9, w: 9.4, h: 1.5, margin: 0,
    fontFace: HEAD, fontSize: 42, bold: true, color: WHITE, valign: "middle", lineSpacingMultiple: 1.02,
  });
  s.addText("What six years of Bay Area crime reporting actually said — and how you read the news at scale without fooling yourself", {
    x: 0.65, y: 3.5, w: 9.0, h: 0.9, margin: 0,
    fontFace: BODY, fontSize: 18, color: LIGHTTXT, valign: "top", lineSpacingMultiple: 1.18,
  });
  s.addText("Prepared for the Center team  ·  August 2026", {
    x: 0.65, y: 6.35, w: 8.0, h: 0.35, margin: 0,
    fontFace: BODY, fontSize: 12.5, color: DIM, valign: "middle",
  });
  s.addNotes(
    "0:00-0:40. Frame it as a fight I tried to settle with evidence. Two things I want you to leave with: what the coverage of reform prosecutors actually looked like, and how to tell a real media study from a bad one. Then a few minutes at the end on where this goes next."
  );
}

// ═══════════════════════════════════════════════════════ 2. THE ARGUMENT
{
  const s = lightSlide();
  title(s, "The argument I set out to settle");

  card(s, { x: 0.65, y: 1.5, w: 5.85, h: 3.15 });
  s.addText("“The press was against them.”", {
    x: 1.0, y: 1.85, w: 5.15, h: 0.55, margin: 0,
    fontFace: HEAD, fontSize: 21, bold: true, italic: true, color: RED, valign: "middle",
  });
  s.addText("Reform prosecutors and their supporters said the coverage was relentlessly hostile, and that it helped drive two of them out of office.", {
    x: 1.0, y: 2.55, w: 5.15, h: 1.6, margin: 0,
    fontFace: BODY, fontSize: 14, color: BODYTXT, valign: "top", lineSpacingMultiple: 1.18,
  });

  card(s, { x: 6.85, y: 1.5, w: 5.85, h: 3.15 });
  s.addText("“The coverage just described what happened.”", {
    x: 7.2, y: 1.85, w: 5.15, h: 0.55, margin: 0,
    fontFace: HEAD, fontSize: 21, bold: true, italic: true, color: SLATE, valign: "middle",
  });
  s.addText("Critics said the problems were real, the recall was real, and reporting on real events is not bias — it is the job.", {
    x: 7.2, y: 2.55, w: 5.15, h: 1.6, margin: 0,
    fontFace: BODY, fontSize: 14, color: BODYTXT, valign: "top", lineSpacingMultiple: 1.18,
  });

  card(s, { x: 0.65, y: 5.0, w: 12.05, h: 1.5, fill: INK });
  s.addText(
    [
      { text: "Both sides were arguing about the same six years of local news. Nobody had read all of it.", options: { bold: true, fontSize: 17, color: WHITE, breakLine: true } },
      { text: "So that is what we did — 12,827 articles about five Bay Area district attorneys.", options: { fontSize: 13.5, color: LIGHTTXT } },
    ],
    { x: 1.05, y: 5.0, w: 11.3, h: 1.5, margin: 0, fontFace: BODY, valign: "middle", lineSpacingMultiple: 1.25 }
  );
  s.addNotes("0:40-2:00. Let the two quotes sit for a beat. The point is that this was an empirical disagreement that nobody had actually tested, because testing it means reading six years of local news.");
}

// ═══════════════════════════════════════════════════════ 3. WHY YOU CARE
{
  const s = lightSlide();
  title(s, "Why this matters if you practise, not just if you publish", { size: 30 });

  const rows = [
    ["1", "Coverage is part of the environment you litigate in",
      "Jury pools, DA elections, and the legislature's appetite for reform all move with how cases get told."],
    ["2", "Prosecutors are nearly invisible in it",
      "In this corpus, 82 out of 100 crime articles mention the police. 15 mention the district attorney. So the little coverage they get does a lot of work."],
    ["3", "And now it can be checked",
      "Six years of local reporting can be sorted in an afternoon. That changes what you can put in a memo, a brief, or a motion."],
  ];
  let y = 1.55;
  rows.forEach(([n, h, b]) => {
    badge(s, 0.68, y + 0.06, n);
    s.addText(h, {
      x: 1.3, y, w: 5.6, h: 0.6, margin: 0,
      fontFace: BODY, fontSize: 16.5, bold: true, color: SLATE, valign: "top", lineSpacingMultiple: 1.05,
    });
    s.addText(b, {
      x: 1.3, y: y + 0.64, w: 5.6, h: 0.95, margin: 0,
      fontFace: BODY, fontSize: 13, color: BODYTXT, valign: "top", lineSpacingMultiple: 1.12,
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
    fontFace: BODY, fontSize: 13, color: BODYTXT, valign: "middle",
  });
  s.addText("15%", {
    x: 7.7, y: 3.75, w: 4.6, h: 1.0, margin: 0,
    fontFace: HEAD, fontSize: 66, bold: true, color: RED, valign: "middle",
  });
  s.addText("mention the district attorney", {
    x: 7.7, y: 4.73, w: 4.6, h: 0.32, margin: 0,
    fontFace: BODY, fontSize: 13, color: BODYTXT, valign: "middle",
  });
  s.addText("The most powerful actor in the system is close to absent from the reporting about it.", {
    x: 7.7, y: 5.15, w: 4.6, h: 0.65, margin: 0,
    fontFace: BODY, fontSize: 11.5, italic: true, color: MUTED, valign: "top", lineSpacingMultiple: 1.1,
  });
  src(s, "Corpus: 12,827 prosecutor-attributed Bay Area articles, 2019-2024.");
  s.addNotes("2:00-3:15. The 82/15 split is the number people remember. It reframes the whole question: this is not a media that is picking on prosecutors, it is a media that barely covers them at all.");
}

// ══════════════════════════════════════════════════════════ 4. WHAT WE DID
{
  const s = lightSlide();
  title(s, "What we actually did");

  const funnel = [
    ["136,313", "articles collected", "Every Bay Area news story touching crime or justice, Jan 2019 - Dec 2024, from 21 outlets"],
    ["12,827", "actually about a DA", "The ones that name a specific district attorney often enough to be about them"],
    ["4 + 1", "ways of reading them", "Four automated readings of every article, plus a person hand-checking samples"],
  ];
  let x = 0.65;
  funnel.forEach(([big, lab, note], i) => {
    card(s, { x, y: 1.45, w: 3.75, h: 2.05 });
    s.addText(big, {
      x: x + 0.3, y: 1.6, w: 3.15, h: 0.72, margin: 0,
      fontFace: HEAD, fontSize: 36, bold: true, color: i === 2 ? RED : SLATE, valign: "middle",
    });
    s.addText(lab, {
      x: x + 0.3, y: 2.32, w: 3.15, h: 0.28, margin: 0,
      fontFace: BODY, fontSize: 13, bold: true, color: SLATE, valign: "middle",
    });
    s.addText(note, {
      x: x + 0.3, y: 2.62, w: 3.15, h: 0.78, margin: 0,
      fontFace: BODY, fontSize: 10.5, color: MUTED, valign: "top", lineSpacingMultiple: 1.08,
    });
    if (i < 2) {
      s.addText("→", {
        x: x + 3.78, y: 1.45, w: 0.5, h: 2.05, margin: 0,
        fontFace: BODY, fontSize: 26, bold: true, color: DIM, align: "center", valign: "middle",
      });
    }
    x += 4.28;
  });

  s.addText("The five prosecutors", {
    x: 0.65, y: 3.7, w: 7.3, h: 0.35, margin: 0,
    fontFace: BODY, fontSize: 14, bold: true, color: SLATE, valign: "middle",
  });
  const rows = [
    [
      { text: "Prosecutor", options: { bold: true, color: WHITE, fill: { color: SLATE } } },
      { text: "County", options: { bold: true, color: WHITE, fill: { color: SLATE } } },
      { text: "Type", options: { bold: true, color: WHITE, fill: { color: SLATE } } },
      { text: "Articles", options: { bold: true, color: WHITE, fill: { color: SLATE }, align: "right" } },
    ],
    ["Chesa Boudin", "San Francisco", "Reform", { text: "5,783", options: { align: "right" } }],
    ["Brooke Jenkins", "San Francisco", "Traditional", { text: "3,097", options: { align: "right" } }],
    ["Nancy O'Malley", "Alameda", "Traditional", { text: "1,497", options: { align: "right" } }],
    ["Pamela Price", "Alameda", "Reform", { text: "802", options: { align: "right" } }],
    ["Steve Wagstaffe", "San Mateo", "Traditional", { text: "1,648", options: { align: "right" } }],
  ];
  s.addTable(rows, {
    x: 0.65, y: 4.1, w: 7.3, colW: [2.4, 1.85, 1.75, 1.3],
    rowH: 0.33, fontFace: BODY, fontSize: 12, color: BODYTXT,
    border: { type: "solid", color: "E3E6EC", pt: 1 }, fill: { color: WHITE },
    valign: "middle", margin: [0.04, 0.1, 0.04, 0.1],
  });

  card(s, { x: 8.35, y: 3.7, w: 4.35, h: 2.5, fill: REDT });
  s.addText("Two counties gave us a natural comparison", {
    x: 8.7, y: 3.95, w: 3.65, h: 0.6, margin: 0,
    fontFace: BODY, fontSize: 15, bold: true, color: "6D1119", valign: "top", lineSpacingMultiple: 1.05,
  });
  s.addText("San Francisco and Alameda each swapped a reform DA for a traditional one, or the reverse, inside the same six years. Same city, same reporters, same paper — different prosecutor.", {
    x: 8.7, y: 4.65, w: 3.65, h: 1.4, margin: 0,
    fontFace: BODY, fontSize: 12, color: "6D1119", valign: "top", lineSpacingMultiple: 1.12,
  });
  s.addNotes("3:15-4:30. Keep this light. The design point worth making out loud is the county pairing: we are not comparing the Chronicle to Fox News, we are comparing the Chronicle to itself, before and after a change of DA.");
}

// ══════════════════════════════════════════════ 5. IT DEPENDS WHAT YOU COUNT
{
  const s = lightSlide();
  title(s, "The first finding is about the question, not the answer");
  s.addText("We asked the same 12,827 articles three different versions of \"was this coverage hostile?\" — and got three different answers.", {
    x: 0.65, y: 1.1, w: 12.05, h: 0.4, margin: 0,
    fontFace: BODY, fontSize: 14, color: BODYTXT, valign: "middle",
  });

  const rows = [
    ["Does the article sound negative?",
      "About the same", DIM, WHITE,
      "Measure the mood of the writing and reform and traditional prosecutors come out nearly identical."],
    ["Is the article arguing against the DA?",
      "Clearly more", RED, WHITE,
      "Look at whether the piece takes a position, and coverage of reform prosecutors leans against them."],
    ["Do critical storylines attach to the DA by name?",
      "Much more", RED, WHITE,
      "Look for “soft on crime” or “recall” sitting next to the prosecutor's name — the widest gap of the three."],
  ];
  let y = 1.75;
  rows.forEach(([q, verdict, vfill, vcolor, gloss]) => {
    card(s, { x: 0.65, y, w: 12.05, h: 1.25 });
    s.addText(q, {
      x: 1.05, y: y + 0.16, w: 5.5, h: 0.42, margin: 0,
      fontFace: BODY, fontSize: 16, bold: true, color: SLATE, valign: "middle",
    });
    s.addText(gloss, {
      x: 1.05, y: y + 0.6, w: 8.4, h: 0.5, margin: 0,
      fontFace: BODY, fontSize: 12.5, color: BODYTXT, valign: "top", lineSpacingMultiple: 1.1,
    });
    chip(s, { x: 9.95, y: y + 0.37, w: 2.4, h: 0.52, fill: vfill, color: vcolor, text: verdict, size: 13 });
    y += 1.42;
  });

  s.addText("Whoever chooses the measure has already chosen much of the answer. That is the part to be suspicious of — in our work and in anyone else's.", {
    x: 0.65, y: 6.15, w: 12.05, h: 0.5, margin: 0,
    fontFace: BODY, fontSize: 14.5, bold: true, color: RED, valign: "middle",
  });
  s.addNotes("4:30-6:00. The most important slide in the deck. Say plainly: if you had only run the first row you would have published 'no bias found.' If you had only run the third you would have published 'overwhelming bias.' Both would have been defensible and both would have been incomplete.");
}

// ═══════════════════════════════════════════════════ 6. A DIFFERENT GENRE
{
  const s = lightSlide();
  title(s, "Not meaner coverage. A different kind of story.");

  card(s, { x: 0.65, y: 1.45, w: 5.85, h: 3.55 });
  s.addText("When the DA was a reformer,", {
    x: 1.0, y: 1.72, w: 5.15, h: 0.35, margin: 0,
    fontFace: BODY, fontSize: 13, bold: true, charSpacing: 0.6, color: RED, valign: "middle",
  });
  s.addText("the article was usually about the DA", {
    x: 1.0, y: 2.08, w: 5.15, h: 0.5, margin: 0,
    fontFace: HEAD, fontSize: 20, bold: true, color: SLATE, valign: "middle",
  });
  s.addText(
    [
      { text: "whether their approach was working", options: { bullet: true, breakLine: true } },
      { text: "whether the office was in trouble", options: { bullet: true, breakLine: true } },
      { text: "the campaign to remove them", options: { bullet: true, breakLine: true } },
      { text: "what their critics said about them", options: { bullet: true } },
    ],
    { x: 1.15, y: 2.75, w: 5.0, h: 1.7, margin: 0, fontFace: BODY, fontSize: 14, color: BODYTXT, paraSpaceAfter: 7 }
  );
  s.addText("A controversy to be adjudicated.", {
    x: 1.0, y: 4.5, w: 5.15, h: 0.4, margin: 0,
    fontFace: BODY, fontSize: 13.5, italic: true, color: MUTED, valign: "middle",
  });

  card(s, { x: 6.85, y: 1.45, w: 5.85, h: 3.55 });
  s.addText("When the DA was traditional,", {
    x: 7.2, y: 1.72, w: 5.15, h: 0.35, margin: 0,
    fontFace: BODY, fontSize: 13, bold: true, charSpacing: 0.6, color: SLATE, valign: "middle",
  });
  s.addText("the article was usually about a case", {
    x: 7.2, y: 2.08, w: 5.15, h: 0.5, margin: 0,
    fontFace: HEAD, fontSize: 20, bold: true, color: SLATE, valign: "middle",
  });
  s.addText(
    [
      { text: "a specific crime and a specific victim", options: { bullet: true, breakLine: true } },
      { text: "an arrest, a charge, a sentence", options: { bullet: true, breakLine: true } },
      { text: "a task force or a new initiative", options: { bullet: true, breakLine: true } },
      { text: "the office as a source, not a subject", options: { bullet: true } },
    ],
    { x: 7.35, y: 2.75, w: 5.0, h: 1.7, margin: 0, fontFace: BODY, fontSize: 14, color: BODYTXT, paraSpaceAfter: 7 }
  );
  s.addText("An official doing a job.", {
    x: 7.2, y: 4.5, w: 5.15, h: 0.4, margin: 0,
    fontFace: BODY, fontSize: 13.5, italic: true, color: MUTED, valign: "middle",
  });

  card(s, { x: 0.65, y: 5.35, w: 12.05, h: 1.15, fill: REDT });
  s.addText(
    [
      { text: "Same beat, same papers, different genre. ", options: { bold: true } },
      { text: "That difference does not show up if you only measure whether the words were harsh." },
    ],
    { x: 1.05, y: 5.35, w: 11.3, h: 1.15, margin: 0, fontFace: BODY, fontSize: 14.5, color: "6D1119", valign: "middle" }
  );
  s.addNotes("6:00-7:15. This is the substantive finding, and the one that translates. Reform prosecutors were treated as an argument; traditional prosecutors were treated as furniture. Neither is name-calling, and the second is arguably the bigger advantage.");
}

// ══════════════════════════════════════════════ 7. STORYLINES WITH A NAME
{
  const s = lightSlide();
  title(s, "Certain storylines came with a name attached");
  s.addImage({ path: IMG("themes.png"), x: 0.55, y: 1.25, w: 7.7, h: 3.47 });
  s.addText("Share of each prosecutor's coverage in which the storyline appears next to their name.", {
    x: 0.55, y: 4.78, w: 7.7, h: 0.3, margin: 0,
    fontFace: BODY, fontSize: 10.5, italic: true, color: MUTED, valign: "middle",
  });

  s.addText("What the gaps look like", {
    x: 8.5, y: 1.25, w: 4.2, h: 0.4, margin: 0,
    fontFace: BODY, fontSize: 16.5, bold: true, color: SLATE, valign: "middle",
  });
  s.addText(
    [
      { text: "“Recall”", options: { bold: true, breakLine: false } },
      { text: " — about 3 to 4 times more often around reform DAs, and the single widest gap.", options: { breakLine: true, paraSpaceAfter: 9 } },
      { text: "“Soft on crime”, “crime is rising”, “public safety failure”", options: { bold: true, breakLine: false } },
      { text: " — each roughly two to four times more often.", options: { breakLine: true, paraSpaceAfter: 9 } },
      { text: "“Releasing criminals”", options: { bold: true, breakLine: false } },
      { text: " — slightly more common around the traditional DAs. This one runs the other way.", options: {} },
    ],
    { x: 8.5, y: 1.75, w: 4.2, h: 2.35, margin: 0, fontFace: BODY, fontSize: 12.5, color: BODYTXT, valign: "top", lineSpacingMultiple: 1.1 }
  );
  card(s, { x: 8.5, y: 3.6, w: 4.2, h: 1.5, fill: REDT });
  s.addText(
    [
      { text: "This is the closest thing we have to what people mean by “the press was against them”", options: { bold: true, breakLine: true } },
      { text: "— not harsh words, but a critical narrative pinned to a specific person.", options: {} },
    ],
    { x: 8.82, y: 3.6, w: 3.56, h: 1.5, margin: 0, fontFace: BODY, fontSize: 11.5, color: "6D1119", valign: "middle", lineSpacingMultiple: 1.12 }
  );

  card(s, { x: 0.65, y: 5.3, w: 12.05, h: 1.25, fill: INK });
  s.addText(
    [
      { text: "Pay attention to the bar that goes the wrong way.", options: { bold: true, fontSize: 16, color: WHITE, breakLine: true } },
      { text: "A method that only ever finds what you expected is a method you should not believe.", options: { fontSize: 13, color: LIGHTTXT } },
    ],
    { x: 1.05, y: 5.3, w: 11.3, h: 1.25, margin: 0, fontFace: BODY, valign: "middle", lineSpacingMultiple: 1.2 }
  );
  s.addNotes("7:15-8:30. Walk to the top bar first — recall. Then deliberately point at 'releasing criminals' running the other way. A stricter second method puts the recall storyline at roughly 18% of reform-DA coverage versus 4% of traditional-DA coverage; same direction, larger gap.");
}

// ══════════════════════════════════════════════════ 8. WHAT IT LOOKS LIKE
{
  const s = lightSlide();
  title(s, "What that looks like in print");

  const items = [
    ["“Boudin might be in trouble if poll holds”", "San Francisco Chronicle · March 2022",
      "A poll story, commissioned by the recall campaign. Crime, dismissals and the recall all in one piece, all attached to him."],
    ["“'Boudin Blunders': SF DA's downfall leading up to recall”", "KRON4 · June 2022",
      "The highest score in the whole corpus. Five critical storylines, each tied to his name — “prosecutors who viewed him as soft on crime.”"],
    ["“Newsom, SF leaders to form joint task force to battle fentanyl crisis”", "NBC Bay Area · October 2023",
      "Also crime coverage, also names the DA's office — as one participant among several. No storyline attaches to the prosecutor at all."],
  ];
  let x = 0.65;
  items.forEach(([hl, meta, note], i) => {
    card(s, { x, y: 1.45, w: 3.9, h: 3.75, fill: i === 2 ? CARD : REDT });
    const txtc = i === 2 ? SLATE : "6D1119";
    s.addText(hl, {
      x: x + 0.32, y: 1.7, w: 3.26, h: 1.1, margin: 0,
      fontFace: HEAD, fontSize: 16.5, bold: true, color: txtc, valign: "top", lineSpacingMultiple: 1.08,
    });
    s.addText(meta, {
      x: x + 0.32, y: 2.88, w: 3.26, h: 0.3, margin: 0,
      fontFace: BODY, fontSize: 11, bold: true, color: i === 2 ? MUTED : "9C4A50", valign: "middle",
    });
    s.addText(note, {
      x: x + 0.32, y: 3.3, w: 3.26, h: 1.6, margin: 0,
      fontFace: BODY, fontSize: 12, color: i === 2 ? BODYTXT : txtc, valign: "top", lineSpacingMultiple: 1.14,
    });
    x += 4.13;
  });

  s.addText("The first two are about a person. The third is about a problem. All three are crime reporting in the same market in the same years.", {
    x: 0.65, y: 5.5, w: 12.05, h: 0.5, margin: 0,
    fontFace: BODY, fontSize: 14.5, bold: true, color: SLATE, valign: "middle",
  });
  src(s, "Real articles from the corpus. Full text and scores in Appendix C of the paper.");
  s.addNotes("8:30-9:45. Read the first two headlines out loud — they do the work. Then contrast with the fentanyl task force piece: the DA's office is in it, but as a participant, not a defendant.");
}

// ══════════════════════════════════════════════════ 9. WHERE IT WENT WRONG
{
  const s = lightSlide();
  title(s, "Two articles that should keep you honest");

  card(s, { x: 0.65, y: 1.45, w: 5.85, h: 3.5 });
  badge(s, 1.0, 1.72, "1");
  s.addText("“Don't blame Alameda DA Price for crime”", {
    x: 1.0, y: 2.28, w: 5.15, h: 0.8, margin: 0,
    fontFace: HEAD, fontSize: 18, bold: true, color: SLATE, valign: "top", lineSpacingMultiple: 1.06,
  });
  s.addText("San Francisco Chronicle op-ed · August 2023", {
    x: 1.0, y: 3.12, w: 5.15, h: 0.3, margin: 0,
    fontFace: BODY, fontSize: 11, bold: true, color: MUTED, valign: "middle",
  });
  s.addText("Our most hostile score in the entire corpus. It is a defence of her, written by a city council member. The words around her name were about crime and failure; the argument was the opposite.", {
    x: 1.0, y: 3.5, w: 5.15, h: 1.35, margin: 0,
    fontFace: BODY, fontSize: 13, color: BODYTXT, valign: "top", lineSpacingMultiple: 1.15,
  });

  card(s, { x: 6.85, y: 1.45, w: 5.85, h: 3.5 });
  badge(s, 7.2, 1.72, "2");
  s.addText("“Suspected mom of newborn left in Wisconsin field arrested”", {
    x: 7.2, y: 2.28, w: 5.15, h: 0.8, margin: 0,
    fontFace: HEAD, fontSize: 18, bold: true, color: SLATE, valign: "top", lineSpacingMultiple: 1.06,
  });
  s.addText("sfgate.com · March 2023", {
    x: 7.2, y: 3.12, w: 5.15, h: 0.3, margin: 0,
    fontFace: BODY, fontSize: 11, bold: true, color: MUTED, valign: "middle",
  });
  s.addText("Filed in our data under a San Francisco district attorney. It is about Wisconsin. It got in because it contains the phrase “district attorney's office.”", {
    x: 7.2, y: 3.5, w: 5.15, h: 1.35, margin: 0,
    fontFace: BODY, fontSize: 13, color: BODYTXT, valign: "top", lineSpacingMultiple: 1.15,
  });

  card(s, { x: 0.65, y: 5.3, w: 12.05, h: 1.3, fill: INK });
  s.addText(
    [
      { text: "Across thousands of articles these mistakes cancel out. In any single article they do not.", options: { bold: true, fontSize: 16.5, color: WHITE, breakLine: true } },
      { text: "That one sentence is the whole rule for using this kind of evidence.", options: { fontSize: 13, color: LIGHTTXT } },
    ],
    { x: 1.05, y: 5.3, w: 11.3, h: 1.3, margin: 0, fontFace: BODY, valign: "middle", lineSpacingMultiple: 1.2 }
  );
  s.addNotes("9:45-11:00. The two best slides in the deck are this one and slide 5. The Price op-ed is the killer example: the machine scored a defence of her as the most hostile article in six years of news. Say that our hand-check found the automated reading of any individual article was no better than a coin flip, and that we published that.");
}

// ═══════════════════════════════════════════════════ 10. WHAT TO ASK
{
  const s = lightSlide();
  title(s, "Four questions for anyone who hands you a media study");

  const items = [
    ["What exactly did you count?",
      "Tone, argument, and storyline gave three different answers on the same articles. The choice of measure is most of the finding."],
    ["Did a human check it?",
      "Ask for the sample and the error rate. If nobody hand-read a few hundred articles, there is no finding — there is an output."],
    ["What is not in your sample?",
      "Broadcast, Spanish-language and neighbourhood outlets fall out of most databases. Ask what the sample cannot see."],
    ["Does anything run against your story?",
      "One of our storylines pointed the other way. A study in which everything confirms is a study that only looked one place."],
  ];
  const pos = [[0.65, 1.4], [6.9, 1.4], [0.65, 3.4], [6.9, 3.4]];
  items.forEach(([h, b], i) => {
    const [cx, cy] = pos[i];
    card(s, { x: cx, y: cy, w: 5.8, h: 1.75 });
    badge(s, cx + 0.3, cy + 0.26, String(i + 1));
    s.addText(h, {
      x: cx + 0.92, y: cy + 0.2, w: 4.55, h: 0.38, margin: 0,
      fontFace: BODY, fontSize: 16, bold: true, color: RED, valign: "middle",
    });
    s.addText(b, {
      x: cx + 0.3, y: cy + 0.7, w: 5.2, h: 0.95, margin: 0,
      fontFace: BODY, fontSize: 12, color: BODYTXT, valign: "top", lineSpacingMultiple: 1.14,
    });
  });

  card(s, { x: 0.65, y: 5.45, w: 12.05, h: 1.15, fill: REDT });
  s.addText(
    [
      { text: "These are the questions I would want asked of my own work. ", options: { bold: true } },
      { text: "A study that can answer all four is usable. One that cannot is a press release." },
    ],
    { x: 1.05, y: 5.45, w: 11.3, h: 1.15, margin: 0, fontFace: BODY, fontSize: 14.5, color: "6D1119", valign: "middle" }
  );
  s.addNotes("11:00-11:45. Offer these as a practical checklist they can use on anyone's study, including mine. Question two is the one that separates real work from output.");
}

// ═════════════════════════════════════════ 11. THE UNANSWERED QUESTION
{
  const s = darkSlide();
  kicker(s, "WHAT WE STILL CAN'T ANSWER", { y: 1.35, color: "E0757F" });
  s.addText("We can tell you the coverage was critical.\nWe can't tell you when it became the story.", {
    x: 0.65, y: 1.8, w: 9.2, h: 1.85, margin: 0,
    fontFace: HEAD, fontSize: 34, bold: true, color: WHITE, valign: "middle", lineSpacingMultiple: 1.12,
  });
  s.addText("Somewhere between January and June 2022, coverage of one district attorney went from routine to inescapable. That tipping point is what actually matters — for showing cause and effect, and for anyone deciding when to respond.", {
    x: 0.65, y: 3.95, w: 8.8, h: 1.2, margin: 0,
    fontFace: BODY, fontSize: 16, color: LIGHTTXT, valign: "top", lineSpacingMultiple: 1.2,
  });
  s.addText("Our data was monthly and stopped at the county line. It could never see that.", {
    x: 0.65, y: 5.3, w: 8.8, h: 0.4, margin: 0,
    fontFace: BODY, fontSize: 14, italic: true, color: DIM, valign: "middle",
  });
  s.addText("There is a free tool built for exactly this.", {
    x: 0.65, y: 6.0, w: 8.8, h: 0.5, margin: 0,
    fontFace: BODY, fontSize: 17, bold: true, color: "E0757F", valign: "middle",
  });
  s.addNotes("11:45-12:15. Slow down here. This is the pivot from findings to potential. The honest limitation of my study is the setup for the last three slides.");
}

// ══════════════════════════════════════════════════════ 12. GDELT
{
  const s = lightSlide();
  title(s, "GDELT, in one slide");
  s.addText("A free public project that watches the world's news — thousands of outlets in 65 languages — and records, every fifteen minutes, what is being covered, where, and in what tone. No fee, no licence, no login.", {
    x: 0.65, y: 1.08, w: 12.05, h: 0.65, margin: 0,
    fontFace: BODY, fontSize: 14.5, color: BODYTXT, valign: "top", lineSpacingMultiple: 1.15,
  });

  const cards = [
    ["How much is being said", "Coverage of any topic, person or place, counted by day or by hour, going back years."],
    ["How it is changing", "Whether attention and tone are rising or falling — so you can see a story build or break."],
    ["Where it is spreading", "Which outlets, which countries, which languages. Including US local television back to 2009, searchable by what was said on air."],
  ];
  let x = 0.65;
  cards.forEach(([h, b]) => {
    card(s, { x, y: 1.9, w: 3.9, h: 1.9 });
    s.addText(h, {
      x: x + 0.32, y: 2.1, w: 3.26, h: 0.35, margin: 0,
      fontFace: HEAD, fontSize: 17, bold: true, color: SLATE, valign: "middle",
    });
    s.addText(b, {
      x: x + 0.32, y: 2.5, w: 3.26, h: 1.15, margin: 0,
      fontFace: BODY, fontSize: 12.5, color: BODYTXT, valign: "top", lineSpacingMultiple: 1.14,
    });
    x += 4.13;
  });

  card(s, { x: 0.65, y: 4.1, w: 12.05, h: 1.55, fill: REDT });
  badge(s, 1.05, 4.5, "!");
  s.addText(
    [
      { text: "The one thing it will not do is hand you the article.", options: { bold: true, fontSize: 16, breakLine: true } },
      { text: "GDELT tells you a story exists, how loud it is, and where to find it. Reading the words is still your job — through LexisNexis, the outlet, or the documents themselves.", options: { fontSize: 12.5 } },
    ],
    { x: 1.7, y: 4.1, w: 10.65, h: 1.55, margin: 0, fontFace: BODY, color: "6D1119", valign: "middle", lineSpacingMultiple: 1.15 }
  );

  s.addText("Easiest way in: type a name into television.gdeltproject.org and look at the chart. No code, no account.", {
    x: 0.65, y: 5.9, w: 12.05, h: 0.45, margin: 0,
    fontFace: BODY, fontSize: 13.5, bold: true, color: SLATE, valign: "middle",
  });
  s.addNotes("12:15-13:00. Deliberately non-technical. If someone asks how you get the data out: a plain web address returns a spreadsheet, and there is a full SQL version for big jobs. Do not go further than that unless asked. Worth mentioning that it rate-limits hard, so a real pull needs a script that waits politely.");
}

// ═══════════════════════════════════════════ 12b. THE ANSWER, MEASURED
{
  const s = lightSlide();
  title(s, "So I ran it");
  s.addText("Two queries and one article pull, on a free public index. About twenty minutes of work.", {
    x: 0.65, y: 1.06, w: 12.05, h: 0.35, margin: 0,
    fontFace: BODY, fontSize: 13.5, color: BODYTXT, valign: "middle",
  });

  s.addImage({ path: IMG("salience.png"), x: 0.6, y: 1.45, w: 8.55, h: 4.91 });

  const finds = [
    ["There was no ramp.", "March and April sat at the 2021 baseline. The story did not build toward the vote."],
    ["It peaked the day after.", "8 June: 500 articles, 0.58% of all US coverage that day."],
    ["It escaped the market.", "In election week Bay Area outlets ran 12x their usual volume. Everyone else ran 76x."],
    ["February fooled me twice.", "That bump is the school board recall, not his. And the police breaking with the DA on 2 Feb did nothing."],
  ];
  let fy = 1.5;
  finds.forEach(([h, b]) => {
    card(s, { x: 9.4, y: fy, w: 3.3, h: 1.15 });
    s.addText(
      [
        { text: h + " ", options: { bold: true, color: RED } },
        { text: b, options: { color: BODYTXT } },
      ],
      { x: 9.62, y: fy, w: 2.86, h: 1.15, margin: 0, fontFace: BODY, fontSize: 10.5, valign: "middle", lineSpacingMultiple: 1.1 }
    );
    fy += 1.26;
  });

  s.addText(
    [
      { text: "Caveat that matters: ", options: { bold: true } },
      { text: "this is US-wide coverage. A story can be deafening in San Francisco and invisible here — which is exactly why you pair it with a local corpus. And nobody yet knows what the December 2021 burst was." },
    ],
    { x: 0.65, y: 6.52, w: 12.05, h: 0.45, margin: 0, fontFace: BODY, fontSize: 12, italic: true, color: MUTED, valign: "middle" }
  );
  s.addNotes(
    "13:00-14:00. The payoff slide. Four things to say out loud: (1) I expected a slow build and there isn't one — the flat line through March and April is the finding; (2) the peak is the day AFTER the vote, which cuts against the simple 'media drove the recall' story at the national level; (3) the February MOU fight, which an earlier draft of this deck named as the obvious candidate, produced nothing nationally; (4) the February bump is the SCHOOL BOARD recall, not his — the query asked for 'Boudin' within twenty words of 'recall', and coverage of that vote kept asking whether he was next. 11% of that week's articles name the school board in the headline alone, against 1% across the rest of the corpus. That is slide 5's lesson happening live, to me, on the tool I am recommending. If asked about the December 2021 spike: I don't know what it was, and after the February lesson I would check before citing it."
  );
}

// ═══════════════════════════════════════════════════════ 13. SIX IDEAS
{
  const s = lightSlide();
  title(s, "Six more things you could ask it");

  const items = [
    ["Was the local curve the same?",
      "Re-run the last slide on Bay Area outlets only. If local coverage ramped when national did not, the causal story changes entirely."],
    ["What was that December burst?",
      "About 230 articles over two days, and none of us knows why. Pull them and read a sample — after the school-board lesson, assume nothing until you have."],
    ["How saturated is this county?",
      "For a venue motion: coverage here against a neighbouring county, week by week, with dates and links you can archive and cite."],
    ["Did the narrative come before the policy?",
      "Line the coverage curve up against when a charging policy, a bill, or a budget actually changed. Which one moved first?"],
    ["Is the story tracking the facts?",
      "Put coverage of “rising crime” next to the agency's own reported numbers and show the gap — or show there isn't one."],
    ["What is being said on the air?",
      "Local TV captions back to 2009. A lot of crime narrative lives on the evening news and is missing from every text database."],
  ];
  const pos = [[0.65, 1.35], [4.78, 1.35], [8.91, 1.35], [0.65, 3.35], [4.78, 3.35], [8.91, 3.35]];
  items.forEach(([h, b], i) => {
    const [cx, cy] = pos[i];
    card(s, { x: cx, y: cy, w: 3.77, h: 1.8, fill: i < 2 ? REDT : CARD });
    const txtc = i < 2 ? "6D1119" : SLATE;
    badge(s, cx + 0.28, cy + 0.24, String(i + 1), { d: 0.36, size: 11 });
    s.addText(h, {
      x: cx + 0.74, y: cy + 0.16, w: 2.8, h: 0.55, margin: 0,
      fontFace: BODY, fontSize: 13.5, bold: true, color: txtc, valign: "middle", lineSpacingMultiple: 1.04,
    });
    s.addText(b, {
      x: cx + 0.28, y: cy + 0.78, w: 3.25, h: 1.05, margin: 0,
      fontFace: BODY, fontSize: 10.5, color: i < 2 ? txtc : BODYTXT, valign: "top", lineSpacingMultiple: 1.12,
    });
  });

  s.addText("The first two follow straight out of the last slide, and each is an afternoon's work.", {
    x: 0.65, y: 5.45, w: 12.05, h: 0.45, margin: 0,
    fontFace: BODY, fontSize: 14.5, bold: true, color: RED, valign: "middle",
  });
  s.addText("Salience and spread are timing questions, and timing is what turns a description of the coverage into an argument about what the coverage did.", {
    x: 0.65, y: 5.9, w: 12.05, h: 0.45, margin: 0,
    fontFace: BODY, fontSize: 13, italic: true, color: MUTED, valign: "middle",
  });
  s.addNotes("14:30-15:00. Move fast — the previous slide already made the case. Point at 2 as the obvious next run, and let the venue idea (3) be the hook for litigators. Then invite them to pick one.");
}

// ══════════════════════════════════════════════════════ 14. TAKEAWAYS
{
  const s = darkSlide();
  kicker(s, "TAKEAWAYS", { y: 0.75, color: "E0757F" });

  const items = [
    ["1", "The coverage wasn't harsher. It was a different kind of story.",
      "Reform prosecutors were written about as a controversy. Traditional prosecutors were written about as officials handling cases."],
    ["2", "Reading at scale finds patterns, not verdicts.",
      "Thousands of articles, yes. Any single article, no — the machine called an op-ed defending Pamela Price the most hostile piece in six years."],
    ["3", "Timing is measurable — and it surprised me.",
      "National attention did not build toward the recall; it peaked the day after the vote. Two free queries, and the question changes shape."],
  ];
  let y = 1.35;
  items.forEach(([n, h, b]) => {
    badge(s, 0.68, y + 0.08, n, { d: 0.46, size: 14 });
    s.addText(h, {
      x: 1.4, y, w: 10.4, h: 0.45, margin: 0,
      fontFace: HEAD, fontSize: 20, bold: true, color: WHITE, valign: "middle",
    });
    s.addText(b, {
      x: 1.4, y: y + 0.48, w: 9.9, h: 0.75, margin: 0,
      fontFace: BODY, fontSize: 13.5, color: LIGHTTXT, valign: "top", lineSpacingMultiple: 1.14,
    });
    y += 1.45;
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: 0.65, y: 5.7, w: 12.05, h: 1.2, rectRadius: 0.06,
    fill: { color: INK2 }, line: { type: "none" },
  });
  s.addText("BRING ME A QUESTION ABOUT COVERAGE AND WE CAN HAVE A FIRST ANSWER THE SAME DAY", {
    x: 1.0, y: 5.85, w: 11.4, h: 0.3, margin: 0,
    fontFace: BODY, fontSize: 10.5, bold: true, charSpacing: 1.6, color: "E0757F", valign: "middle",
  });
  s.addText(
    [
      { text: "television.gdeltproject.org", options: { color: "8FD8B0" } },
      { text: "          gdeltproject.org", options: { color: "8FD8B0" } },
    ],
    { x: 1.0, y: 6.2, w: 11.4, h: 0.5, margin: 0, fontFace: MONO, fontSize: 13, valign: "middle" }
  );
  s.addNotes("14:30-15:00. Close on the ask, not the tool. The three links are for the deck, not the talk.");
}

const out = path.join(__dirname, "media_research_overview.pptx");
pres.writeFile({ fileName: out }).then(() => console.log("wrote " + out));
