from flask import Flask, request, jsonify
from flask import render_template
import jmcomic

app = Flask(__name__)

OPTION = jmcomic.create_option_by_file('config/option.yml')


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
