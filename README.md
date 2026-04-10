# Faves-FoodNearMe
Aplicatie Web Django

## Docker

Start the stack:

- `docker compose up --build`

For live-reload style development (bind-mount the repo into the container):

- `docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build`

If Docker Desktop fails to start due to a Windows bind-mount error (e.g. `error while creating mount source path '/run/desktop/mnt/host/c/...': mkdir ... file exists`), use the default command (no bind mount):

- `docker compose up --build`
