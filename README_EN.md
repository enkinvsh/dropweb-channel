<div align="right">
  <a href="README.md">Русский</a>
</div>

# dropweb-channel — Animated Sticker & Emoji Studio

End-to-end toolchain for creating branded animated Telegram stickers and custom emoji for dropweb: **from an AI prompt to a production `.tgs`**, complete with a browser-based animation studio for fine-tuning. Flat neon-green identity, pure vector Lottie/TGS pipeline, seamless 120 BPM loops.

## Quick Start

```bash
dropweb-studio            # alias: starts the studio server + opens http://localhost:8765
# or manually:
./run.sh studio
```

Prompt-based icon generation requires `CLIPROXY_KEY` (read from the environment or `~/.cli-proxy-api/cliproxyapi.conf.staged`, never committed to the repository). Without a key, everything except AI prompt generation works out of the box (PNG upload, animation tuning, `.tgs`/`.zip` export).

## Browser Studio (`http://localhost:8765`)

- **Creation**: text prompt → `gpt-image-2`, reference image (`image-to-image`), or direct PNG upload.
- **Auto-style enforcement**: prompts are normalized into flat neon icons with path-complexity budgets keeping the final `.tgs` ≤ 64 KB.
- **Animation tuning**: 40 whole-glyph animations + 8 per-element rigs, dual-layer blending, custom colors/rainbow/strokes, and an optional **tile background** (dark rounded squircle with configurable radius and color).
- **Pack management**: create, switch, rename, and delete packs or individual emoji.
- **Export**: download a single `.tgs` or a full pack `.zip` directly from the browser.
- **Pack persistence**: saving writes back to the pack definition on disk so the entire pack can be deterministically rebuilt from the CLI.

## Vector TGS Pipeline

1. `gpt-image-2` (`cliproxyapi` at `localhost:8317`) → raster icon from prompt/reference, or uploaded PNG.
2. Alpha/luma mask → `vectorize` (`potrace` + `picosvg`) → clean multi-path SVG (each `<path>` becomes an independently animatable element).
3. SVG → static Lottie base (`svg2base`).
4. Procedural animation (`studio.js` `makeAnimX`): per-element keyframes + whole-glyph rigs + optional background tile.
5. Gzip compression → `.tgs` (512×512, 60 fps, seamless loop at 120 BPM, ≤ 64 KB), ready for `@stickers`.

## CLI Commands

- `./run.sh studio [--port 8765]` — launch the interactive studio server and HTTP API.
- `./run.sh render [pack]` — render a **full pack into `.tgs` matching the studio output** via Node (`build/<pack>/tgs/`).
- `python -m tools.build_tgs --pack <name> [--id X] [--bg]` — full vector build from specs (`potrace` → `.tgs`).
- `python -m tools.studio_server --pack <name> --port N` — run the studio HTTP server directly.
- `./run.sh [--id X]` — legacy WebM sticker build (`build_emoji`).

## Repository Layout

- `studio/` — browser studio frontend: `index.html` + `studio.js` (animation engine shared between browser and Node CLI) + `bases.js`.
- `tools/` — `studio_server.py` (HTTP + API), `svg2base.py`, `vectorize.py`, `gen_icon.py`, `tgs_anim.py` (per-element presets), `build_tgs.py` (pipeline orchestrator), `build_emoji.py` (masks + legacy WebM), `render_pack.cjs` (Node pack renderer).
- `packs/<name>/` — `pack.json` (emoji specs and saved studio tuning) + `bases.json` (Lottie vector bases). Single source of truth for each pack.
- `build/<pack>/tgs/` — compiled `.tgs` files; `build/<pack>/preview/` — rendered preview frames.
- `docs/` — `brand-tokens.md` (brand specification), `plans/` (design docs), `animation-playbook.md`.

## Local Studio HTTP API

`GET /api/pack[s]`, `POST /api/generate` (with optional `ref`), `/api/regenerate`, `/api/upload`, `/api/save`, `/api/pack/create|rename|delete`, `/api/emoji/delete`.

See `docs/brand-tokens.md` for full visual and motion specifications.

## License

MIT — see [LICENSE](LICENSE).
