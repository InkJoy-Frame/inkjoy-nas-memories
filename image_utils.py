import os
import logging
import tempfile
from io import BytesIO
from PIL import Image, ImageOps

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


def apply_exif_orientation(img):
    """按 EXIF Orientation 把像素转到观看方向。

    相机竖拍常把像素横着存（例如 4240×2400、Orientation 8）。
    转正后才是后续裁切、毛玻璃和相框旋转要用的画面。
    方向为 1 或没有标记时原样返回，并清掉方向标记，避免之后再转一次。
    """
    try:
        orientation = img.getexif().get(0x0112, 1)
    except Exception:
        logger.warning('读取 EXIF Orientation 失败，按像素原方向继续')
        return img
    if orientation in (None, 1):
        return img
    try:
        transposed = ImageOps.exif_transpose(img)
    except Exception:
        logger.warning('EXIF Orientation %s 无法应用，按像素原方向继续', orientation)
        return img
    if transposed is None:
        return img
    logger.info(
        'EXIF orientation %s applied: %s×%s → %s×%s',
        orientation, img.width, img.height, transposed.width, transposed.height,
    )
    return transposed


def open_image(fileobj, ext):
    """打开已经读入的图片，并按 EXIF Orientation 转正。不接受路径，避免打开时再跟随软链接。"""
    if isinstance(fileobj, (str, bytes, os.PathLike)):
        raise TypeError('refusing to open a filesystem path')
    ext = (ext or '').lower()
    fileobj.seek(0)

    if ext in RAW_EXTENSIONS:
        if not _rawpy_available:
            raise RuntimeError(f'rawpy 未安装，无法打开 {ext} 文件')
        payload = fileobj.read()
        return apply_exif_orientation(_open_raw(payload, ext))

    if ext in HEIC_EXTENSIONS and not _heif_available:
        raise RuntimeError(f'pillow-heif 未安装，无法打开 {ext} 文件')

    img = Image.open(fileobj)
    img.load()
    return apply_exif_orientation(img)


def _open_raw(payload, ext):
    try:
        with _rawpy.imread(BytesIO(payload)) as raw:
            rgb = raw.postprocess(use_camera_wb=True)
        return Image.fromarray(rgb)
    except Exception:
        fd, name = tempfile.mkstemp(suffix=ext or '.raw')
        try:
            os.write(fd, payload)
        finally:
            os.close(fd)
        try:
            with _rawpy.imread(name) as raw:
                rgb = raw.postprocess(use_camera_wb=True)
            return Image.fromarray(rgb)
        finally:
            try:
                os.remove(name)
            except OSError:
                pass


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
