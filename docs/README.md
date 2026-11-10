# Docs

All of these come from a real mock-mode run: `python main.py simulate --weeks 2 --fresh`, then `python main.py week` for week 3, so three week-3 videos are waiting for review. Rebuild the storyboard and terminal image with `python docs/build_docs_images.py`.

## Diagrams (`diagrams/`)
| File | Shows |
|---|---|
| 01_architecture | Agents, Prune gateway (one key per agent), video pipeline, database, approval gate, YouTube |
| 02_weekly_loop | Plan → produce → professor review → publish (private) → measure → review and plan |
| 03_handoff_sequence | One production run, including the Fact-Checker sending a draft back |
| 04_approval_gate | Every rule an upload must pass |

`.mmd` files are Mermaid source, so you can edit them in VS Code or mermaid.live. The `.png` files are rendered.

## Screenshots (`screenshots/`)
| File | Shows |
|---|---|
| 00_terminal_week1 | Week 1 of the simulation in the terminal |
| 01_review_queue | Review page: 3 waiting, 4 uploaded (private), 1 rejected |
| 02_review_page_pending | One video waiting: player, script, fact-check, titles, cost, and the Approve / Request changes / Reject buttons |
| 03_review_page_after_changes | A video after "request changes" → revision 2 → approved → uploaded private |
| 04_dashboard | Profit per video and cost per agent |
| 05_weekly_report_week2 | The week 2 report with the Business Manager's plan for week 3 |

## Storyboard (`storyboard/`)
Every scene of W01E02, revision 2: the real slide, timing, voice text, on-screen text, and the professor's spot.

## Samples
- `sample_reports/`: weekly reports for weeks 1 and 2 (Markdown and HTML)
- `sample_video/`: W01E02_r2.mp4 (burned-in captions plus a soft subtitle track), the .srt file, and the exact upload request the uploader would send to YouTube
- `simulation_log.txt`, `week3_production_log.txt`: full console output
