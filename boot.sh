#!/bin/bash
exec gunicorn -w 4 -b :5000 --access-logfile - --error-logfile - app:app