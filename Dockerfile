FROM python:slim
LABEL authors="stvzhg"

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt
RUN pip install gunicorn

VOLUME /data
COPY config config
COPY static static
COPY templates templates
COPY app.py boot.sh ./
RUN chmod a+x boot.sh

ENV FLASK_APP app.py

EXPOSE 5000
ENTRYPOINT ["./boot.sh"]