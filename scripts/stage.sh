set -e
version="stage-$1"

#git checkout main

docker build -t pms-staging:$version .

docker container rm --force pms-staging-$1 &>/dev/null && echo 'Removed old container'

docker run -d -p $1:80 --name pms-staging-$1 --rm pms-staging:$version
