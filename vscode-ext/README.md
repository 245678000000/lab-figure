# Lab Figure Preview

Live preview for lab-figure R scripts in VS Code and Cursor: the script on the
left, the figure on the right, redrawn after every edit — whether you type it or
an agent (Claude Code, Codex, Cursor) writes the file.

## Use

Open a figure script (`figures/*.R`, `examples/*.R`) and click the preview icon
in the editor title bar, or run **Lab Figure: Open Figure Preview**.

- **Redraws** 300 ms after the last edit. The data section (everything above
  `# ---- plot ----`) runs once and is cached; editing the plot section only
  re-runs the plot code.
- **Errors** are underlined on their line in the editor; the panel keeps the
  last figure that worked, dimmed.
- **Size** previews the figure at another preset; **Zoom** switches between
  fitting the panel and true size.
- **Export and check** saves the script, runs it for real (writes the PDF/PNG)
  and runs the font-size and collision checks on each PDF.
- In preview, `save_fig()` hands the plot to the panel instead of writing files.

## Requirements

- R with the `labstyle` package installed (`Rscript setup/install_r_packages.R`
  in the lab-figure repo).
- For Export and check: the lab-figure skill installed at
  `~/.agents/skills/lab-figure` (or set `labFigure.labfigPath`).

## Settings

| Setting | Default | |
|---|---|---|
| `labFigure.rscriptPath` | search PATH and `/usr/local/bin`, `/opt/homebrew/bin`, the R framework | Rscript for the worker |
| `labFigure.labfigPath` | `~/.agents/skills/lab-figure/scripts/labfig` | used by Export and check |
| `labFigure.debounceMs` | 300 | wait after the last edit |
| `labFigure.renderTimeoutSeconds` | 120 | longer renders restart the worker |

The R worker's log is in the **Lab Figure** output channel.

## Develop

```bash
npm install
npm test          # compiles and drives the real R worker
npm run package   # lab-figure-preview-<version>.vsix
```
