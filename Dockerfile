FROM python:3.12-slim
WORKDIR /app
COPY server.py .
COPY public ./public
# PORT can be overridden by the platform (Render/Railway/Cloud Run set it)
ENV PORT=8000
EXPOSE 8000
CMD ["python3", "server.py"]
