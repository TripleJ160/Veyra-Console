# Evidence and comparison scope

Baseline: upstream tag **v2.1.5**, peeled commit **dc6f6e1e** (full SHA in the release manifest). Upstream's product revision was `01dc81b3b4acc15f525b3865e62a54a052ce8219`; the tag also includes release documentation. This publication preserves that ancestry. Selected final source comes from research HEAD `507c5cc88ae2d042af336d79f42a77f5b0b407e5` plus its preserved Console/NR delivery changes. Machine-specific logs, capture identifiers, profiles and recordings remain local.

## Prior functional evidence

The runtime-complete **2.1.5-5090-looks** private development build passed 645 preset checks, 461 chain checks, 154 actual bridge checks, and QtQuick 176 passed / 0 failed / 1 skipped. A 14-phase recorded-playback smoke covered seven NR looks, runtime/model switching, all four AA methods, NR+DLAA and recovery to standard DLSS 2×. These are prior results. The source-preview validation receipt reports the publication-candidate checks separately; no public binary is distributed.

## Pixel comparisons

Saved graph outputs: native **2560×1440 SDR**, no SR/FG/sharpening, identical input/color/extent. NR-on AA cases use one SF B layer at 1440p, correction 0.25 and image-derived optical flow. Readbacks exist only in the test fixture, not the playback hot path.

Recorded sequence: 12 pictures from existing capture footage. Actual relative PTS (ms): `6.602, 24.355, 39.765, 56.487, 73.088, 93.534, 106.308, 123.294, 139.593, 156.385, 174.924, 189.872`. No CFR insertion/drop in this final comparison. The source is already processed/encoded console video; its game-engine cadence is unknown. The final picture is used consistently in the contact sheets.

Synthetic sequence: moving diagonals, thin lines and hard boundaries, 0.75 px/frame at explicit synthetic 60 Hz. Spatial edge quality was also compared with a 16×16 supersampled linear-light reference:

| Method | Shape-edge RGB-code MAE | Thin-line MAE |
|---|---:|---:|
| Off | 32.449 | 50.322 |
| FXAA High | 8.224 | 34.649 |
| SMAA High | 6.379 | 14.751 |
| MLAA | 10.971 | 39.289 |

All three spatial filters left 3,597,433 flat pixels unchanged. This establishes targeted edge improvement on this fixture, not a universal ranking. DLAA created/evaluated successfully: 12 evaluations, 11 motion-guided in each final sequence. It weakened some thin lines and changed broader texture. On the final recorded picture, pixels changed by at least one RGB code: FXAA 2.84%, SMAA 0.231%, MLAA 0.827%, DLAA 76.21%. **Change extent is not quality.** No AA shader strength or threshold was changed.

Subtle and Balanced stay progressively closer to Reference than Full on this sample. SF A and Original yielded identical final-frame pixels here; this does not establish general equivalence. Reduced really infers at 1920×1080 then composites to 2560×1440. There is no recovered-ground-truth, sustained-performance or latency claim.

## Images and limits

UI images are actual application screenshots with existing recorded footage and isolated preferences, not mockups. They demonstrate controls, not matched quality comparisons against upstream. The upstream comparison is source-backed unless explicitly labeled otherwise. No clean full-height image is published from this run; the occupied desktop prevented a suitable capture. The native caption is visible in the overview. Screenshots and Present counters do not prove physical display cadence.

NR/AA sheets are prior artifacts of the unchanged processing implementation. Runtime versions are listed in [RUNTIMES.md](RUNTIMES.md); their presence in the comparison does not mean those optional runtimes are publicly distributed. Game imagery belongs to its respective rights holders and illustrates processing differences; no video recording or game data files are distributed.
