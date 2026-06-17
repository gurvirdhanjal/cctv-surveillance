"""
Body Re-ID UDA (Unsupervised Domain Adaptation) fine-tuning script.

Starting point: ViT-B16+ICS_MSMT17.pth (supervised MSMT17 checkpoint)
Target:         unlabeled body crop images from a customer site

Usage:
    python scripts/adapt_body_reid_uda.py \
        --source-ckpt models/ViT-B16+ICS_MSMT17.pth \
        --target-crops data/site_crops/           \
        --output-ckpt  models/ViT-B16+ICS_SITE01.pth \
        --epochs 30

See docs/superpowers/notes/2026-06-15-vms-body-reid-adaptation-strategy.md for
when to run this and how to evaluate the result.

NOTE: This is a reference skeleton — not production-ready.
Fill in the training loop, loss functions, and clustering hyperparameters
before running on real data. Requires GPU.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
from PIL import Image

logger = logging.getLogger(__name__)

# Input spec for ViT-B16+ICS_MSMT17.pth (confirmed from pos_embed shape [1,193,768])
INPUT_H = 384
INPUT_W = 128
EMBED_DIM = 768  # BNNeck output dimension

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------


class CropDataset(Dataset):
    """Flat directory of body crop images (one image = one detection crop)."""

    def __init__(self, root: Path, transform: transforms.Compose) -> None:
        self.paths = sorted(root.glob("**/*.jpg")) + sorted(root.glob("**/*.png"))
        self.transform = transform
        if not self.paths:
            raise FileNotFoundError(f"No images found under {root}")

    def __len__(self) -> int:
        return len(self.paths)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, int]:
        img = Image.open(self.paths[idx]).convert("RGB")
        return self.transform(img), idx


def build_transform() -> transforms.Compose:
    return transforms.Compose(
        [
            transforms.Resize((INPUT_H, INPUT_W)),
            transforms.RandomHorizontalFlip(),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ]
    )


def build_eval_transform() -> transforms.Compose:
    return transforms.Compose(
        [
            transforms.Resize((INPUT_H, INPUT_W)),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ]
    )


# ---------------------------------------------------------------------------
# Model: TransReID inference wrapper
# ---------------------------------------------------------------------------


class TransReIDBodyEmbedder(nn.Module):
    """
    Wraps the ViT-B16+ICS_MSMT17.pth state dict for embedding extraction.

    Architecture (from checkpoint key analysis):
      base.*         — ViT-B/16 backbone with ICS convolutional stem
      bottleneck.*   — BNNeck (BatchNorm1d on 768-dim CLS token)
      classifier.*   — MSMT17 ID head (1041 classes) — used during training only
    """

    def __init__(self) -> None:
        super().__init__()
        # TODO: import or reimplement the TransReID model class.
        # The TransReID repo uses a custom vit_base_patch16_224_TransReID backbone
        # with an ICS convolutional stem. You need either:
        #   a) pip install the TransReID repo and import make_model()
        #   b) reimplement the forward pass matching the checkpoint key structure
        #
        # Checkpoint key layout (verified 2026-06-15):
        #   base.cls_token            [1,1,768]
        #   base.pos_embed            [1,193,768]  <- 384x128 @ stride16 = 24x8=192 patches
        #   base.patch_embed.conv.*   ICS conv stem (7x7 stride-2 -> 3x3 -> 3x3 -> proj)
        #   base.blocks.{0..11}.*     12x transformer blocks
        #   base.norm.*               final LayerNorm
        #   base.fc.*                 [1000,768] ImageNet head (ignored at inference)
        #   bottleneck.*              BNNeck [768]
        #   classifier.*              [1041,768] MSMT17 head
        raise NotImplementedError(
            "Instantiate the TransReID model class here and load the checkpoint. "
            "See TransReID repo: model/make_model.py -> make_model(cfg, num_class=1041)"
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Returns L2-normalized 768-dim body embedding."""
        # feat = self.base(x)       # CLS token, shape (B, 768)
        # feat_bn = self.bottleneck(feat)  # BNNeck
        # return nn.functional.normalize(feat_bn, dim=1)
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Pseudo-label generation (DBSCAN clustering)
# ---------------------------------------------------------------------------


@torch.no_grad()
def extract_embeddings(model: nn.Module, loader: DataLoader, device: torch.device) -> torch.Tensor:
    model.eval()
    all_feats: list[torch.Tensor] = []
    for imgs, _ in loader:
        imgs = imgs.to(device)
        feats = model(imgs)
        all_feats.append(feats.cpu())
    return torch.cat(all_feats, dim=0)


