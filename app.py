import os
import shutil
from flask import Flask, request, jsonify
from flask import render_template
import jmcomic

app = Flask(__name__)

# Ensure a working config exists: copy the example if option.yml is missing
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


@app.route("/")
def index():
    return render_template('index.html')


@app.route('/api/download', methods=['POST'])
def api_download():
    """JSON API for async download requests from the frontend."""
    data = request.get_json(silent=True)
    comic_id = (data or {}).get('comic_id', '').strip()

    if not comic_id:
        return jsonify({'status': 'error', 'message': 'No comic ID provided'}), 400

    try:
        album, _downloader = jmcomic.download_album(comic_id, OPTION)
        album_title = getattr(album, 'title', comic_id)
        return jsonify({
            'status': 'success',
            'message': f'Album "{album_title}" downloaded successfully.',
            'album_title': album_title,
            'album_id': comic_id,
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
