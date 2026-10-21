.PHONY: setup up down logs ps test smoke package

setup:
	cp .env.example .env
	chmod 600 .env
	./scripts/download_models.sh

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=150

ps:
	docker compose ps

test:
	docker build --target test -t facerec-tests ./backend
	docker run --rm facerec-tests

smoke:
	./scripts/smoke_test.sh

package:
	tar --exclude='./frontend/node_modules' --exclude='./frontend/dist' --exclude='./.env' --exclude='./facerec-lab.tar.gz' -czf facerec-lab.tar.gz .
