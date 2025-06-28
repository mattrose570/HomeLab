load_env_variables() {
  if [ -f .env ]; then
  set -o allexport
  source .env
  set +o allexport
  else
    echo ".env file not found!"
    exit 1
  fi

}

root_check() {
  if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root. Use: sudo $0"
    exit 1
  fi
# Your root-required commands go here
echo "Running as root..."
}