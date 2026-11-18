# Kawaiicon 2026: Talks & Takeaways

An HTML slideshow (built with [reveal.js](https://revealjs.com/)) summarising the talks and learnings from
[Kawaiicon 2026](https://kawaiicon.org/), held 30–31 October 2026 in Wellington.

## Files

| File | Purpose |
| --- | --- |
| `index.html` | The deck |
| `css/theme.css` | Custom theme (colours and fonts are CSS variables at the top) |
| `assets/` | Images, logos, diagrams |
| `notes.md` | Per-talk notes: public summaries plus your own takeaways |
| `sources.md` | Per-talk links: abstracts, slides, write-ups, recordings |

## Viewing the deck

Open `index.html` in a browser. reveal.js and fonts load from a CDN, so an internet connection is needed.

If anything doesn't load from `file://`, serve the folder locally instead:

```powershell
npx serve .
# or
python -m http.server 8000
```

## Presenting

| Key | Action |
| --- | --- |
| `→` / `Space` | Next slide |
| `S` | Speaker notes window |
| `O` / `Esc` | Slide overview |
| `F` | Fullscreen |
| `Alt` + click | Zoom |

## Exporting to PDF

Open `index.html?print-pdf` in Chrome or Edge, then print to PDF (landscape, no margins, background graphics on).

## Workflow

1. Fill in **My notes**, **Key takeaway** and **So what for us** for each talk in `notes.md`, and set its priority.
2. Copy the content into the matching talk slide in `index.html` (or ask the agent to do it).
3. Choose the final recurring themes and top actions for the wrap-up slides.
