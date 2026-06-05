"""
camera_utils.py — 카메라 행렬 / 구면 좌표 공통 유틸리티

⚠️  det=+1 우수좌표계 필수:
    right = cross(fwd, world_up) — 이 순서가 틀리면 (world_up × fwd)
    pyrender이 특정 각도에서 완전 검은 화면을 렌더링한다.
"""

import numpy as np


def make_c2w(eye: np.ndarray, center: np.ndarray) -> np.ndarray:
    """
    eye → center를 바라보는 camera-to-world 4×4 행렬 (det=+1).

    Parameters
    ----------
    eye    : (3,) 카메라 위치 (world space)
    center : (3,) 바라볼 목표점 (world space)

    Returns
    -------
    T : (4, 4) c2w 행렬
    """
    fwd = np.asarray(center, float) - np.asarray(eye, float)
    fwd /= np.linalg.norm(fwd)

    world_up = np.array([0., 1., 0.])
    if abs(np.dot(fwd, world_up)) > 0.999:   # gimbal lock 회피
        world_up = np.array([0., 0., 1.])

    right = np.cross(fwd, world_up); right /= np.linalg.norm(right)
    up    = np.cross(right, fwd)

    T = np.eye(4)
    T[:3, :3] = np.stack([right, up, -fwd], axis=1)
    T[:3,  3] = eye
    return T


def spherical_to_eye(center: np.ndarray,
                     az_deg: float,
                     el_deg: float,
                     dist: float) -> np.ndarray:
    """
    구면 좌표 → world-space 카메라 위치.

    Parameters
    ----------
    center : (3,) orbit 기준점
    az_deg : 방위각 (degrees)
    el_deg : 앙각  (degrees)
    dist   : center에서의 거리

    Returns
    -------
    eye : (3,) 카메라 위치
    """
    az = np.radians(az_deg)
    el = np.radians(el_deg)
    offset = dist * np.array([
        np.sin(az) * np.cos(el),
        np.sin(el),
        np.cos(az) * np.cos(el),
    ])
    return np.asarray(center, float) + offset
