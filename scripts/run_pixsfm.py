import sys

import argparse
import logging
from pathlib import Path

import pixsfm
import pycolmap
from omegaconf import OmegaConf
from pixsfm.refine_hloc import PixSfM

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sfm_dir", type=str)
    parser.add_argument("--image_dir", type=str)
    parser.add_argument("--pairs_path", type=str)
    parser.add_argument("--features_path", type=str)
    parser.add_argument("--matches_path", type=str)
    parser.add_argument("--cache_path", type=str)
    parser.add_argument("--pixsfm_config", type=str)
    parser.add_argument("--camera_mode", type=str, choices=["single", "auto"])
    args = parser.parse_args()


    formatter = logging.Formatter(
        fmt="[%(asctime)s %(name)s %(levelname)s] %(message)s", datefmt="%Y/%m/%d %H:%M:%S"
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.setLevel(logging.DEBUG)

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    logger.propagate = False


    logging.info(f"Running pixsfm with python: {sys.executable}")


    conf = OmegaConf.load(args.pixsfm_config)

    # conf.mapping.BA.optimizer.refine_extrinsics = True



    refiner = PixSfM(conf=conf)
    sparse_model, _ = refiner.run(
        output_dir=Path(args.sfm_dir),
        image_dir=Path(args.image_dir),
        pairs_path=Path(args.pairs_path),
        features_path=Path(args.features_path),
        matches_path=Path(args.matches_path),
        cache_path=Path(args.cache_path),
        verbose=False,
        camera_mode=pycolmap.CameraMode.AUTO if args.camera_mode == "auto" else pycolmap.CameraMode.SINGLE,
    )

    if sparse_model is not None:
        sparse_model.write(Path(args.sfm_dir))

    # clear cache
    for file in Path(args.cache_path).glob("*"):
        file.unlink()
