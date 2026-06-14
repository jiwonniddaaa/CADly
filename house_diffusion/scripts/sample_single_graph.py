"""
Single graph inference entrypoint for CADly + HouseDiffusion.

Example:
python sample_single_graph.py \
  --graph_json examples/single_graph.json \
  --model_path ckpts/exp/model250000.pt \
  --out_dir outputs/cadly \
  --name test_001 \
  --dataset rplan \
  --batch_size 1 \
  --set_name eval \
  --target_set 8
"""

from __future__ import annotations

import argparse
import os

import torch as th

from house_diffusion import dist_util, logger
from house_diffusion.script_util import (
    model_and_diffusion_defaults,
    create_model_and_diffusion,
    add_dict_to_argparser,
    args_to_dict,
    update_arg_parser,
)

from house_diffusion.single_graph_dataset import load_single_graph_data
from utils.export_floorplan import export_prediction


def _to_cuda_model_kwargs(model_kwargs):
    cuda_kwargs = {}
    room_meta = None

    for key, value in model_kwargs.items():
        if key == "room_meta":
            # DataLoader collates list[dict] into a dict/list structure depending on PyTorch version.
            room_meta = value
            continue

        if hasattr(value, "cuda"):
            cuda_kwargs[key] = value.cuda()
        else:
            cuda_kwargs[key] = value

    room_meta = _normalize_room_meta(room_meta)
    return cuda_kwargs, room_meta


def _normalize_room_meta(room_meta):
    """
    Handles PyTorch DataLoader's default collation for metadata.
    Preferred alternative: pass room_meta separately, but this keeps the loader simple.
    """
    if isinstance(room_meta, list) and room_meta and isinstance(room_meta[0], dict):
        return room_meta

    if isinstance(room_meta, dict):
        # Collated dict of lists/tensors -> list of dicts
        keys = list(room_meta.keys())
        n = len(room_meta[keys[0]])
        rows = []
        for i in range(n):
            row = {}
            for k in keys:
                v = room_meta[k][i]
                if hasattr(v, "item"):
                    v = v.item()
                row[k] = v
            rows.append(row)
        return rows

    # Fallback: no labels
    return []


def main():
    args = create_argparser().parse_args()
    update_arg_parser(args)

    dist_util.setup_dist()
    logger.configure()

    logger.log("creating model and diffusion...")
    model, diffusion = create_model_and_diffusion(
        **args_to_dict(args, model_and_diffusion_defaults().keys())
    )
    model.load_state_dict(dist_util.load_state_dict(args.model_path, map_location="cpu"))
    model.to(dist_util.dev())
    model.eval()

    data = load_single_graph_data(
        graph_json=args.graph_json,
        batch_size=1,
        analog_bit=args.analog_bit,
    )

    data_sample, model_kwargs = next(data)
    model_kwargs, room_meta = _to_cuda_model_kwargs(model_kwargs)
    data_sample = data_sample.cuda()

    sample_fn = diffusion.p_sample_loop if not args.use_ddim else diffusion.ddim_sample_loop

    logger.log("sampling single CADly graph...")
    sample = sample_fn(
        model,
        data_sample.shape,
        clip_denoised=args.clip_denoised,
        model_kwargs=model_kwargs,
        analog_bit=args.analog_bit,
    )

    # Original image_sample.py converts [steps, batch, coord, points] -> [steps, batch, points, coord].
    sample = sample.permute([0, 1, 3, 2])

    os.makedirs(args.out_dir, exist_ok=True)
    export_prediction(
        sample=sample,
        model_kwargs=model_kwargs,
        room_meta=room_meta,
        out_dir=args.out_dir,
        name=args.name,
    )

    logger.log(f"done. exported to {args.out_dir}")


def create_argparser():
    defaults = dict(
        graph_json="",
        out_dir="outputs/cadly",
        name="floorplan",
        clip_denoised=True,
        batch_size=1,
        use_ddim=False,
        model_path="",
    )
    defaults.update(model_and_diffusion_defaults())

    parser = argparse.ArgumentParser()
    add_dict_to_argparser(parser, defaults)
    return parser


if __name__ == "__main__":
    main()
