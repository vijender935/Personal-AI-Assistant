# Production Deployment

The repository includes render.yaml for the FastAPI backend and React frontend.

Before production use, configure the model API key and frontend API URL through the deployment environment. Configure CORS to the exact frontend origin. Keep shell access disabled unless explicitly required.

The current application stores SQLite data and uploaded files on the local filesystem. Use persistent storage or migrate the database and file storage to managed services before relying on production data.
