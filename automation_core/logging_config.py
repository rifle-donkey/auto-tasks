# ipam_client/logging_config.py
import logging
import sys

def setup_logging(log_file):
    datefmt = '%Y-%m-%d %H:%M:%S'
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        datefmt=datefmt,
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )