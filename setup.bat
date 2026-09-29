@echo off
echo === Credit Union Pipeline Setup ===
echo.
echo Step 1: Starting all containers...
docker compose up -d
echo.
echo Step 2: Waiting for Postgres to be healthy...
:wait_loop
docker compose ps postgres | findstr "healthy" > nul
if errorlevel 1 (
    echo   Still waiting...
    timeout /t 5 /nobreak > nul
    goto wait_loop
)
echo   Postgres is healthy!
echo.
echo Step 3: Running Alembic migrations...
docker compose exec api alembic upgrade head
echo.
echo Step 4: Verifying tables were created...
docker compose exec postgres psql -U appuser -d creditunion -c "\dt"
echo.
echo Setup complete! Open:
echo   API docs:  http://localhost:8000/docs
echo   n8n:       http://localhost:5678
echo   Dashboard: http://localhost:8501
