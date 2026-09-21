# Bring-up and test procedure — stereo rig

Staged so that each step depends only on the ones before it. If a stage
fails, fixing it there is much cheaper than discovering it three stages
later. Record the numbers as you go — the table at the end is what tells you
whether this method beats the one you already have.

Throughout: `py` is whatever launches Python on the warehouse PC.

---

## Stage 0 — Bench test, before you mount anything

Both cameras plugged in, sitting on a desk. You are testing the USB path,
not the optics.

```
py calibrate.py probe
```

**Pass:** both cameras open, both show live video simultaneously, and you can
tell which index is which. Set `camera_index_left` / `camera_index_right` in
`stereo_params.yaml`.

**If one camera fails to open, or video stutters or freezes:** USB bandwidth.
Two 1280×720 streams need MJPEG; uncompressed YUY2 at that size is ~55 MB/s
per camera and USB 2.0 carries ~35–40 MB/s in total. Move one camera to a
port on a different controller (usually a different physical side of the PC,
not another socket on the same hub) and retry. Solve this now — it will
otherwise reappear as mysterious frame drops during measurement.

---

## Stage 1 — Target, then mounting

```
py calibrate.py board
```

Print **at 100% scale**, measure the printed squares with calipers, put the
measured value in `square_size_cm`, glue the sheet to foam board or MDF.

Then mount the rig: two identical cameras ~15 cm apart along the **horizontal
(1280 px) sensor axis**, both pointing straight down, on **one rigid bar**.

Before calibrating, check the parcel envelope in `README.md` against your
largest packages. Raising the rig later invalidates everything from Stage 3
onward.

---

## Stage 2 — Calibration quality

```
py calibrate.py intrinsics left
py calibrate.py intrinsics right
py calibrate.py stereo
```

| Check | Target | If it fails |
|---|---|---|
| Intrinsics RMS, each camera | < 0.5 px | More views, sharper focus, better light, steeper tilts |
| Frame coverage | > 60%, grid mostly green | Put the board near the frame edges and corners |
| Stereo RMS | < 0.5 px | Recapture; make sure the rig did not move mid-capture |
| Recovered baseline | within 10% of 15 cm | **Re-measure the printed squares** — this almost always means `square_size_cm` is wrong |
| Focal lengths, left vs right | within 5% | The cameras are not a matched pair |

The baseline check is the important one. Scale enters this system in exactly
one place — the measured square size — so a baseline that is 8% off means
every dimension you ever report will be 8% off, and nothing downstream will
look wrong.

---

## Stage 3 — Rectification

```
py calibrate.py verify
```

Horizontal green lines are drawn across both rectified views. Put a
high-contrast object (a marker pen, a label corner) in the scene and track one
feature across both halves.

**Pass:** the feature sits on the same horizontal line in both views, anywhere
you move it in the frame. It shifts *horizontally* between the views — that
shift is the disparity, and it should grow as you raise the object toward the
cameras.

**Fail:** the feature drifts vertically between the views, or drift grows
toward the frame edges. The calibration is bad; go back to Stage 2. Do not
continue — every later number depends on this.

---

## Stage 4 — Depth on the bare conveyor

Nothing on the belt.

```
py stereo_check.py
```

Drag a box over an empty area of belt. Then press **F** to set it as the floor
reference.

| Reading | Expect | Meaning |
|---|---|---|
| **DENSITY** (top of screen) | > 60% | Fraction of pixels that matched. **This is the number that decides whether the method works in your warehouse.** |
| Region distance | matches your tape measure to ~1% | Absolute scale is right |
| Flatness RMS | < 0.1 cm | Your depth noise — and therefore your height precision floor |
| Tilt | small and stable | How square the rig is to the belt |

**If density is low (under ~30%) on the bare belt:** the surface has too little
texture to match. No calibration fixes this. Options, cheapest first: more or
more-angled light to raise surface contrast; a patterned mat on the belt; a
visible-light speckle projector aimed at the work area.

**If the distance is off by a consistent percentage:** `square_size_cm` is
wrong. Back to Stage 1.

**If flatness RMS is large (> 0.3 cm):** matching is noisy. Raise
`sgbm_uniqueness` for fewer but more trustworthy matches, or raise
`sgbm_block_size` for more smoothing at the cost of edge sharpness.

---

## Stage 5 — Known heights

Use rigid objects of accurately known height — machined blocks, a stack of
identical books measured with calipers, anything flat-topped and stable. Not
a box that might be bowed.

With the floor reference still set from Stage 4, place an object on the belt,
drag a box over its **top face only** (stay well inside the edges — depth is
unreliable in the transition band at a surface boundary), and read **HEIGHT
above floor**.

Test at least: a short object (~5 cm), a medium one (~20 cm), and the tallest
you expect to handle.

| Reading | Expect |
|---|---|
| Height error | within 0.5 cm, and no worse on the tall object than the short one |
| Density on the top face | > 60% |
| Flatness on the top face | similar to the floor's |

**If density collapses on a plain cardboard top but is fine on the belt:** this
is the texture problem, localized to the packages. Same fixes as Stage 4.

**If error grows with height:** the disparity search range may be clipping.
Check `max_parcel_height_cm` covers your tallest parcel.

**If error is a constant offset at all heights:** likely the floor reference
was taken over a region that is not the true resting plane.

---

## Stage 6 — Position and repeatability

Same object, moved around. This is where the original system's weakness
shows, so it is the direct comparison.

1. **Centre vs corners.** Measure the same object under the middle of the rig,
   then near each corner of the working area. Error should stay within the
   Stage 5 tolerance everywhere. *This is the test the current system fails:
   the existing parallax correction is exact only on-axis, so an off-centre
   package reads large.*
2. **Repeatability.** Same object, same place, 10 separate measurements —
   remove and replace it each time. Spread should be under ~0.3 cm.
3. **Rotation.** Rotate the object 45° about the vertical. Height must not
   change.
4. **Lighting.** Measure with the warehouse lights in their normal state, then
   with whatever variation actually occurs (a door open, a light off). Depth
   should hold; density may move.

---

## Stage 7 — Real packages, head to head

Take ~20 representative packages across your real size range. For each,
record the current system's L/W/H, the stereo rig's readings, and a
hand-measured truth.

| # | Package | True L/W/H | Current system | Stereo | Notes |
|---|---|---|---|---|---|
| 1 | | | | | |

Look for: which method is closer on average, which has the larger worst case,
and — most usefully — whether the errors depend on where the package sat.
Position-dependent error is the specific weakness the stereo rig should
eliminate.

Keep any package where stereo does *worse*. Those cases are what the
measurement pipeline needs to handle, and shiny tape, black surfaces and soft
bags are the usual culprits.

---

## Recording your results

```
Date:                        Mounting height:            cm
Baseline recovered:       cm   Intrinsics RMS L/R:      /      px
Stereo RMS:              px    Floor distance:          cm
Floor density:            %    Floor flatness RMS:      cm

Height checks     true      measured     error     density
  short                                                    
  medium                                                   
  tall                                                     

Off-centre worst error:        cm
Repeatability spread:          cm
```

If Stage 4 density and Stage 5 height error both pass, the approach works in
your warehouse and the measurement pipeline is worth building. If density
fails, solve texture first — no amount of code will.
