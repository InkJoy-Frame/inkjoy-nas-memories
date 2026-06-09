import os
import logging
from PIL import Image

logger = logging.getLogger(__name__)

STANDARD_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
HEIC_EXTENSIONS = {'.heic', '.heif'}
RAW_EXTENSIONS = {
    '.arw', '.cr2', '.cr3', '.nef', '.dng',
    '.raw', '.orf', '.rw2', '.raf', '.pef', '.srw',
}
IMAGE_EXTENSIONS = STANDARD_EXTENSIONS | HEIC_EXTENSIONS | RAW_EXTENSIONS

_heif_available = False

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    _heif_available = True
except ImportError:
    logger.warning('pillow-heif 未安装，HEIC/HEIF 格式不可用')

_rawpy_available = False

try:
    import rawpy as _rawpy
    _rawpy_available = True
except ImportError:
    logger.warning('rawpy 未安装，RAW 格式（ARW/NEF/DNG 等）不可用')


def open_image(path):
    """打开任意支持格式的图片，返回 PIL Image（像素已加载，文件句柄已释放）。"""
    ext = os.path.splitext(path)[1].lower()

    if ext in RAW_EXTENSIONS:
        if not _rawpy_available:
            raise RuntimeError(f'rawpy 未安装，无法打开 {ext} 文件')

        with _rawpy.imread(path) as raw:
            rgb = raw.postprocess(use_camera_wb=True)

        return Image.fromarray(rgb)

    if ext in HEIC_EXTENSIONS and not _heif_available:
        raise RuntimeError(f'pillow-heif 未安装，无法打开 {ext} 文件')

    img = Image.open(path)
    img.load()
    return img


def ensure_rgb(img):
    """RGBA/其他模式 → RGB，白底合成透明通道。"""
    if img.mode == 'RGBA':
        bg = Image.new('RGB', img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        return bg

    if img.mode != 'RGB':
        return img.convert('RGB')

    return img


# 与 webtool 对齐：估算 PNG ≤ 5MB 时用 PNG，否则回退 JPEG
_PNG_BYTE_RATIO = 2.5
_MAX_PNG_BYTES = 5 * 1024 * 1024


def save_for_display(img, output):
    """保存图片用于推送到墨水屏。优先 PNG 无损（消除 JPEG DCT 伪影），大图回退 JPEG。
    返回 (ext, mimetype)，如 ('png', 'image/png')。
    """
    est_png = img.width * img.height * _PNG_BYTE_RATIO

    if est_png <= _MAX_PNG_BYTES:
        img.save(output, format='PNG')
        return 'png', 'image/png'

    img.save(output, format='JPEG', quality=95)
    return 'jpeg', 'image/jpeg'
