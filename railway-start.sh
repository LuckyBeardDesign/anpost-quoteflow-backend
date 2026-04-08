#!/bin/bash
echo "Starting FastAPI server..."
uvicorn main:app --host 0.0.0.0 --port ${PORT:-3230}
