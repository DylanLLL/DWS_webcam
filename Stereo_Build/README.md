# Stereo DWS — dual top-mounted camera measurement

An alternative measurement method for the DWS system. Instead of two cameras
each measuring their own dimensions in 2D (top = length/width, side = height),
this uses **two identical cameras mounted side by side above the conveyor** as
a stereo pair, and recovers length, width and height together from one 3D
reconstruction.

`DWS_Build/` — the original, working single-top-plus-side system — is
untouched and remains the production fallback. This directory is self-contained
and does not import from it.

## Why

The original system measures length/width and height independently, then
couples them with a correction factor: the top camera reads the side camera's
height to correct its cm-per-pixel ratio, and the side camera reads the top
camera's offset to correct its own. That mutual loop is approximate in two
ways. The parallax correction `RATIO * (1 - height / D_FLOOR_TOP)` is exact
only for a package directly under the lens — one off to the side also shows
its side walls to the camera, inflating the measured outline in a way a single
scalar ratio cannot describe. And no lens distortion is corrected anywhere.

A calibrated stereo pair replaces both approximations with geometry:

- Every pixel becomes a real 3D ray, with lens distortion removed.
- Height comes from a plane fit over the whole top face, not from a manually
  set floor line.
- The top face's plane is known exactly, so the package outline can be
  back-projected onto it instead of scaled by an approximate ratio.
- Shadows stop mattering. A shadow lies on the floor plane, so filtering the
  point cloud by height discards it — no HSV shadow heuristics to hand-tune.

## Hardware

Two **identical** camera units, ~15 cm apart, both looking straight down,
on **one rigid bar**. Separate brackets flex, and any flex invalidates the
calibration.

Mismatched cameras will produce a technically valid calibration that performs
poorly: rectification resamples both views to a common focal length, so the
sharper camera's resolution is thrown away, and block matching across views
with different magnification, blur and vignetting degrades badly. The tool
warns if the two focal lengths differ by more than 5%.

Separate the cameras along the sensor's **horizontal (1280 px) axis**.
Rectification assumes horizontal disparity, and that axis has field of view to
spare — the 720 px axis is the tighter constraint, so putting the baseline
there would cost working area where you have none free.

### Choosing the mounting height

Do this *before* calibrating. Raising the rig afterwards invalidates
everything from the `stereo` step onward.

At f ≈ 1123 px on 1280×720, mounted 100 cm above the conveyor, the largest
parcel footprint that stays fully inside the stereo overlap is:

| Parcel height | Along baseline | Across baseline |
|---|---|---|
| 0 cm | 99 cm | 64 cm |
| 20 cm | 76 cm | 51 cm |
| 40 cm | 53 cm | 38 cm |
| 60 cm | 31 cm | 26 cm |

The right-hand column binds at every height, so the 15 cm baseline is
effectively free — it eats into the axis that had slack. Check the table
against your largest packages; if they do not fit, mount higher.
`calibrate.py stereo` reprints this table from your real calibration.

## Procedure

Install dependencies:

```
pip install opencv-python numpy pyyaml
```

### 1. Print and measure the calibration target

```
py calibrate.py board
```

Print the generated PNG **at 100% scale** — turn off "fit to page". Home
printers rescale by a few percent, and this target is the only thing that sets
the system's absolute scale, so a 3% printing error becomes a 3% error in every
dimension the system ever reports.

Then **measure the printed squares with calipers**, spanning several squares
and dividing, and put the measured value into `square_size_cm` in
`stereo_params.yaml`. Do not assume it printed exactly.

Glue the sheet to foam board or MDF. The calibration assumes the target is a
plane; a curled or hand-held sheet is not one.

### 2. Identify the camera indices

```
py calibrate.py probe
```

Note which device index is which camera and set `camera_index_left` and
`camera_index_right`. Left/right are as seen in the images, not from where you
are standing. Indices can change across reboots and USB replugs.

### 3. Calibrate each camera's lens

```
py calibrate.py intrinsics left
py calibrate.py intrinsics right
```

Intrinsics are **per physical unit, not per model** — two copies of the same
webcam differ in focus and manufacturing tolerance, so each gets its own pass.

Hold the board in view and press SPACE to capture each pose. The on-screen
coverage grid shows which parts of the frame have board samples. Fill it, and
include steep tilts. Distortion coefficients are only constrained where you
actually put the board, so a calibration built from flat centred views is
wrong at the frame edges — exactly where a package sitting off to one side
gets measured.

Press C to calibrate once you have 15+ views. Aim for an RMS below 0.5 px.

### 4. Mount the rig, then stereo calibrate

The rig must be in its **final** position first — these extrinsics describe
where the two cameras sit relative to each other.

```
py calibrate.py stereo
```

Hold the board where both cameras see it; capture is only allowed when both
detect it. Vary depth and tilt across the shared field.

