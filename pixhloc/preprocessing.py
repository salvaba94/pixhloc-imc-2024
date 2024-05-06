import argparse
import gc
import logging
import torch
from pathlib import Path
from typing import Any, Dict, List, Tuple
from torchvision import transforms

import cv2
import torch
from torch import nn

import numpy as np
from tqdm import tqdm


class OrientationPredictor(nn.Module):

    def __init__(self, rotation_weights, device="auto", dtype="float16"):

        import timm
        from iglovikov_helper_functions.config_parsing.utils import object_from_dict
        from iglovikov_helper_functions.dl.pytorch.utils import state_dict_from_disk


        model = {
            "type": timm.create_model,
            "model_name": "swsl_resnext50_32x4d",
            "num_classes": 4,
            "pretrained": True
        }

        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"

        self.model = object_from_dict(model)
        corrections: Dict[str, str] = {"model.": ""}
        state_dict = state_dict_from_disk(file_path=rotation_weights, rename_in_layers=corrections)
        self.model.load_state_dict(state_dict)

        self.model = torch.nn.Sequential(self.model, torch.nn.Softmax(dim=1))
        self.model = self.model.eval().to(device=device).to(dtype=dtype)

        self.transforms = transforms.Compose(
            transforms.ToTensor(),
            transforms.Resize(size=(224, 224)),
            transforms.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
        )

        self.angles = np.array([0, 90, 180, 270])

    def forward(self, image):
        image = self.transforms(image)
        logits = self.model(image)
        result = self.angles[torch.argmax(logits, dim=-1)]
        return result, logits



def resize_image(image: np.ndarray, max_size: int) -> np.ndarray:
    """Resize image to max_size.

    Args:
        image (np.ndarray): Image to resize.
        max_size (int): Maximum size of the image.

    Returns:
        np.ndarray: Resized image.
    """
    img_size = image.shape[:2]
    if max(img_size) > max_size:
        ratio = max_size / max(img_size)
        image = cv2.resize(image, (0, 0), fx=ratio, fy=ratio, interpolation=cv2.INTER_LANCZOS4)
    return image


def get_rotated_image(image: np.ndarray, angle: float) -> Tuple[np.ndarray, float]:
    """Rotate image by angle (rounded to 90 degrees).

    Args:
        image (np.ndarray): Image to rotate.
        angle (float): Angle to rotate the image by.

    Returns:
        Tuple[np.ndarray, float]: Rotated image and the angle it was rotated by.
    """
    if angle < 0.0:
        angle += 360
    angle = (round(angle / 90.0) * 90) % 360  # angle is now an integer in [0, 90, 180, 270]

    # rotate and save image
    if angle == 90:
        image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    elif angle == 180:
        image = cv2.rotate(image, cv2.ROTATE_180)
    elif angle == 270:
        image = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)

    return image, int(angle)


def preprocess_image_dir(
    input_dir: Path, output_dir: Path, image_list: List[str], args: argparse.Namespace
) -> Tuple[Dict[str, Any], bool]:
    """Preprocess images in input_dir and save them to output_dir.

    Args:
        input_dir (Path): Directory containing the a folder "images" with the images to preprocess.
        output_dir (Path): Directory to save the preprocessed images to.
        image_list (List[str]): List of image file names.
        args (argparse.Namespace): Arguments.

    Returns:
        Tuple[Dict[str, Any], bool]: Dictionary mapping image file names to rotation angles and
            whether all images have the same shape.
    """
    same_original_shapes = True
    prev_shape = None

    # log paths to debug
    logging.debug(f"Rescaling {input_dir / 'images'}")
    logging.debug(f"Saving to {output_dir / 'images'}")

    for image_fn in tqdm(image_list, desc=f"Rescaling {input_dir.name}", ncols=80):
        img_path = input_dir / "images" / image_fn
        image = cv2.imread(str(img_path))

        if prev_shape is not None:
            same_original_shapes &= prev_shape == image.shape

        prev_shape = image.shape

        # resize image
        if args.resize is not None:
            image = resize_image(image, args.resize)

        cv2.imwrite(str(output_dir / "images" / image_fn), image)

    # rotate image
    rotation_angles = {}
    n_rotated = 0
    n_total = len(image_list)

    same_rotated_shapes = True
    prev_shape = None

    if args.rotation_matching or args.rotation_wrapper:
        # log paths to debug
        logging.debug(f"Rotating {output_dir / 'images'}")
        logging.debug(f"Saving to {output_dir / 'images_rotated'}")

        deep_orientation = OrientationPredictor(args.rotation_weights)


        for image_fn in tqdm(image_list, desc=f"Rotating {input_dir.name}", ncols=80):
            img_path = output_dir / "images" / image_fn

            image = cv2.imread(str(img_path))
            angle, _ = deep_orientation(image)

            image = cv2.imread(str(img_path))
            image, angle = get_rotated_image(image, angle)

            if prev_shape is not None:
                same_rotated_shapes &= prev_shape == image.shape

            prev_shape = image.shape

            if angle != 0:
                n_rotated += 1

            cv2.imwrite(str(output_dir / "images_rotated" / image_fn), image)

            rotation_angles[image_fn] = angle

        # free cuda memory
        del deep_orientation
        gc.collect()
        # device = cuda.get_current_device()
        # device.reset()

    logging.info(f"Rotated {n_rotated} of {n_total} images.")

    same_shape = same_rotated_shapes if args.rotation_wrapper else same_original_shapes

    logging.info(f"Images have same shapes: {same_shape}.")

    return rotation_angles, same_shape