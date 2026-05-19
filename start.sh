#!/bin/bash
pip install -r requirements_web.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
