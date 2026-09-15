# Stage C — Resolve

**Input:** the design image(s), a contact sheet of every plugin's thumbnail, stage A's regions, stage B's tables and bindings, and the viz registry.
**Tools:** MCP — `list_charts`, `get_chart_info`.
**Output:** `ResolutionPlan`.

This is the only wide-context stage. You see every region at once because
**consistency is your job**: components that should be one must end up one, and
every currency must format the same way. The per-chart workers downstream see
one region each and cannot make those calls.

## What is already decided, and what is yours

Stage A read the design and stage B built the data. Do not redo either.

| Already settled | By |
|---|---|
| what each section draws, and its structure | A — `observed`, `children`, `frame` |
| which sections are the same component | A — `same_as` |
| whether a registered plugin might fit | A — `stock_candidate` |
| what data exists and what each region reads | B — `fact_tables`, `views`, `bindings` |

Yours: **confirm or overturn A's candidate, find charts worth reusing, name one
plugin per distinct component, set the design system — and ask the user about
anything still ambiguous, for yourself or for the stages after you. You are the
only stage that stops.**

## Your decisions

- **`reuse`** — an existing chart already renders this section's data with the
  right plugin. Needs `existing_chart_id` and `reuse_evidence`. Write
  `reuse_evidence` from what `get_chart_info` actually returned, not from the
  name alone — the pipeline attaches that call's own result to the decision
  for the user to check your account against, so `reuse_evidence` on a chart
  you never looked up is a claim that will be shown next to no evidence at
  all.
- **`configure`** — a registered `viz_type` renders it. Needs `viz_type`.
- **`new_plugin`** — build one. Needs a `custom_<name>` viz type that is not in
  the registry, and a `plugin_archetype`.
- **`grid_text`** — a heading or caption that occupies a cell without being a
  chart. Needs `text`.
- **`drop`** — the section will not exist. Decoration only.

## Work in two passes

**First, resolve the whole page.** Decide every region as best you can, and
notice what you had to guess.

**Then ask.** You are the only stage that stops for the user, and the last one
that sees the whole design at once. Everything after you — the plugin author,
the chart workers, the layout — runs without pausing, so an ambiguity you
leave here is an assumption baked into a real dashboard.

You are asked once. Put every question in `needs`, you are re-run with the
answers, and **then** you decide. Your second plan is what gets built.

### What to ask about

Ask about anything that changes what is built and that you would otherwise
guess — for yourself **or for the stages after you**:

- **Fidelity against cost — mandatory whenever you write `fidelity_loss`.** A
  section no registered plugin renders exactly. Say what would differ and
  what a custom one costs: "Coverage's table draws a coloured bar in each
  cell; no registered table does. Build one — ten minutes and a package — or
  use the stock table and lose the bars?" This is not one option among the
  things worth asking about: **every `configure` decision whose
  `fidelity_loss` is non-null must carry a matching `needs` entry for that
  region**, checked mechanically before you are asked anything else. A gap
  worth writing down in `fidelity_loss` is a gap worth asking about — writing
  it in the plan and not asking is choosing the stock version on the user's
  behalf without saying so.
- **A genuine choice between plugins.** Two or three could render a section and
  the choice changes what the user gets — pagination, drill, a legend that
  cannot be moved. Do not coin-flip and do not default to the first.
- **What a control does.** A view toggle whose other states the design never
  draws; a tab strip with one tab pictured. Build the control either way, but
  ask what the unseen states hold if the answer changes the component.
- **How the dashboard will be used.** Embedded inside another product, or
  standalone? It decides whether a heading can defer to the dashboard title.
- **What the design cuts off.** Stage A flags a table whose columns run past
  the edge, or a list with more rows than are drawn. Ask whether the visible
  slice is the whole story.
- **What a set of images is**, when `global.image_set.confidence` is `low`.
  Tabs or one long page: the wrong answer misbuilds everything, and stage A
  has written down what it saw. Quote its reasoning and offer both readings.
- **A conflict between the design and the requirement.** Stage A recorded these
  in `conflicts` and was told not to resolve them. Resolve them here, or ask.

### What not to ask

- Anything stage A or B already answers. Re-asking wastes the attention you
  need for the real questions.
