# JMComic Crawler WebUI

A lightweight web interface for [JMComic-Crawler-Python](https://github.com/hect0x7/JMComic-Crawler-Python). Enter a comic album ID, preview metadata, and download with real-time progress tracking.

**GitHub** — [stvzhg/JMComic-Crawler-WebUI](https://github.com/stvzhg/JMComic-Crawler-WebUI)  
**Docker Hub** — [stvzhg/jmcomic-downloader](https://hub.docker.com/r/stvzhg/jmcomic-downloader)  
**Upstream library** — [hect0x7/JMComic-Crawler-Python](https://github.com/hect0x7/JMComic-Crawler-Python)

## Features

- **Preview** — fetch album metadata (title, authors, tags, cover) before downloading
- **Progress tracking** — real-time progress bar with page and chapter counters
- **Responsive UI** — works on desktop and mobile
- **Docker support** — pre-built image with persistent data and config volumes

## Quick Start

### Local

```bash
# Clone and install
git clone https://github.com/stvzhg/JMComic-Crawler-WebUI.git
cd JMComic-Crawler-WebUI
pip install -r requirements.txt

# (Optional) Customize config
cp option.example.yml config/option.yml
# edit config/option.yml as needed

# Start server
flask run
# or for production:
gunicorn -w 4 -b :5000 app:app
```

Open http://localhost:5000, enter an album ID, and click **Preview** or **Download**.

### Docker

```bash
docker pull stvzhg/jmcomic-downloader

docker run -p 5000:5000 \
  -v ./data:/data \
  -v ./config:/config \
  stvzhg/jmcomic-downloader
```

- `/data` — downloaded comics persist here
- `/config` — mount your own `option.yml` to customize download settings (see `option.example.yml`)

On first run without a mounted config, the example config is copied automatically.

## Configuration

Copy `option.example.yml` to `config/option.yml` and customize:

- **Download format** — image suffix (`.png`, `.jpg`, or null for original)
- **Directory layout** — folder naming pattern for downloaded albums
- **Threading** — concurrent image and chapter downloads
- **Plugins** — zip, PDF, email notifications, and more

See the [upstream option file syntax](https://github.com/hect0x7/JMComic-Crawler-Python/blob/master/assets/docs/sources/option_file_syntax.md) for all available options.

## Development

```bash
# Python >= 3.9
pip install -r requirements.txt
flask run
```

Tech stack: Flask + Jinja2 + vanilla JS. No frontend framework. CSS is mobile-first with a single breakpoint at 600px.

### Tests

```bash
# Install test dependencies
pip install pytest pytest-cov

# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=app --cov-report=term-missing --cov-branch
```
