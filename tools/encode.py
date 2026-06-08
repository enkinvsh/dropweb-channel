"""Кодирование RGBA-кадров -> webm кастом-эмодзи Telegram (VP9 + альфа).

Эмодзи Telegram: ровно 100x100, <=3с, <=30fps, <=256КБ, без звука, зациклено.
"""
import os
import shutil
import subprocess
import tempfile


def encode_webm(frames, out_path, fps=30, crf=16, size=100):
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg не установлен - выполни: brew install ffmpeg")
    if len(frames) > fps * 3:
        raise ValueError(f"{len(frames)} кадров > 3с при {fps}fps")
    tmp = tempfile.mkdtemp(prefix="dwemoji_")
    try:
        for i, f in enumerate(frames):
            f.convert("RGBA").resize((size, size)).save(
                os.path.join(tmp, f"{i:04d}.png"))
        cmd = [
            "ffmpeg", "-y", "-framerate", str(fps),
            "-i", os.path.join(tmp, "%04d.png"),
            "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
            "-b:v", "0", "-crf", str(crf), "-an",
            "-deadline", "best", "-cpu-used", "0",
            "-auto-alt-ref", "0", "-lag-in-frames", "0",
            "-s", f"{size}x{size}", out_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    kb = os.path.getsize(out_path) / 1024
    if size <= 100 and kb > 256:
        raise RuntimeError(f"{out_path}: {kb:.0f}КБ > 256КБ; подними crf")
    return out_path, kb
