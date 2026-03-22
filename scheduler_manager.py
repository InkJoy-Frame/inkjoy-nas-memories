import os
import random
import logging
from io import BytesIO
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_tz = 'Asia/Shanghai'
scheduler = BackgroundScheduler(timezone=_tz)

_images_dir = '/images'

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}


def init_scheduler(app):
    global _images_dir, _tz
    _images_dir = app.config.get('IMAGES_DIR', '/images')

    _tz = os.environ.get('TZ', 'Asia/Shanghai')
    scheduler.configure(timezone=_tz)
    scheduler.start()

    from database import get_all_schedules
    loaded = 0
    for schedule in get_all_schedules():
        if schedule['enabled']:
            _add_job(schedule)
            loaded += 1

    logger.info(f'Scheduler started (tz={_tz}), loaded {loaded} job(s).')


def _add_job(schedule):
    try:
        hour, minute = schedule['schedule_time'].split(':')
        trigger = CronTrigger(hour=int(hour), minute=int(minute), timezone=_tz)
        scheduler.add_job(
            execute_schedule,
            trigger,
            args=[schedule['id']],
            id=f"schedule_{schedule['id']}",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        job = scheduler.get_job(f"schedule_{schedule['id']}")
        next_run = job.next_run_time.isoformat() if job and job.next_run_time else 'unknown'
        logger.info(
            f"Job added: schedule {schedule['id']} ('{schedule.get('name', '')}') "
            f"at {schedule['schedule_time']} tz={_tz} → next run: {next_run}"
        )
    except Exception as e:
        logger.error(f"Failed to add job for schedule {schedule['id']}: {e}")


def add_job(schedule):
    _add_job(schedule)


def remove_job(schedule_id):
    job_id = f'schedule_{schedule_id}'
    try:
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            logger.info(f'Job removed: {job_id}')
    except Exception as e:
        logger.error(f'Failed to remove job {job_id}: {e}')


def get_scheduler_status():
    """返回调度器运行状态及所有注册 job 的信息，用于调试。"""
    jobs = []
    try:
        for job in scheduler.get_jobs():
            next_run = job.next_run_time.isoformat() if job.next_run_time else None
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run': next_run,
                'trigger': str(job.trigger),
            })
    except Exception as e:
        logger.error(f'get_scheduler_status error: {e}')

    return {
        'running': scheduler.running,
        'timezone': _tz,
        'server_time': datetime.now().isoformat(),
        'jobs': jobs,
    }


def _pick_random_image(schedule_id, folder, max_scan=2000):
    """
    从 folder（含所有子文件夹）随机选一张图片，兼顾效率与均匀性。

    策略：reservoir sampling（蓄水池抽样），一次遍历 O(N) 时间、O(1) 空间，
    不需要把全部路径都存到内存，适合超大目录。
    超过 max_scan 个文件后仍可正确抽样（每个文件被选中的概率相同）。
    """
    chosen = None
    count = 0
    for root, dirs, files in os.walk(folder):
        # 跳过隐藏目录（如 .thumbnails）
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for fname in files:
            if os.path.splitext(fname)[1].lower() not in IMAGE_EXTENSIONS:
                continue
            count += 1
            # 蓄水池抽样：第 count 个元素以 1/count 概率替换当前选中值
            if random.randint(1, count) == 1:
                chosen = os.path.join(root, fname)
            if count >= max_scan:
                # 已足够大，不再继续遍历（提前返回以保证效率）
                logger.info(
                    f'[schedule:{schedule_id}] scan stopped at {max_scan} files '
                    f'(folder may contain more), sampled: {chosen}'
                )
                return chosen

    logger.info(f'[schedule:{schedule_id}] scanned {count} image(s) recursively in {folder}')
    return chosen


