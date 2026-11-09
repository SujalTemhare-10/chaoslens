FROM python:3.12-slim
WORKDIR /app
COPY svc.py .
HEALTHCHECK --interval=2s --timeout=2s --retries=1 --start-period=3s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=1)"
CMD ["python", "-u", "svc.py"]
