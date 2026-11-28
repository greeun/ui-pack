---
name: ui-pack
description: Use when applying a saved UI design system pack (tokens, fonts, components, motion, interactions, guide) to another project, or listing and viewing the available packs. Not for making or syncing packs - that is the ui-pack-create skill. Also fetches a published pack from its GitHub repository or Galpi entry. Triggers - "apply a UI pack", "apply the design system", "apply this pack from GitHub", "apply this pack from Galpi", "list packs", "view pack", "/ui-pack".
---

# ui-pack

A UI pack is a folder that holds one project's screen design: color, type and spacing tokens, fonts, components, motion, interaction hooks, a design guide, a gallery page and tests. Packs live in the pack store at `$UI_PACK_HOME/packs/<pack>/`, and a consuming project gets a pack by **copying** it with `install.py` (the consuming project never references the pack).

`UI_PACK_HOME` defaults to `~/.axt/vault/ui-pack`. When the variable is not set, write that path in its place in the commands below.

| Location | Content |
| --- | --- |
| `~/.claude/skills/ui-pack/` | This skill (usually a link to a clone of the skill repository). Changes to the skill are made in that repository |
| `$UI_PACK_HOME/packs/index.html` | The pack index: every pack with light and dark gallery preview images |
| `$UI_PACK_HOME/packs/<pack>/view/index.html` | The pack viewer: the component gallery (rendered by the real code, and working), the design guide, install details and the file list. It is one file with CSS, fonts and scripts inside, so it opens directly in any browser |
| `$UI_PACK_HOME/packs/<pack>/pack.json` | The pack definition (install list, required stack, optional groups, viewer settings). The format is in `references/pack-format.md` |
| `viewer/` | The Next.js template the pack viewer is built from. `scripts/build-view.py` uses it |
| `catalog.json` | The component catalog: the standard list of components a UI pack is expected to cover (category, name, description). Each pack records a status per component (`present`, `rules-only`, `absent`, `unused`) in `components` of its `pack.json`; the "Component catalog" section of the pack viewer and the component × pack table of the pack index show it |

**Core principle: a pack changes how the target app looks and responds; it does not change what the app does.** Features, data, the number of screens and the flows stay as they are, and the same work is redrawn with the pack's components and rules.