def _apply_blur_fill(img, device_width, device_height):
    """毛玻璃填充：以模糊放大的原图为背景，居中叠加适应缩放的原图。"""
    from PIL import Image, ImageOps, ImageFilter
    # 背景：等比例放大裁切至目标尺寸，再做高斯模糊
    bg = ImageOps.fit(img.copy(), (device_width, device_height), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=24))
    # 前景：等比例缩放至恰好放入目标尺寸（保持原始比例）
    fg = img.copy()
    fg.thumbnail((device_width, device_height), Image.LANCZOS)
    offset = ((device_width - fg.width) // 2, (device_height - fg.height) // 2)
    bg.paste(fg, offset)
    return bg


def execute_schedule(schedule_id):
    from database import get_schedule, get_account, update_schedule_run_status, update_account_token
    from api_client import InkJoyClient
    from PIL import Image, ImageOps

    logger.info(f'[schedule:{schedule_id}] START execute at {datetime.now().isoformat()}')
    try:
        schedule = get_schedule(schedule_id)
        if not schedule:
            logger.warning(f'[schedule:{schedule_id}] not found in DB, skip')
            return
        if not schedule['enabled']:
            logger.warning(f'[schedule:{schedule_id}] disabled, skip')
            return

        account = get_account(schedule['account_id'])
        if not account:
            raise Exception(f'关联账号不存在 (account_id={schedule["account_id"]})')

        logger.info(f'[schedule:{schedule_id}] logging in as {account["email"]} → {account["server_url"]}')
        client = InkJoyClient(account['server_url'])

        # 登录最多重试 3 次，每次间隔 5 秒，避免偶发网络超时导致任务失败
        import time as _time
        login_data = None
        for _attempt in range(3):
            try:
                login_data = client.login(account['email'], account['password'])
                break
            except Exception as _e:
                if _attempt < 2:
                    logger.warning(
                        f'[schedule:{schedule_id}] login attempt {_attempt + 1} failed: {_e}, retrying in 5s…'
                    )
                    _time.sleep(5)
                else:
                    raise
        update_account_token(account['id'], login_data['token'])
        logger.info(f'[schedule:{schedule_id}] login OK')

        folder = schedule['folder_path']
        if not os.path.isabs(folder):
            folder = os.path.join(_images_dir, folder)

        logger.info(f'[schedule:{schedule_id}] resolved folder: {folder}')
        if not os.path.isdir(folder):
            raise Exception(f'文件夹不存在: {folder}')

        image_path = _pick_random_image(schedule_id, folder)
        if not image_path:
            raise Exception(f'文件夹（含子文件夹）中没有图片: {folder}')
        logger.info(f'[schedule:{schedule_id}] selected: {image_path}')

        device_width = schedule.get('device_width')
        device_height = schedule.get('device_height')
        resize_mode = schedule.get('resize_mode', 'crop')

        # ISFR 模式：保留完整画面（不裁切），但等比例缩小到设备分辨率的 1.5 倍以内
        # 避免发送超大原图导致服务器 ISFR 算法处理失败（system error）
        if resize_mode == 'isfr':
            with Image.open(image_path) as orig:
                img = orig.copy()
            if img.mode not in ('RGB',):
                if img.mode == 'RGBA':
                    bg = Image.new('RGB', img.size, (255, 255, 255))
                    bg.paste(img, mask=img.split()[3])
                    img = bg
                else:
                    img = img.convert('RGB')

            # 计算等比缩小目标：不超过设备分辨率的 1.5 倍（若无设备信息则限制 3000px）
            max_w = int((device_width or 2000) * 1.5)
            max_h = int((device_height or 2000) * 1.5)
            orig_size = img.size
            if img.width > max_w or img.height > max_h:
                img.thumbnail((max_w, max_h), Image.LANCZOS)

            output = BytesIO()
            img.save(output, format='JPEG', quality=92)
            output.seek(0)
            image_data = output.read()
            logger.info(
                f'[schedule:{schedule_id}] ISFR mode: {orig_size} → {img.size}, '
                f'size={len(image_data)} bytes (no crop)'
            )
            client.publish_image(schedule['device_id'], image_data)
            update_schedule_run_status(schedule_id, 'success')
            logger.info(f'[schedule:{schedule_id}] DONE OK (isfr)')
            return

        with Image.open(image_path) as orig:
            img = orig.copy()

        # Mode conversion (outside `with` to avoid closed-file issues after copy)
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')
        if img.mode == 'RGBA':
            bg = Image.new('RGB', img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            img = bg

        if device_width and device_height:
            logger.info(
                f'[schedule:{schedule_id}] resize {img.size} → {device_width}×{device_height} mode={resize_mode}'
            )
            if resize_mode == 'crop':
                img = ImageOps.fit(img, (device_width, device_height), Image.LANCZOS)
            elif resize_mode == 'blur':
                img = _apply_blur_fill(img, device_width, device_height)
            else:
                img = img.resize((device_width, device_height), Image.LANCZOS)

        output = BytesIO()
        img.save(output, format='JPEG', quality=95)
        output.seek(0)
        image_data = output.read()
        logger.info(f'[schedule:{schedule_id}] image encoded, size={len(image_data)} bytes')

        logger.info(f'[schedule:{schedule_id}] publishing to device {schedule["device_id"]}')
        client.publish_image(schedule['device_id'], image_data)
        update_schedule_run_status(schedule_id, 'success')
        logger.info(f'[schedule:{schedule_id}] DONE OK')

    except Exception as e:
        logger.error(f'[schedule:{schedule_id}] FAILED: {e}', exc_info=True)
        update_schedule_run_status(schedule_id, 'error', str(e))