def cluster_pseudo_labels(
    embeddings: torch.Tensor, eps: float = 0.6, min_samples: int = 4
) -> torch.Tensor:
    """
    DBSCAN clustering on L2-normalized embeddings (cosine distance via eps).
    Returns label tensor; -1 = noise (outlier, excluded from training).

    eps and min_samples are the main hyperparameters to tune:
    - Lower eps → tighter clusters, fewer pseudo-identities, higher purity
    - Higher eps → larger clusters, more pseudo-identities, more noise
    """
    from sklearn.cluster import DBSCAN

    emb_np = embeddings.numpy()
    db = DBSCAN(eps=eps, min_samples=min_samples, metric="cosine", n_jobs=-1)
    labels = db.fit_predict(emb_np)
    num_ids = len(set(labels)) - (1 if -1 in labels else 0)
    noise_ratio = (labels == -1).sum() / len(labels)
    logger.info("Clustering: %d pseudo-identities, %.1f%% noise", num_ids, noise_ratio * 100)
    return torch.tensor(labels, dtype=torch.long)


# ---------------------------------------------------------------------------
# Training loop skeleton
# ---------------------------------------------------------------------------


def train_one_epoch(
    model: nn.Module,
    loader: DataLoader,
    pseudo_labels: torch.Tensor,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
) -> float:
    """
    One epoch of UDA fine-tuning using pseudo-labeled contrastive loss.

    TODO: implement the actual loss. Common choices:
    - ClusterContrast (ECCV 2022): memory-based contrastive with cluster centroids
    - SpCL (NeurIPS 2020): soft pseudo labels with reliability scores
    - Triplet loss on pseudo-labeled pairs (simpler baseline)

    This skeleton logs a placeholder loss.
    """
    model.train()
    total_loss = 0.0

    for imgs, indices in loader:
        imgs = imgs.to(device)
        labels = pseudo_labels[indices].to(device)

        # Filter out noise samples (label == -1)
        mask = labels >= 0
        if mask.sum() == 0:
            continue

        feats = model(imgs[mask])
        labels_clean = labels[mask]

        # TODO: replace with ClusterContrast or triplet loss
        loss = torch.tensor(0.0, device=device, requires_grad=True)

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        total_loss += loss.item()

    return total_loss / max(len(loader), 1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Body Re-ID UDA fine-tuning")
    parser.add_argument("--source-ckpt", required=True, type=Path)
    parser.add_argument("--target-crops", required=True, type=Path)
    parser.add_argument("--output-ckpt", required=True, type=Path)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=3.5e-5)
    parser.add_argument(
        "--recluster-every", type=int, default=5, help="Re-generate pseudo labels every N epochs"
    )
    parser.add_argument("--dbscan-eps", type=float, default=0.6)
    parser.add_argument("--dbscan-min-samples", type=int, default=4)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("Device: %s", device)

    # Load model
    model = TransReIDBodyEmbedder()  # will raise NotImplementedError until filled in
    state = torch.load(args.source_ckpt, map_location="cpu", weights_only=False)
    model.load_state_dict(state, strict=True)
    model.to(device)

    # Dataset
    dataset = CropDataset(args.target_crops, build_transform())
    eval_dataset = CropDataset(args.target_crops, build_eval_transform())
    loader = DataLoader(
        dataset, batch_size=args.batch_size, shuffle=True, num_workers=4, pin_memory=True
    )
    eval_loader = DataLoader(eval_dataset, batch_size=256, shuffle=False, num_workers=4)

    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr, weight_decay=5e-4)

    pseudo_labels = torch.full((len(dataset),), -1, dtype=torch.long)

    for epoch in range(1, args.epochs + 1):
        if (epoch - 1) % args.recluster_every == 0:
            logger.info("Epoch %d: extracting embeddings for clustering...", epoch)
            embeddings = extract_embeddings(model, eval_loader, device)
            pseudo_labels = cluster_pseudo_labels(
                embeddings, eps=args.dbscan_eps, min_samples=args.dbscan_min_samples
            )

        loss = train_one_epoch(model, loader, pseudo_labels, optimizer, device)
        logger.info("Epoch %d/%d  loss=%.4f", epoch, args.epochs, loss)

    # Save adapted checkpoint
    args.output_ckpt.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), args.output_ckpt)
    logger.info("Saved adapted checkpoint to %s", args.output_ckpt)
    logger.info(
        "Next step: export to ONNX via scripts/export_transreid_onnx.py, then re-calibrate reid_body_confirmed_sim"
    )


if __name__ == "__main__":
    main()