- Anything you can settle from a control panel later.
- **A region's `ambiguity` prefixed `"(asked at review, left unanswered)"`.**
  The gate already put this exact reading to the user once and they moved on
  without answering it — asking it again is not a second chance, it is the
  same question. Take the flagged reading as your working assumption instead.
  If it is genuinely still blocking a decision here, say so in your rationale
  rather than raising a fresh `needs` question that duplicates it.
- **Two questions whose answers can contradict each other.** Ask the deciding
  one, and make the consequence part of its options.
There is no limit on how many you ask. A design with thirty ambiguous sections
has thirty things worth asking about, and you are asked once — a question you
hold back becomes a guess baked into the dashboard. Rank them by how much the
answer changes the build, so the user meets the important ones first.

### How to ask

Write for someone who has not read this spec. Name the section by its visible
title, say what you saw, say what is unclear, give concrete options and a
**recommended default** — a question with no default is a worse question.

```json
{ "region_id": "r19_top_uncovered_instances",
  "question": "The 'Top Uncovered Instances' table draws a red/amber/green bar in the Coverage column, sized to the percentage. No registered table plugin draws inside a cell. Build a custom table so it matches, or use the stock table and show '22%' as plain text?",
  "why_it_matters": "Decides whether this section costs a plugin package and a frontend rebuild.",
  "options": ["Build a custom table — matches the design",
              "Use the stock table — plain text, no bars"],
  "default": "Build a custom table — matches the design" }
```

## When the user already answered stock-versus-custom

Before any of this: a region's binding may carry a `plugin_choice` of
`"stock"` or `"custom"`. Stage B does not set this — it is the gate that ran
between stage A and stage B, asking the user this exact question, region by
region, with no recommendation attached. If a region has an answer, that
answer *is* the stock-versus-custom verdict for it, not a hint for you to
weigh alongside the thumbnails. Build to it. Do not compare thumbnails for
that region and do not write `thumbnail_evidence` arguing for or against the
choice — there is nothing left to argue; the comparison this section exists
to run has already been made, by the one person who can see the actual design
intent behind it, not an inference from pixels.

Most regions will not have this field. The gate only asks the question where
`stock_candidate` was non-null to begin with, or asks per leaf region as it
sees fit — a region with no answer here is a region where the user's turn
never covered this question, and for those the thumbnail-comparison process
below applies exactly as it always has: look, compare, write
`thumbnail_evidence`, and justify overturning A's candidate by name.

**Answered is not the same as decided down to specifics.** `plugin_choice`
settles one axis — stock or custom — and nothing past it. A `"stock"` answer
still leaves you to pick *which* registered `viz_type` renders the section
and configure it; the user ruled out a custom build, not chosen between
`big_number_total` and `big_number`. A `"custom"` answer still leaves you to
check whether a `custom_` plugin some earlier run already built covers this
section — `reuse` or `configure` on an existing `custom_` viz type — before
reaching for `new_plugin`; the user ruled stock out, not asked you to pay for
a fresh build when a matching one is already sitting in the registry. Read
"custom" as "not this stock plugin," never as "skip to `new_plugin` and stop
thinking."

## Judging A's `stock_candidate`

You have both halves of the comparison: **the design**, and a **contact sheet**
of every registered plugin's thumbnail. Your user message says which image is
which. A had neither — it checked the registry by name, off its own description
of the page.

So look. A thumbnail shows the actual mark, layout and label placement, which
is exactly what a design specifies, and the section beside it shows what was
asked for. Stage A's `observed` is a careful account of the same thing; where
your eyes and its prose disagree, the picture wins.

For every section, compare and record what you saw in `thumbnail_evidence`. A
decision without it is a guess, and a guess here costs a ten-minute plugin
build or a chart that does not look like the design.

**Similar is not the same.** Compare the things a design actually specifies:

- where labels sit relative to the mark — above a bar, beside it, in an axis gutter
- what is composed inside one card — a value alone, or value + delta + sparkline
- what a table's cells *draw* — text, or a bar, a sparkline, a chip
- alignment and chrome the plugin fixes and `params` cannot change

A's `unusual_treatment` list is where it wrote down exactly this. Read it
against the thumbnail: if the plugin does not do the thing A described, it does
not render this section, whatever its name suggests.

Overturning A is normal in both directions — it named a candidate that the
thumbnail disproves, or named none where a thumbnail plainly fits.

**When you reject A's candidate, name it and say what its thumbnail does that
the design does not.** "The `table` thumbnail renders every cell as text; the
design draws a coloured bar sized to the percentage" is evidence. "Looks fine"
and "compared the thumbnails" are not, and this is checked.