The tool reports the **recovered baseline**, which is really a check on
`square_size_cm`: scale enters the system in exactly one place, so a baseline
10% off nominal means the square size is about 10% wrong, and so is everything
downstream.

### 5. Verify

```
py calibrate.py verify
```

Horizontal lines are drawn across both rectified views. A feature must land on
the same line in both — that is what reduces the disparity search to one
dimension. Vertical drift between the views means a bad calibration; redo it.

### 6. Check depth, then validate against known objects

```
py stereo_check.py
```

Drag a box over bare conveyor, press F to set it as the floor reference, then
drag over the top face of an object of known height. Watch the DENSITY figure:
it is the fraction of pixels that matched, and on low-texture surfaces it is
what decides whether this approach works at all.

With the side camera gone there is no independent height reading to check
against, so validate against rigid objects of accurately known size before
trusting the system on real packages.

**`TESTING.md` has the full staged procedure**, with the number to expect at
each stage and what to do when one fails.

## Files

| File | Purpose |
|---|---|
| `calibrate.py` | Calibration tool. Sub-commands: `board`, `probe`, `intrinsics`, `stereo`, `verify`. Replaces `ratio_calibration.py`. |
| `camera_config.py` | Opens cameras with identical locked settings. Used by both calibration and measurement so the two cannot drift apart. |
| `stereo_params.yaml` | Board geometry, measured square size, camera indices, locked capture settings. |
| `stereo_check.py` | Diagnostic: live disparity/depth view, match density, and plane fitting for distance, flatness and height. Run this before building anything else on top. |
| `stereo_depth.py` | Rectification, disparity and plane fitting. Shared by the diagnostic and the eventual measurement pipeline, so validating one validates the other. |
| `TESTING.md` | Staged bring-up and test procedure, with the number to expect at each stage. |
| `calib/` | Calibration output (git-ignored — specific to one physical rig). |

## Capture settings, and why they are locked

`camera_config.py` is deliberately the single place cameras are opened. A
calibration is only valid for the optical configuration it was captured under.

- **Autofocus off.** A refocus changes the focal length and silently
  invalidates the intrinsics. This is the easiest one to overlook.
- **Identical exposure on both cameras**, and the same value at calibration
  and at runtime. (The original scripts used different exposure and ISO on
  the two cameras — fine when they measured independently, not fine for a
  stereo pair.)
- **MJPEG.** Uncompressed YUY2 at 1280×720×30 is ~55 MB/s per camera; USB 2.0
  carries ~35–40 MB/s in total. One raw stream already exceeds the bus. Put
  the two cameras on separate USB controllers where possible.

## Not yet built

The measurement pipeline itself — rectify, match, fit the floor and top-face
planes, segment by height, back-project the outline, emit L/W/H. It will reuse
`launcher.py`'s hotkey, clipboard-weight and dashboard-paste logic from
`DWS_Build/`, none of which depends on how the dimensions were measured.

One risk to plan for: **plain cardboard has almost no texture**, and block
matching needs distinctive patches to correspond. The intended approach is to
use stereo for the top-face depth only and keep the existing outline
segmentation for length and width, back-projecting it onto the now
exactly-known plane. If dense depth turns out to be necessary, a visible-light
speckle projector is the standard fix (webcams have IR-cut filters, so an IR
pattern would need the filter physically removed).

## Why the cameras are vertical and parallel, not angled

**Converging them** (toeing them in toward each other) gains nothing.
`stereoRectify` computes virtual rotations that make the two image planes
coplanar, so a converged rig is rectified back to a parallel one anyway — and
the keystone distortion that convergence introduces shrinks the valid
rectified region, costing working area. Small *accidental* misalignment is
fine; that is what the extrinsics are for.

**Tilting the whole rig off-vertical** trades away more than it gains. Stereo
depth error acts along the camera ray, so tilting splits that error into a
vertical part and a horizontal part. The vertical part shrinks slightly — and
the horizontal part, which was zero, starts contaminating length and width:

| Tilt | Height error | L/W error vs vertical |
|---|---|---|
| 0° | 0.300 cm | 1.00x |
| 10° | 0.295 cm | 1.16x |
| 20° | 0.282 cm | 1.53x |
| 30° | 0.260 cm | 1.96x |

At 20° you gain 6% on height and pay 53% on length and width. Length and width
come from image edges, which are far more precise than disparity, so tilting
injects the noisier measurement into the more accurate one.

A tilted pair would also see one side face — but for a cuboid on a flat
surface that adds no information. The top face's outline already gives length
and width exactly, and the floor-to-top-plane distance gives height. Tilting
would help only for non-cuboid parcels, and it costs worse self-occlusion
(a tall box hides the floor behind it) and a wider disparity search.

## Limits of a top-down rig

A top-mounted pair measures the top face plus the height. For a rectangular
box that is exactly L/W/H. For a soft bag or a tapered parcel the top-down
outline is not the true maximum footprint, and no overhead rig can see an
undercut.
