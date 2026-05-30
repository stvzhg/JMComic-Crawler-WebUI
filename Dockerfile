FROM python:slim
LABEL authors="stvzhg"

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt
RUN pip install gunicorn

# Copy default config (override by mounting: -v ./config:/config)
COPY config config
# User-mountable volumes for persistent data and custom config
VOLUME /data
VOLUME /config

COPY static static
COPY templates templates
COPY app.py boot.sh ./
RUN chmod a+x boot.sh

ENV FLASK_APP=app.py

EXPOSE 5000
ENTRYPOINT ["./boot.sh"]