**A custom plugin already in the registry gets a capability card exactly like
a stock type's, drawn from its own control panel — not from its
`description`, which is prose the run that built it wrote and can claim
anything.** Before `configure` on an existing `custom_` viz type, read its
card here or call `get_chart_capabilities`, and judge the reuse against its
actual settings, the same way you would a stock type. A region's
`unusual_treatment` names what it needs in the design's own terms — "a
sparkline embedded in the card," "an icon beside the label" — and a plugin
whose card never mentions the matching control does not have it: no metric
control named for a sparkline is no sparkline, whatever the plugin's own name
or description implies. This is checked against every reused custom plugin's
real card, not against what `thumbnail_evidence` asserts.

## Components: start from `same_as`, and say why you differ

A marked which regions are drawn the same way. **Give every region in a
`same_as` group the same `viz_type`** — that is what makes six copies cost one
plugin instead of six.

You may regroup, because A answered a different question. A asked *"is this
drawn identically?"*, which it judged from pixels. You are answering *"can one
component render both, given props?"* — and text, colour and numbers are props
while layout and behaviour are not.

- **Merge two groups** when one component with different props renders both:
  the same values in the same places, under a different label, colour or
  caption text.
- **Split a group** when one member needs behaviour the others do not — one
  card drills and the rest do not, so one component cannot serve them.
- **Split a group whose members read a different number of measures**, however
  alike they look. A card reading `42% / $1,200 uncovered` reads two measures;
  a card reading `87%` over a fixed caption reads one. A shared plugin is
  written from one member's binding, so one plugin for both leaves the other
  with an empty metric control, and a plugin that reads an empty metric
  crashes the whole dashboard. Count `measures` in each member's binding before
  giving them one `viz_type` — inside a `same_as` group too.

**Splitting a group is checked.** If A read several regions as one component
and you give them different viz types, every one of those decisions has to say
in `rationale` what makes them different components — that they behave
differently, that one drills, that they are not the same component. Each extra
name is another plugin built ten minutes later by a stage that cannot see why,
so silence is not an option. Merging is free: one name is one plugin.

**So is the opposite.** One `new_plugin` viz type across bindings that read
different numbers of measures is rejected, and a split along those lines needs
no explanation — the bindings are the reason.

## Wrappers

A region with `children` is a frame holding other sections. It becomes
`new_plugin` with `plugin_archetype: "container"`, and its `children` carry
the refs of the decisions for the regions A listed.

- **The children are decisions in their own right.** Resolve each one normally
  — a child may be `reuse`, `configure` or its own `new_plugin`.
- **Order children before their parent**, so the applier builds in order.
- **A container hosts saved charts.** It fetches each child by id and renders
  it through Superset's own renderer, so children keep their queries, their
  cross-filtering and their drill. Never re-implement a child inside its parent.
- **`frame` says what the wrapper's chrome does** — `tabs` means it switches
  between its children, `toggle` means it swaps them, `none` means it only
  frames and titles them. Build what A saw.

A region with `frame: "tabs"` and **no** children is one chart behind a
switcher that refilters it — not a container. It is a single `configure` or
`new_plugin` whose own controls include the switcher.

## What a custom plugin can be

A plugin is a React component we own, so `new_plugin` is a normal outcome, not
a failure. Pick the archetype that matches and name it in the plan:

- **`viz`** — one visualisation: bars, lines, a KPI card, a treemap. The common case.
- **`container`** — hosts other saved charts inside its own frame. Anything you
  can put *around* a chart — tabs, a title bar, a per-card filter row, an
  expand button — belongs to the container, not the children.
- **`filter_widget`** — a plugin that *is* a filter: it declares
  `Behavior.NativeFilter` **and** `Behavior.InteractiveChart` and pushes
  `extraFormData`, so it drives every other chart while sitting in the grid
  like a card. `InteractiveChart` is not optional here — it is what gives the
  control an entry in `chart_configuration`, which is where its scope lives.
  Declared alone, `NativeFilter` reaches no scope table at all and its value
  lands on every chart on the page regardless of which ones should keep their
  own history.
- **`table`** — a table whose cells are not text: ratio bars, sparklines, trend
  arrows, chips, expandable rows. Stock tables render strings and numbers;
  anything drawn inside a cell means this archetype.
- **`navigation`** — breadcrumbs, drill headers, or any element whose job is to
  move between states rather than plot data.
