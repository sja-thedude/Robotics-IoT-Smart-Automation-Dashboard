# RoboGrid AI — common developer & ops commands
.PHONY: help build up down logs migrate makemigrations superuser seed shell test \
        bridge simulate worker beat collectstatic check

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

build:           ## Build the application image
	docker compose build

up:              ## Start the full stack
	docker compose up -d

down:            ## Stop the stack
	docker compose down

logs:            ## Tail logs (make logs s=web)
	docker compose logs -f $(s)

migrate:         ## Apply migrations
	docker compose run --rm web python manage.py migrate

makemigrations:  ## Create migrations
	docker compose run --rm web python manage.py makemigrations

superuser:       ## Create a Django superuser
	docker compose run --rm web python manage.py createsuperuser

seed:            ## Load demo org/devices/sensors/rules
	docker compose run --rm web python manage.py seed_demo

shell:           ## Django shell
	docker compose run --rm web python manage.py shell

check:           ## Run Django system checks
	docker compose run --rm web python manage.py check

test:            ## Run the test suite
	docker compose run --rm web python manage.py test

collectstatic:   ## Collect static files
	docker compose run --rm web python manage.py collectstatic --noinput

bridge:          ## Run the MQTT bridge locally
	python manage.py run_mqtt_bridge

simulate:        ## Simulate a device (make simulate serial=ROBO-001)
	python manage.py simulate_device --serial $(serial)

worker:          ## Run a celery worker locally
	celery -A config worker -l info

beat:            ## Run celery beat locally
	celery -A config beat -l info
