import sys

from autochat.worker import run_autochat_worker

if __name__ == "__main__":
    run_autochat_worker(sys.argv[1:])