- **`map`** — values plotted at named geographic locations: a choropleth by
  country, region markers on a world map. Superset's own stock
  `legacy-plugin-chart-world-map` already depends on `datamaps`, so this
  archetype's plugins may import it — it is a real, already-installed
  dependency, not a new one to weigh.

A plugin may also carry its own control-panel UI, issue several queries, and
declare `DrillBy` / `DrillToDetail` / `InteractiveChart`. Say so when the
design implies it.

## Every filter is a grid element

A filter is a chart that happens to filter. `configure` it when a registry
plugin matches, otherwise `new_plugin` with `plugin_archetype:
"filter_widget"` — a plugin that declares both `Behavior.NativeFilter` and
`Behavior.InteractiveChart` and pushes `extraFormData`, so it drives every
other chart while sitting in the layout exactly where the design draws it.

There is no filter-bar route. Superset's own native filters are configured by
hand afterwards by anyone who wants them; nothing here creates one. A control
the design draws is a control the dashboard draws, in the same place.

**A region with several controls listed together is still one decision.** A
band of selects, a Daily/Weekly/Monthly toggle, a search box beside a
dropdown — however many controls stage A recorded inside one region's
`controls`, that region gets exactly one `ref`, one plugin, one entry in
`decisions`. The plugin's own component renders and drives every one of them
itself, each free to act independently — its own `setDataMask` call, its own
re-query, its own commit timing — the same way a chart with a view toggle
already re-queries on its own control without becoming three charts. This is
not a `container`: nothing here is a separately-saved chart being hosted, it
is one component with more than one piece of UI, and `container` is for
hosting other charts by id, not for a chart with several controls of its own.
**Never give two decisions the same `region_id`** to split one region's
controls across them — a region_id names one decision, and this is checked:
a second decision naming it is rejected, not read as a second chart.

**Carry the commit mode into the decision.** Stage A records whether the band
draws a commit button. Say in `rationale` which way it goes — selections held
until Apply is pressed, or applied as each control changes — because it decides
how many times the dashboard requeries, and it is the one thing about a filter
the user can see going wrong.

**A date or time range control is a `new_plugin` with
`plugin_archetype: "filter_widget"`, always.** Stage B binds it to a one-row
view carrying `range_start` and `range_end`; keep that binding. The plugin reads
those two dates and renders a calendar bounded by them, so the user can only
pick a window the data actually covers, and pushes the chosen range as
`extraFormData`. Say in `fidelity_loss` if it lands anywhere other than where
the design draws it. Never resolve one to the shared placeholder dataset — a
calendar with no bounds is a control that cannot open.

## Text costs no generation

- **`grid_text` by default, and especially for anything the design draws bare
  — but only when it is one line.** A `grid_text` decision becomes a
  `HEADER` node, which carries no chart header, no overflow menu, and holds
  exactly one line of text; there is no cheaper way to place a single-line
  heading, and `region.chrome.surface` of `bare` is stage A telling you a
  page heading sitting directly on the page background is the single most
  common thing this pipeline has put in a box the design never drew.
- **`configure` with `custom_text` — always, the instant the text needs more
  than one line.** A title with a subtitle beneath it, a caption with two
  lines, anything `region.observed` describes as more than a single line of
  text: this is not a `grid_text` decision, whatever `region.chrome.surface`
  says. Superset's `HEADER` node has nowhere to put a second line, and its
  `MARKDOWN` node — which can — always renders inside its own scrolling
  container, which no design draws and this pipeline does not build around.
  `custom_text` is a real, already-built plugin with separate `Text` and
  `Sub-text` controls for exactly this shape, so it costs one extra query
  against nothing, not a rebuild — use it whether or not the design draws a
  card, and let stage D leave its own chrome bare when it does not.
- **`configure` with `custom_text` for a single line, too,** whenever the
  text needs typography the dashboard's own styling cannot reach *and* the
  design draws it on a card. Typography mattering is not on its own a
  reason when the text is both single-line and bare: the chrome you inherit
  by becoming a chart costs more fidelity than the font gains there.

**Never build a new plugin to render text.** It costs ten minutes, a package
and a rebuild to do what `custom_text` already does for nothing.

A heading that also shows a queried value is not plain text — it reads data, so
it is a chart.

## Build what the design shows, including controls whose result it does not

