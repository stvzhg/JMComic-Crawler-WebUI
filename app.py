import json
import os
import shutil
import threading
import time
import uuid

from flask import Flask, request, jsonify
from flask import render_template
import jmcomic
from jmcomic.jm_toolkit import JmcomicText

app = Flask(__name__)

# --- Config bootstrap ---

CONFIG_PATH = 'config/option.yml'
EXAMPLE_CONFIG_PATH = 'option.example.yml'

if not os.path.isfile(CONFIG_PATH):
    if os.path.isfile(EXAMPLE_CONFIG_PATH):
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        shutil.copyfile(EXAMPLE_CONFIG_PATH, CONFIG_PATH)
        print(f'Created {CONFIG_PATH} from {EXAMPLE_CONFIG_PATH}')
    else:
        print(f'Warning: neither {CONFIG_PATH} nor {EXAMPLE_CONFIG_PATH} found, '
              f'falling back to JMComic defaults')

OPTION = jmcomic.create_option_by_file(CONFIG_PATH) if os.path.isfile(CONFIG_PATH) \
    else jmcomic.create_option_by_str('{}')

# --- File-based task store (cross-worker safe) ---

TASKS_DIR = 'data/.tasks'


def _task_path(task_id):
    return os.path.join(TASKS_DIR, f'{task_id}.json')


def _read_task(task_id):
    """Read a task file. Returns dict or None if not found / corrupt."""
    try:
        with open(_task_path(task_id), 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _write_task(task_id, data):
    """Atomically write a task file (tmp + rename)."""
    os.makedirs(TASKS_DIR, exist_ok=True)
    path = _task_path(task_id)
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f)
    os.rename(tmp, path)  # atomic on POSIX


# --- Progress-aware downloader ---

class ProgressDownloader(jmcomic.JmDownloader):
    """JmDownloader subclass that writes progress to a task file.

    Uses a class-level _current_task_id so the background thread can inject
    the task id before jmcomic.download_album() instantiates the downloader
    via new_downloader(). Safe because each gunicorn sync worker is single-
    threaded — at most one download runs per worker at a time.
    """

    _current_task_id = None

    def __init__(self, option):
        super().__init__(option)
        self._task_id = ProgressDownloader._current_task_id
        # Debounce file writes: only flush every N images
        self._write_interval = 3
        self._last_written_pages = 0

    def _update_task(self, **kwargs):
        """Read-modify-write the task file atomically."""
        task = _read_task(self._task_id) or {}
        task.update(kwargs)
        _write_task(self._task_id, task)

    def before_album(self, album):
        super().before_album(album)
        self._update_task(
            total_pages=getattr(album, 'page_count', 0) or 0,
            total_chapters=len(album),
            album_title=getattr(album, 'name', '') or getattr(album, 'title', ''),
            status='downloading',
        )

    def after_image(self, image, img_save_path):
        super().after_image(image, img_save_path)
        task = _read_task(self._task_id)
        if task is None:
            return
        downloaded = task.get('downloaded_pages', 0) + 1
        # Debounce: write to disk every _write_interval images
        if downloaded - self._last_written_pages >= self._write_interval:
            task['downloaded_pages'] = downloaded
            _write_task(self._task_id, task)
            self._last_written_pages = downloaded

    def after_photo(self, photo):
        super().after_photo(photo)
        task = _read_task(self._task_id)
        if task is None:
            return
        task['downloaded_chapters'] = task.get('downloaded_chapters', 0) + 1
        # Always flush on chapter completion (catches remaining images
        # that didn't hit the debounce threshold in after_image)
        task['downloaded_pages'] = task.get('downloaded_pages', 0)
        _write_task(self._task_id, task)


# --- Cleanup daemon ---

