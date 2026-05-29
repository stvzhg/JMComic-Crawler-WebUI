from flask import Flask, request
from flask import render_template
import jmcomic

app = Flask(__name__)

OPTION = jmcomic.create_option_by_file('config/option.yml')

@app.route("/")
def index():
    return render_template('index.html')

@app.route('/download')
def download():
    id = request.args.get('comidId', '')
    print(id)
    try:
        jmcomic.download_album(id, OPTION)
        return render_template('success.html')
    finally:
        return render_template('error.html')