A view toggle, a tab strip or an expand button drawn in the design is part of
the design, even when only one of its states is pictured. Keep the control,
build the state that *is* drawn, and leave the others empty or "Coming soon".
Do not drop a control because its other states are unknown, and do not invent
content for them.

A's `controls` list carries these, with what each icon looks like. They belong
to the section they sit on — they are not separate regions and get no decision
of their own.

## The user's answers are settled

If the input carries `user_answers`, the user has already been asked and has
answered. **Their answers are decisions, not opinions.** A plan step that
contradicts one is a bug, and the user has no way to tell you so — that was
their only turn. Where two answers conflict, follow the more specific one and
say which in `rationale`. Where an answer conflicts with the design, follow the
answer.

## Design-system contract

Emit one; every stage D worker obeys it.

```json
{
  "palette": ["#...", "..."],
  "color_scheme": "supersetColors | <registered scheme>",
  "label_colors": { "AWS": "#2563EB", "Azure": "#7C3AED", "Production": "#3B82F6" },
  "currency": { "symbol": "$", "format": "SMART_NUMBER" },
  "number_formats": { "money": "$,.2f", "percent": ".1%", "count": ",d" },
  "date_format": "%b %Y",
  "default_time_grain": "P1M",
  "row_limit": 1000,
  "legend": { "show": true, "position": "top" },
  "naming_convention": "<Dashboard> — <Metric> by <Dimension>",
  "show_values": false,
  "card_chrome": { "border": "1px solid #E5E7EB", "radius": "8px",
                   "shadow": "none", "padding": "16px",
                   "header": "13px/500, #6B7280, 8px below" },
  "typography": { "value": "24px/700", "label": "13px/500",
                  "caption": "11px/400" },
  "theme": "light"
}
```

`label_colors` maps a **category value** the design draws — a provider name,
an environment name, a series label — to the exact hex it is drawn in, for
every value you can read a colour off the design for. This is not the same
job as `color_scheme`: a stock chart type's own colour control only ever
picks a *named* scheme, and this pipeline registers none of its own, so a
registered scheme's colours never match a design's specific brand palette. A
category-to-colour map applies across every chart on the finished dashboard
regardless of `color_scheme`, matched by the category's own text — Superset's
existing per-dashboard colour settings, not a mechanism this pipeline has to
build. Report every category whose colour the design shows; leave one out and
its chart falls back to the dashboard's default scheme. This is separate from
`palette`, which is the same colours in the order they appear rather than
attached to what they mean.

`card_chrome` describes the card **Superset's own chart holder** is restyled
to match, once, for the whole dashboard. No plugin draws it. Report it
faithfully and do not thin it out for a plugin's benefit: plugin source may not
carry a literal colour, and the dashboard's stylesheet is where this one lands.

Every `card_chrome` value except `header` is written into the dashboard's CSS
as it stands, so it must be a CSS value a browser accepts: a description
(`subtle drop shadow`) is rejected. Every `typography` value starts with
`<size>px/<weight>`; a colour or a descriptor such as `uppercase` may follow
after a comma. Give one concrete value each: a range (`16-20px`), an
approximation (`~14px`) or an alternative (`blue or dark`) is rejected, because
parallel plugin authors each pick a different reading of it. Leaving
`card_chrome` or `typography` out when stage A observed one is rejected too.

`card_chrome` and `typography` come straight from stage A's `global`:
reconcile them into one repeated treatment rather than inventing your own.
They matter more than they look. Plugin authors run in parallel, each seeing
only its own card, and nothing makes six of them pick the same corner radius
except this. The card treatment is the most repeated thing on the page, so a
contract that omits it produces a dashboard inconsistent in exactly the way a
reader notices first.

### Magnitude suffixes and unit labels are two different problems

Establish **what the stored value is** before picking a mechanism. Stage B
built the tables, so its `fact_tables` tell you the real magnitude.

- **Base units, abbreviated by the design.** A number-format job: D3 SI
  (`,.3s`) or `SMART_NUMBER` scale and append the letter. `8920400` → `8.92M`.
  The common case.
- **Already scaled, with the unit drawn.** A column already in millions summing
  to `8920.13` and drawn as `8,920.4M`: `,.3s` gives `8.92k`, wrong by three
  orders of magnitude. Keep a plain format and put the unit in the subheader.

Never write that a suffix is impossible without saying which case applies —
the first is always achievable.

## A second attempt

