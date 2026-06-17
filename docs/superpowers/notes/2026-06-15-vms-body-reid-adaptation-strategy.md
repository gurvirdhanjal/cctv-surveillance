# Body Re-ID Domain Adaptation Strategy

**Research Note** · 2026-06-15  
**Status:** Reference only — no plan written, no implementation started

---

## Context

The deployed body re-ID model (`ViT-B16+ICS_MSMT17.pth`) is supervised-trained on MSMT17
(street pedestrians, 1041 identities, 75.1 mAP / 89.6 R1). Plant-floor workers wearing
identical PPE (hard hats, hi-vis vests, gloves) represent a real domain gap: MSMT17 feature
space discriminates on clothing colour and texture, which collapses when everyone wears the
same gear. Two adaptation strategies exist when this becomes a problem.

### Assets on disk

| File | What it is | Role in adaptation |
|---|---|---|
| `models/ViT-B16+ICS_MSMT17.pth` | Complete supervised model (768-dim BNNeck, 1041-class head) | Starting point for UDA fine-tuning |
| `models/vit_base_ics_cfs_lup.pth` | SSL-pretrained backbone only (no ID head, no BNNeck) | Alternative backbone init for USL training from scratch |

---

## Approach 1 — UDA (Unsupervised Domain Adaptation)

**When to use:** A specific customer site is deployed and body re-ID accuracy is measurably
poor (e.g. cross-camera re-ID precision < 60% on internal eval). You have unlabeled footage
from the target site but do not want to manually label workers.

**How it works:**

1. **Source:** labeled MSMT17 identities (already in the checkpoint)
2. **Target:** unlabeled tracklets from the customer's cameras (collected offline from a
   1–2 hour recording with no people removed — just raw detections)
3. **Pseudo-label loop:**
   - Extract embeddings for all target tracklets using current model
   - Cluster with DBSCAN or k-means → each cluster = pseudo-identity
   - Fine-tune with combined loss: cross-entropy on source + contrastive/triplet on pseudo-labeled target
   - Re-cluster every N epochs (typically 5–10)
4. **Output:** a new `ViT-B16+ICS_SITE-<site_id>.pth` + updated ONNX

**Reference script:** `scripts/adapt_body_reid_uda.py`

**Expected gain on factory-clothing domain:** +5–12 mAP points based on published UDA results
(MMT, SpCL, TransReID-SSL UDA). Worth the effort once base supervised model is deployed and
measured.

**Constraints:**
- Offline only — never runs during live inference
- Requires ~2–4 hours of unlabeled factory footage minimum
- GPU required for pseudo-label extraction (CPU is too slow for the clustering loop)
- New ONNX must go through the same threshold re-calibration as any model swap
  (CLAUDE.md §0.5 mandatory `/advisor` trigger applies)
- Do not use DukeMTMC as source domain — dataset officially retracted (legal risk)

---

## Approach 2 — USL (Unsupervised Learning)

**When to use:** A brand-new site with no labeled data from any domain and the MSMT17
supervised model performs poorly (e.g. fully uniform workforce). Start from the SSL backbone
(`vit_base_ics_cfs_lup.pth`) and train purely on unlabeled footage from the target site.

**How it works:**

1. Initialize backbone from `vit_base_ics_cfs_lup.pth` (88.4M params, ICS stem, no ID head)
2. Add a fresh BNNeck + projection head (random init)
3. Collect unlabeled tracklets from target site cameras
4. Train with clustering-based contrastive loss (e.g. ClusterContrast, ISE)
5. Output: a site-specific ONNX with no dependency on MSMT17

**Reference script:** `scripts/adapt_body_reid_usl.py` (not yet written — add when needed)

**Expected performance:** 52–62 mAP on MSMT17-equivalent difficulty. Lower ceiling than
supervised + UDA, but requires zero external labels.

**Constraint:** Much longer training than UDA (typically 80–120 epochs vs 20–30 for UDA).
Only justified when the supervised MSMT17 model is genuinely unusable on the target domain.

---

## Decision tree

```
Deploy ViT-B16+ICS_MSMT17.pth
         │
         ▼
Cross-cam re-ID precision on site footage?
         │
    ≥ 70% ──────────────────────────────► Done, no adaptation needed
         │
    < 70%
         │
    Do workers have mostly uniform appearance (PPE)?
         │
        YES ──► UDA: fine-tune supervised model on unlabeled site footage
         │       └── script: scripts/adapt_body_reid_uda.py
         │
        NO  ──► Investigate other causes first (occlusion, low res, camera angle)
                before investing in domain adaptation
```

---

## Implementation notes (fill in when executing)

- [ ] Collect 2h unlabeled factory footage from at least 3 cameras
- [ ] Run `vms/inference/engine.py` offline to extract body crops → save to disk
- [ ] Run `scripts/adapt_body_reid_uda.py` with collected crops
- [ ] Evaluate on held-out 30-min clip (separate from training footage)
- [ ] If mAP gain > 3 points: export to ONNX, re-calibrate `reid_body_confirmed_sim`
- [ ] `/advisor` before changing `reid_body_confirmed_sim` (CLAUDE.md §0.5)
