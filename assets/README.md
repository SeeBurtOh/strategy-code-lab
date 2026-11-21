# Visual assets

| Asset | Origin | Resolution |
| --- | --- | --- |
| `hero.png` | Custom conceptual illustration; built-in image-generation tool | 1672 × 941 |
| `backtest.png` | Matplotlib plot of the included synthetic demo | 3000 × 1800 |
| `screenshots/strategy-editor.jpg` | Browser capture of the running offline Gradio app | 1280 × 720 |
| `screenshots/backtest-results.jpg` | Browser capture after running the synthetic backtest | 1280 × 720 |

The hero is artwork, not a product screenshot or a performance claim. The model returned the native resolution shown above; it has not been upscaled. No API keys, account details, or personal trading data appear in these assets. Screenshots are unretouched captures.

Regenerate the chart with `python scripts/export_demo.py` after installing `requirements-dev.txt`.

## Hero prompt

The built-in image-generation tool was used, rather than the API/CLI fallback.

```text
Use case: stylized-concept
Asset type: professional GitHub portfolio README hero, landscape high resolution 2560 x 1440 or higher.
Primary request: polished editorial illustration for "Strategy Code Lab", a Python AI code generation and simulated equity trading project.
Scene: dark midnight navy studio with precise luminous teal and pale blue glass layers. Three elegant floating panels suggest a written idea becoming structured code and then a restrained data chart, connected by fine paths. Abstract short code strokes, tiny structured nodes, a modest fluctuating chart with both rises and falls; no profit claims or actual metrics.
Style: premium architectural 3D illustration, clean geometric surfaces, subtle depth and soft volumetric lighting, highly detailed crisp edges, sophisticated editorial technology aesthetic.
Composition: wide balanced cinematic composition with generous breathing room, restrained visual density.
Text: no words or numbers.
Avoid: logos, company trademarks, coins, dollar signs, bullish arrows, robot heads, watermarks, fake app screenshots. This is conceptual artwork, not a UI.
```