If the input carries `you_asked_these_and_they_are_now_answered`, this is your
second pass. The user has answered; those answers are decisions, not opinions.
Fold every one into the plan and emit `needs: []` — you do not get asked again,
and the plan you return now is what gets built.

If it carries `validation_problems`, your previous plan was checked and
rejected. Those are mechanical checks, not opinions.

**Fix them as a patch.** Your last plan comes back to you as `your_last_plan` —
read it, because it is what you are correcting. Set `"revision": "patch"` and
put only the regions you are changing in `decisions`, each one whole, not a diff
of fields. Everything you leave out carries over from `your_last_plan`
untouched, and the merged plan is re-checked in full, so a decision you omit is
one you are standing behind.
Include `plan_for_review` again only if the fix changes what the user would
read; the same goes for `design_system` and `summary`. Re-emitting sixteen
unchanged decisions to correct one spends minutes and buys nothing.

If it carries `charts_you_already_searched`, that survey is **done**: it holds
every chart search from your earlier attempts and what each returned. Do not run
them again — read them and decide. Search only for something you have not looked
for yet, and never to confirm a result you already have.

If it carries `plan_feedback`, the user read your plan and sent it back. That
outranks your judgement.

## Output

This is your stage's contract, not the reply itself. Per the response envelope,
wrap the whole thing as `{"final": { ...this... }}` — never return it bare, and
never mix it with `tool_calls`. Concretely, the reply must look like:

```json
{"final": {"status": "needs_approval", "revision": "full", "decisions": [ ... ], "...": "..." }}
```

The `tool_calls` field *inside* the contract below is a count (an integer), not
a request to call tools. It does not change the wrapper: the whole object still
goes inside `final`.

The contract:

```json
{
  "status": "ready" | "needs_approval",
  "revision": "full" | "patch",
  "design_system": { ... },
  "decisions": [{
    "region_id": "...", "ref": "c1",
    "decision": "reuse|configure|new_plugin|grid_text|drop",
    "text": "markdown to render, for grid_text only",
    "viz_type": "...|null", "existing_chart_id": null, "children": ["c2","c3"],
    "plugin_archetype": "viz|container|filter_widget|table|navigation|map|null",
    "behaviors": ["InteractiveChart", "DrillToDetail"],
    "slice_name": "...", "rationale": "one sentence",
    "reuse_evidence": "what get_chart_info confirmed, or null",
    "thumbnail_evidence": "which thumbnails you compared and what you saw",
    "fidelity_loss": "what will differ, or null",
    "confidence": "high|medium|low"
  }],
  "needs": [{ "region_id": "...", "question": "...", "why_it_matters": "...",
              "options": ["..."], "default": "..." }],
  "counts": { "reuse": 0, "configure": 0, "new_plugin": 0,
              "grid_text": 0, "drop": 0 },
  "plan_for_review": [{
    "step": 1,
    "what": "one line naming the work in plain words",
    "why": "the thumbnail comparison or binding that decided it",
    "exactness": "how close to the design this lands",
    "cost": "queries per load, and whether code gets written"
  }],
  "tool_calls": 0,
  "summary": "N reused, M configured, K new plugins."
}
```

Return `"needs_approval"` whenever `counts.new_plugin > 0` — the orchestrator
gates there and shows the plan before any code is generated. Order `decisions`
so every container's children come before it.

## The plan a human will read

`plan_for_review` is shown to the user for approval **before anything is
created**, so write it for them. One object per meaningful piece of work,
carrying **what** you will do, **why** (citing the thumbnail comparison or the
binding), how **exact** the result will be, and what it **costs**.

**Four separate keys, not one sentence.** The four are shown in different
places: `what` is the step's heading, `why` sits under it, and `exactness` and
`cost` are labelled and set apart, because a caveat buried mid-paragraph is a
caveat nobody reads. A step written as a single prose string still renders, but
it arrives as an unbroken block with the caveat hidden in it.

- **Name the archetype in plain words.** "A wrapper card holding your three
  provider charts behind tabs" tells the user something; "custom plugin for
  r04" does not.
- **Every section appears.** A section you dropped or demoted is exactly the
  one the user needs to see. Silence reads as agreement.
- **Say what the dashboard will cost to load** — how many queries the finished
  chart runs every time someone opens it. Your own tool calls are not part of
  this; they happen once.
- **Say plainly where a step will not match the design.** The user is approving
  a specific outcome, and a step that oversells itself makes the approval
  meaningless.
