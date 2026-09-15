# Stage F — Repair a plugin that does not compile

**This overrides the Output section of the system prompt.** That section asks
for a whole scaffold. The plugin has already been written, and TypeScript
rejected part of it: you are fixing it, not writing it again.

**Input:** the compiler's errors, the files they name with line numbers, the
files those import, and the name of every other file in the package.
**Output:** only the files you change.

## Your job

Fix exactly the errors listed, with the smallest change that fixes each one.

- **Do not restructure.** Do not re-architect, rename exports, change a
  control's name, split or merge files, or redesign what is drawn. Every line
  you did not need to change already compiled; rewriting it trades an error
  you can see for one you cannot.
- **The house rules still apply.** No `any` and no cast to `any`, no literal
  colours, and every Superset symbol through `src/adapters/supersetAdapter.ts`.
  An error is fixed by giving a value the type it needs, never by hiding it.
- **Fix the fault where it is.** An error reported in one file can belong in
  another — most often a symbol the adapter does not export. Change the context
  file when that is where the fix belongs, and keep everything it already
  exports.
- **Files marked as written by the skeleton cannot be changed.** A reply that
  returns one is rejected whole. If an error is in one of them, fix the file
  that feeds it.
- **Never delete a file**, and never return a file emptied.

## Reading what you are given

Each error names a file and a line, and shows the offending line with a little
context. The numbered contents of each failing file are exactly what the
compiler checked, so the line numbers match. The line-number gutter
(`117 | `) is not part of the file: never copy it into what you return.

A library's type is the specification. When an object literal is not
assignable to one, change the object to the shape the type accepts.

## Output

```json
{
  "status": "ok",
  "files": [{ "path": "superset-frontend/plugins/...", "contents": "..." }],
  "review_notes": "which error each change fixes"
}
```

- `files` holds **only** the files you change, each with its **full** new
  contents, at the full path shown. A file you leave out is kept exactly as it
  is on disk.
- Add `params_hint` only if a control's name or shape changed — which a repair
  should not need to do.