def _cleanup_old_tasks():
    """Periodically remove stale task files."""
    while True:
        time.sleep(60)
        now = time.time()
        try:
            for fname in os.listdir(TASKS_DIR):
                if not fname.endswith('.json'):
                    continue
                task_id = fname.replace('.json', '')
                task = _read_task(task_id)
                if task is None:
                    # Corrupt or empty — remove if older than 10 min
                    try:
                        mtime = os.path.getmtime(os.path.join(TASKS_DIR, fname))
                        if now - mtime > 600:
                            os.remove(os.path.join(TASKS_DIR, fname))
                    except OSError:
                        pass
                    continue
                status = task.get('status', '')
                if status in ('done', 'error'):
                    finished_at = task.get('finished_at', 0)
                    if now - finished_at > 300:  # 5 min
                        os.remove(os.path.join(TASKS_DIR, fname))
                elif status == 'starting':
                    created_at = task.get('created_at', 0)
                    if now - created_at > 600:  # 10 min — likely crashed
                        os.remove(os.path.join(TASKS_DIR, fname))
        except FileNotFoundError:
            pass


_cleanup_thread = threading.Thread(target=_cleanup_old_tasks, daemon=True)
_cleanup_thread.start()

# --- Routes ---


@app.route("/")
def index():
    return render_template('index.html')


@app.route('/api/download', methods=['POST'])
def api_download():
    """Start a download in a background thread. Returns a task_id for polling."""
    data = request.get_json(silent=True)
    comic_id = (data or {}).get('comic_id', '').strip()

    if not comic_id:
        return jsonify({'status': 'error', 'message': 'No comic ID provided'}), 400

    task_id = str(uuid.uuid4())
    now = time.time()

    # Write initial task file (visible immediately to all workers)
    _write_task(task_id, {
        'task_id': task_id,
        'status': 'starting',
        'comic_id': comic_id,
        'total_pages': 0,
        'downloaded_pages': 0,
        'total_chapters': 0,
        'downloaded_chapters': 0,
        'album_title': '',
        'message': '',
        'created_at': now,
        'finished_at': None,
    })

    def _run():
        try:
            ProgressDownloader._current_task_id = task_id
            album, _downloader = jmcomic.download_album(
                comic_id, OPTION, downloader=ProgressDownloader
            )
            album_title = getattr(album, 'name', None) or getattr(album, 'title', comic_id)
            _write_task(task_id, {
                **_read_task(task_id),
                'status': 'done',
                'album_title': album_title,
                'message': f'Album "{album_title}" downloaded successfully.',
                'finished_at': time.time(),
            })
        except Exception as e:
            task = _read_task(task_id) or {}
            _write_task(task_id, {
                **task,
                'status': 'error',
                'message': str(e),
                'finished_at': time.time(),
            })

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return jsonify({'status': 'accepted', 'task_id': task_id})


@app.route('/api/progress/<task_id>', methods=['GET'])
def api_progress(task_id):
    """Return current download progress for a task (cross-worker safe)."""
    task = _read_task(task_id)
    if task is None:
        return jsonify({
            'status': 'not_found',
            'message': 'Task not found. It may have been cleaned up or the ID is invalid.',
        }), 404
    return jsonify(task)


@app.route('/api/preview', methods=['POST'])
def api_preview():
    """Fetch album metadata without downloading."""
    data = request.get_json(silent=True)
    comic_id = (data or {}).get('comic_id', '').strip()

    if not comic_id:
        return jsonify({'status': 'error', 'message': 'No comic ID provided'}), 400

    try:
        client = OPTION.build_jm_client()
        album = client.get_album_detail(comic_id)
        cover_url = JmcomicText.get_album_cover_url(comic_id)

        return jsonify({
            'status': 'success',
            'album_id': album.album_id,
            'title': album.name,
            'authors': album.authors,
            'tags': album.tags,
            'description': album.description or '',
            'views': album.views,
            'likes': album.likes,
            'page_count': album.page_count,
            'chapter_count': len(album),
            'cover_url': cover_url,
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/download')
def download():
    """Server-rendered download — used as no-JS fallback."""
    comic_id = request.args.get('comicId', '').strip()
    print(comic_id)
    try:
        album, _downloader = jmcomic.download_album(comic_id, OPTION)
        album_title = getattr(album, 'title', comic_id)
        return render_template('success.html', comic_id=comic_id, album_title=album_title)
    except Exception as e:
        return render_template('error.html', message=str(e))