**App contract**: the following are part of what the app does, not of its look, so they do not change. The user's habits, automation and tests rely on them.
- Visible text (button, link, heading, hint, empty-state and error text), placeholders, `aria-label`
- The role of each element (a button stays a button, a link a link, a radio a radio), the `name` of inputs, link targets, `data-testid`
- The tab title (`metadata`), storage keys (`localStorage` and the like), keyboard behavior
- Content that appears on hover or focus, and its condition (tooltips, expanding descriptions). The look may change; the condition and the content stay
- Elements that hide or show by screen width (menus and links hidden on narrow screens), and the widths. Even when the pack shell's responsive layout is used, hide them at the widths where they used to hide
- How the theme is decided (a `.dark` class, a provider such as next-themes, the storage key). Do not add a theme switch to an app that had none
- Brand marks (the product logo, other companies' logos such as YouTube or Google, and their colors). Shape and color do not change. When a color outside the tokens is needed, keep it separately as a `--brand-*` variable

`compare.py` extracts this list from the screens before and after applying and compares them. `removed` must be 0.

## Actions

| Request | Action |
| --- | --- |
| "list packs", `/ui-pack list` | Show a table of name, version, description, requires and the pack viewer path from `$UI_PACK_HOME/packs/*/pack.json`. When asked about components, show a component × pack table from `catalog.json` and each pack's `components` |
| "view pack", `/ui-pack view [pack]` | `open $UI_PACK_HOME/packs/<pack>/view/index.html` (`$UI_PACK_HOME/packs/index.html` when no pack is named). When the pack viewer is missing or the pack was edited since, build it first with `python3 ~/.claude/skills/ui-pack/scripts/build-view.py $UI_PACK_HOME/packs/<pack>` |
| "apply pack", `/ui-pack apply <pack>` | "Apply" below |
| "fetch pack", `/ui-pack fetch <URL>`, or `/ui-pack apply <URL>` (a GitHub repository or a Galpi entry of a published pack) | "Fetching a published pack" below, then "Apply" with the fetched pack when the request was to apply it |
| "make a pack", "make a pack from this site, link or screenshot", "sync the pack" | Not this skill's job. Use the `ui-pack-create` skill (extracting from source code, making a pack from a URL, SNS post, screenshot or video, syncing with the source) |

This skill does not edit pack files. A request to change the pack's values while applying it is handled first with "Editing a pack" of the `ui-pack-create` skill, and the pack is applied after that. To apply a pack that is not merged yet, give the pack folder of that worktree where the commands below take the pack path.

## Fetching a published pack

Packs are published as public git repositories (`https://github.com/<owner>/ui-pack-<pack>`, with a Galpi entry that links to the repository).

1. Find the repository address. A GitHub address is used as given. For a Galpi entry, read the entry page and take its repository link (the `github.com/.../ui-pack-...` address in the entry); if there is none, tell the user and stop.
2. Fetch it into the pack store:
   ```bash
   python3 ~/.claude/skills/ui-pack/scripts/fetch.py <repository URL>
   ```
   The script refuses (exit code 3) a repository without a valid `pack.json`, with symlinks, with an install list that reads outside the pack or writes outside the target, or a pack name that already exists in the pack store. Do not work around a refusal; report it. When the name already exists, ask the user whether the existing pack is the same one (then use it) or which to keep.
3. A fetched pack is someone else's code. Before installing it, show the user the npm packages the script printed and the pack's `requires`, and go on only after the user agrees.
4. The fetched pack has no pack viewer (`view/index.html` is not published). Build it with `build-view.py` only when the user wants to see the pack first.

## Apply

### 1. Read
- Read all of `<pack>/pack.json`, `<pack>/README.md` and `<pack>/guide/ui-direction.md` (the design guide, including the "pack note" at its top). The README and the design guide tell you which components this pack has and what they are for. When the user wants to see the pack's look first, open the pack viewer.
- Survey the target project: `package.json`, the list of screen files, existing shared components, and whether it has sign-in and background jobs.

- **Capture the screens before installing.** Start the target's dev server and capture every route this work will change. After the install the "before" screens cannot be obtained again.
  ```bash
  python3 ~/.claude/skills/ui-pack/scripts/compare.py capture --base http://localhost:<port> --routes / /settings --out <compare-folder>/before
  ```
  Keep `<compare-folder>` outside the target project (a temporary work folder, for example). The app contract (`*__contract.json`) is saved along with the screens. Stop this server after capturing.
- Decide the scope: the whole app or some screens. For some screens, also follow "Applying to a limited scope" below.

### 2. Install (the mechanical part is a script)
```bash
# product-name: when the user did not give one, use the name in package.json and note where to change it (productName in ui-pack-config.ts) under "Open issues" in the final report
python3 ~/.claude/skills/ui-pack/scripts/install.py $UI_PACK_HOME/packs/<pack> <target> --name <product-name> [--without jobs] [--keep-defaults] --dry-run
python3 ~/.claude/skills/ui-pack/scripts/install.py $UI_PACK_HOME/packs/<pack> <target> --name <product-name> [--without jobs] [--keep-defaults]
```
- When the target has no background-job feature (a job progress API), pass `--without jobs`. When applying to some screens only, pass `--keep-defaults`.
- Commit the `ui-pack.lock.json` the script leaves to the target repository. On a later install it keeps files edited after the install (the config, the design guide, the merged `globals.css`) from being overwritten.
- The script deletes the `.next` build cache (so stale CSS is not served from it). It is rebuilt when the dev server restarts.
- When the script stops on a required-stack mismatch, follow "When the stack differs".
- When it finishes, handle the "Next steps" in its output: merge `layout.tsx` with the `.pack-example` file (fonts, `lang`, the theme script, `suppressHydrationWarning`), and set the menu, sign-out and job URLs in `ui-pack-config.ts` for the target. `lang` must name the language the app's screens are written in. With no sign-in, `logout: null`. Leave the target layout's `metadata` (tab title), providers and global components (notifications and the like) as they are.
- Edit the installed `docs/design/ui-direction.md` as its "pack note" says, to fit the target app: replace the screen definition sentence of section 1, the examples of the identity in section 2 and the domain terms in the word table of section 8 with the target app's, and remove product-only content. Do not finish with this step left over.
- The gallery page (`components/design/Gallery.tsx`) is a pack file too, so do not edit it. Gallery copy is sample wording that is not tied to any domain.
- Check whether the target's own CSS in each `.before-pack` file (global rules other than fonts, and so on) should be carried over, then delete the file.

### 3. Convert the screens
Rewrite each screen file with the pack's components and tokens. The pack's README and design guide name the components it has. The table below is the typical mapping for a pack that follows the inkpaper layout; a pack that lacks one of these components, or names it differently, says so in its README.

| What the target has | What to use from the pack |
| --- | --- |
| The frame of the whole screen, top or side menu | Wrap with `AppShell` in the layout and move the menu to `ui-pack-config.nav`. Delete the menu markup each screen had. When the menu has app-specific behavior (a menu that changes with the sign-in state, a sign-in link, the user name), keep that markup and behavior and change only the look, with the same classes `AppShell` uses |
| A theme switch the app already has | Keep that button (same name, storage key and number of states) and change only its look. Wire it to also set `<html data-theme>` when switching, so the pack tokens read it |
| An app with a theme mechanism (next-themes and the like) but no switch on screen, or no theme mechanism | Do not add a switch (`themeSwitch: false` in `ui-pack-config`). When the app's mechanism turns `.dark` on, only wire `data-theme` to change with it. When the user wants a switch, write it under "Suggestions" |
| Page title | `PageTitle` |
| White boxes, card sections | `Panel` (a section); `ItemCard` for repeated items |
| Buttons, link buttons | `primaryButton` (one per screen), `secondaryButton`, `dangerButton`, `textButton`, `textLink` in `ui.ts`. The element does not change (`<button>` stays `<button>`, `<a>` stays `<a>`) |
| Inputs, labels, error text | `fields.tsx` and the input classes in `ui.ts` |
| Status display such as running or done | `StatusMark` (color and text together) |
| Counts and tags for things waiting for the user | `WaitTag` (in the pack's accent color) |
| Empty list, loading, error | The look of `EmptyState` and `DataState`. Put the original text in as it is. Remove spinners, and only where there was no text at all put the loading sentence the pack's design guide gives, in the app's language |
| Progress with a known total (n/m) | `ProgressBar` (only where a bar or number already was) |
| Items entering and leaving a list | `motion/AnimatedList` |
| Confirming a successful action | `motion/useConfirmFlash` |
| A reorder feature that already exists | `SortableList`, `GroupedSortable` |
| Choosing one | When it was a radio group, `ChoiceGroup`. When it was a group of buttons, keep the buttons and show the chosen state with the `secondaryButton` or `tabLink` look and `aria-pressed` (switching to `ChoiceGroup` turns buttons into radios) |
| Arbitrary color, shadow and radius classes (`bg-blue-600`, `shadow-lg`, `rounded-xl` ...), gradients, emoji decoration | Remove them and use token classes (`bg-surface`, `text-ink-2`, `rounded-panel`, `shadow-lift-1` ...) |

Rules:
- **Do not add features.** Do not create confirmation steps, leave warnings, new cards, charts, number tags or data fields the target did not have. When a feature would be better with a pack component, do not build it; write it under "Suggestions" in the final report.
- **Do not remove features.** Keep every behavior that was there (add, check, delete, links) and the whole app contract (above). Keep links and brand marks (logos, the logo in "Continue with Google") even when they look decorative. Remove icons only when they are decoration without meaning.
- **Do not change the wording.** Leave text that does not follow the sentence rules of the design guide's section 8 as it is, and write the proposed rewording under "Suggestions" in the final report. Adding a visible label that was not there (a label above an input, for example) is allowed and is reported as `added` in the comparison.
- **Identity elements** (in an inkpaper-style pack: time notation, number tags, bands proportional to length; in general whatever section 2 of the pack's design guide lists) are used only when the target already has that concept. Example: when there is a duration value, change it to the fixed-width notation, but do not draw a band that was not there.
- Do not edit component files (the pack files under `components/` and `lib/`). Values that differ per app are set only in `ui-pack-config.ts`. When a component must be edited, report it with the reason.
- Do not use design cleanup skills such as antislop or unslop in the apply phase. The pack's look went through that check when the pack was made, and those skills change look and wording in a direction different from the pack (an app contract violation). Decoration left in the target screens is removed with the mapping table above and the check for colors outside the tokens.

### Applying to a limited scope (some screens only)
- Install with `install.py --keep-defaults`. The Tailwind default color, type, radius and shadow tokens stay, so the screens that are not converted look as before.
- Move the existing tokens (shadcn variables and the like) and dark-theme variants from `globals.css.before-pack` to the end of the new `globals.css` (for the screens that are not converted). Then delete the `.before-pack` file.
- Among the existing global rules, **element selector rules** (rules that set type, color or borders on `h1`-`h6`, `a`, `body`, `*`, `button` and so on) leak into pack components too (example: `h1, h2 { tracking-tight }` changes the letter spacing of the pack's card titles). Do not carry them over, or put a class (for example `legacy`) on the top element of the screens that are not converted and carry them over narrowed, as `.legacy h1`. Class rules (`.glass` and the like) can be carried over as they are.
- Run the grep for colors outside the tokens only on the files changed this time. Report the screens that were not converted as a list.

### 4. Verify (run all of it and attach the results to the report)
1. `next typegen` (the route types Next.js generates, such as `LayoutProps`; without `.next`, `tsc` fails unless this runs first) → `tsc --noEmit`, lint, the pack tests (`vitest run tests/`). When the target's vitest uses the jsdom environment, run the pack tests separately as a node-environment set.
2. **Restart** the dev server (a server started before the install keeps serving the old CSS), then capture each screen and `/design` with headless Chrome:
   ```bash
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --hide-scrollbars \
     --force-prefers-reduced-motion --blink-settings=preferredColorScheme=1 --virtual-time-budget=8000 \
     --window-size=1440,2400 --screenshot=<file>.png <url>
   ```
   `preferredColorScheme=1` is the light theme, `0` the dark theme. Reduced motion must be on to capture the screen after its entrance motion ends. A narrow width only works down to `--window-size=500,...`, so check anything narrower with an `<iframe width=400>` page.
3. Compare by computed style whether the gallery looks the same as the pack's. When the target's global CSS leaks into pack components, it shows up here. The result must be "0 differ"; otherwise find the rule the output points to and narrow its scope.
   ```bash
   node ~/.claude/skills/ui-pack/scripts/gallery-check.mjs $UI_PACK_HOME/packs/<pack> http://localhost:<port>/design
   ```
   Look at the captures yourself and compare them with the `/design` gallery: the look of the background, cards and buttons, whether the accent color is used only with the meaning section 2 of the design guide gives it, and whether any color outside the tokens is left (`grep -rnE "(bg|text|border)-(gray|blue|red|green|yellow|purple|slate)-" src/app src/components` must print nothing).
4. Go through section 10 of the design guide (pre-delivery checks) item by item. Item 5 (the design quality checklist, antislop) was done when the pack was made, so it is not done in the apply phase; write "not applicable (checked when the pack was made)".
5. Capture the screens after applying, with the same routes as in step 1, and build the before/after comparison page. When `removed` in the app contract output is not 0, restore those items (text, role and link back to the original). Write the `added` items in the report with the reason. Open the comparison page yourself and check that both screens show the same content.
   ```bash
   python3 ~/.claude/skills/ui-pack/scripts/compare.py capture --base http://localhost:<port> --routes / /settings --out <compare-folder>/after
   python3 ~/.claude/skills/ui-pack/scripts/compare.py page --before <compare-folder>/before --after <compare-folder>/after --out <compare-folder>/index.html --title "<app name> before and after <pack>"
   ```
6. Stop the dev server you started (with TaskStop when it runs as a background task) and check that no process is left.

### 5. Final report (in this order)
1. Install: a summary of the script output, and the groups left out with `--without`
2. Mapping per screen: a "before → pack component" table for each screen
3. Features preserved: the list of behaviors that were there and the check result of each
4. Verification results: the commands and their output, **the path of the before/after comparison page (`<compare-folder>/index.html`) and the app contract comparison output (`removed` 0, the list of `added`)**, the `gallery-check.mjs` output ("0 differ"), the result of the section 10 checks
5. Suggestions: features that pack components could add but that were not built
6. Open issues

## When the stack differs
- With React below 19, a Next.js app that does not use the App Router, or Tailwind below 4, do not copy the components. Tell the user and let them choose: (1) upgrade the target's stack and then apply, or (2) carry over only the tokens (the CSS variables in `tokens/globals.css`), the fonts and the design guide, and write the components anew in the target's stack from the design guide.

## Common mistakes
| Mistake | Correction |
| --- | --- |
| Building the source app's features (bands, number tags, confirmation steps) anew for "the same design" | Carry over the look only. Report features under "Suggestions" |
| Copying files by hand, one at a time | Use `install.py` |
| Verifying with the dev server started before the install | Restart the server |
| A test checks source-only tokens such as caption colors, so they cannot be deleted from `globals.css` | Leave the tokens and remove them from the design guide only |
| Only the dark theme gets captured | Set `preferredColorScheme` explicitly |
| Leaving the design guide edit as "remaining work" | Finish it within the apply phase |
| Changing button names and hint text to fit section 8 of the design guide ("Load" → "Import", "Generate" → "Create banner") | Wording is app contract. Leave it and write it under "Suggestions" |
| Keeping a logo but turning it into the single ink color | A brand logo keeps its colors too (`--brand-*`) |
| A menu that used to hide on narrow screens becomes visible because of the pack shell | Hide it at the widths where it used to hide (responsive behavior is app contract too) |
| Adding `ThemeSwitch` to an app that had no theme switch | Set `themeSwitch: false` and write it under "Suggestions". When only some screens are converted, the theme would also drift apart from the screens that were not |
| Polishing the screens with antislop or unslop in the apply phase | Do not. Carrying the pack over as it is, is the job of this phase |
| Making a description that showed on hover always visible, or removing a tooltip behavior that looks like a defect | The condition for appearing is app contract too. Change only the look and write the fix under "Suggestions" |
| Turning a group of buttons into `ChoiceGroup`, or a button into a link | Keep the role of the element. Change only the look, with pack classes |
| Swapping the app's theme switch or account area for pack components | Keep the behavior of the original component and change only its look |
| Changing the gallery (`Gallery.tsx`) copy to the target's words | Do not edit the gallery |
| Only some screens were converted, and the colors of the other screens disappear | Install with `--keep-defaults` and keep the existing tokens |
| Existing `h1`-`h4` or `*` rules that were kept change the letter spacing or borders of titles in the pack gallery | Do not carry over element selector rules, or narrow their scope. Check with `gallery-check.mjs` |
| Taking the install as stopped because `pnpm add` failed with "ignored build scripts" | The script checks that the packages are installed and continues. The `allowBuilds` decision is left to the user |
| A `tsc` error that `LayoutProps` cannot be found | Run `next typegen` first |
| Referencing the pack from the consuming project by link or path | Copy it with `install.py`. The consuming project must build without the pack |
