"""
glb_utils.py — GLB 파싱 / 텍스처 베이킹 공통 유틸리티

모든 스크립트에서 공유하는 GLB 로딩 + UV 텍스처 → vertex color 베이킹 로직.
"""

import io
import struct
import json

import numpy as np
from PIL import Image


def _parse_glb(path: str):
    """GLB 바이너리를 파싱해 (gltf_dict, bin_data) 반환."""
    raw = open(path, "rb").read()
    chunk0_len = struct.unpack("<I", raw[12:16])[0]
    gltf = json.loads(raw[20:20 + chunk0_len])
    bin_data = raw[20 + chunk0_len + 8:]
    return gltf, bin_data


def _get_arr(gltf: dict, bin_data: bytes, acc_idx: int, dtype=np.float32) -> np.ndarray:
    """accessors[acc_idx]가 가리키는 버퍼를 numpy 배열로 반환."""
    acc = gltf["accessors"][acc_idx]
    bv  = gltf["bufferViews"][acc["bufferView"]]
    off = bv.get("byteOffset", 0)
    buf = np.frombuffer(bin_data[off:off + bv["byteLength"]], dtype=dtype)
    dim = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[acc["type"]]
    return buf[: acc["count"] * dim].reshape(acc["count"], -1).squeeze()


def bake_vertex_colors(uvs: np.ndarray, tex_img: Image.Image) -> np.ndarray:
    """UV 좌표로 텍스처를 bilinear 샘플링 → RGBA uint8 vertex colors (N, 4)."""
    tex = np.array(tex_img.convert("RGB"), dtype=np.float32)
    H, W = tex.shape[:2]

    u = np.clip(uvs[:, 0], 0.0, 1.0) * (W - 1)
    v = np.clip(uvs[:, 1], 0.0, 1.0) * (H - 1)
    x0 = np.floor(u).astype(np.int32); x1 = np.minimum(x0 + 1, W - 1)
    y0 = np.floor(v).astype(np.int32); y1 = np.minimum(y0 + 1, H - 1)
    wx = (u - x0)[:, None]; wy = (v - y0)[:, None]

    rgb = np.clip(
        tex[y0, x0] * (1 - wx) * (1 - wy) + tex[y0, x1] * wx * (1 - wy) +
        tex[y1, x0] * (1 - wx) * wy        + tex[y1, x1] * wx * wy,
        0, 255,
    ).astype(np.uint8)
    alpha = np.full((len(rgb), 1), 255, dtype=np.uint8)
    return np.concatenate([rgb, alpha], axis=1)


def load_glb_base(path: str):
    """
    GLB에서 base mesh(정점·법선·UV·면) + 텍스처 vertex colors 로드.

    Returns
    -------
    pos, norm, faces, vertex_colors
    """
    gltf, bin_data = _parse_glb(path)
    prim  = gltf["meshes"][0]["primitives"][0]

    pos   = _get_arr(gltf, bin_data, prim["attributes"]["POSITION"])
    norm  = _get_arr(gltf, bin_data, prim["attributes"]["NORMAL"])
    uvs   = _get_arr(gltf, bin_data, prim["attributes"]["TEXCOORD_0"])
    faces = _get_arr(gltf, bin_data, prim["indices"], dtype=np.uint32) \
              .reshape(-1, 3).astype(np.int64)

    img_bv    = gltf["bufferViews"][gltf["images"][0]["bufferView"]]
    img_bytes = bin_data[img_bv.get("byteOffset", 0):
                         img_bv.get("byteOffset", 0) + img_bv["byteLength"]]
    tex_img   = Image.open(io.BytesIO(img_bytes))
    vertex_colors = bake_vertex_colors(uvs, tex_img)

    return pos, norm, faces, vertex_colors


def load_glb_morph(path: str):
    """
    GLB에서 base mesh + morph target delta + 애니메이션 + vertex colors 로드.

    Returns
    -------
    base_pos, base_norm, delta_pos, delta_norm, faces, times, weights, vertex_colors
    """
    gltf, bin_data = _parse_glb(path)
    prim = gltf["meshes"][0]["primitives"][0]

    base_pos  = _get_arr(gltf, bin_data, prim["attributes"]["POSITION"])
    base_norm = _get_arr(gltf, bin_data, prim["attributes"]["NORMAL"])
    uvs       = _get_arr(gltf, bin_data, prim["attributes"]["TEXCOORD_0"])
    faces     = _get_arr(gltf, bin_data, prim["indices"], dtype=np.uint32) \
                  .reshape(-1, 3).astype(np.int64)

    tgt        = prim["targets"][0]
    delta_pos  = _get_arr(gltf, bin_data, tgt["POSITION"])
    delta_norm = _get_arr(gltf, bin_data, tgt["NORMAL"])

    smp     = gltf["animations"][0]["samplers"][0]
    times   = _get_arr(gltf, bin_data, smp["input"])
    weights = _get_arr(gltf, bin_data, smp["output"])

    img_bv    = gltf["bufferViews"][gltf["images"][0]["bufferView"]]
    img_bytes = bin_data[img_bv.get("byteOffset", 0):
                         img_bv.get("byteOffset", 0) + img_bv["byteLength"]]
    vertex_colors = bake_vertex_colors(uvs, Image.open(io.BytesIO(img_bytes)))

    return base_pos, base_norm, delta_pos, delta_norm, faces, times, weights, vertex_colors
